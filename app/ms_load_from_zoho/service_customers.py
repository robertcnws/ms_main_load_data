# =========================
# BOOKS CUSTOMERS SERVICE (fixed)
# =========================

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, List
import logging
import os
import time
import requests

from django.conf import settings
from mongoengine.queryset.visitor import Q

from ms_load_from_zoho.models import (
    AppConfig,
    ZohoCustomer,
    SyncMetadata,
)
from ms_load_from_zoho.manage_instances import create_books_customers_instance
import ms_load_from_zoho.helpers as helpers

# Utilidades compartidas (parseos/fecha y sesión robusta)
from ms_load_from_zoho.service_shipments import (
    _iso_zoho_midnight_utc,
    _new_session,
    _parse_zoho_date,
    _parse_zoho_ts,
)
# Persistencia de métricas en colección (no en memoria)
from ms_load_from_zoho.metrics import set_metrics, now_iso

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def _lm_customer_any(it: Dict[str, Any]) -> Optional[datetime]:
    """Devuelve el mejor timestamp disponible para un customer de Books."""
    return (
        _parse_zoho_ts(it.get("last_modified_time"))
        or _parse_zoho_ts(it.get("created_time"))
        or _parse_zoho_date(it.get("date"))
    )


def load_customers_service(*, start_date: Optional[str], zoho_org_id: str) -> Dict[str, Any]:
    """
    Servicio idempotente para cargar/actualizar Customers desde Zoho Books.
    - Aplica cutoff = medianoche UTC de 'start_date'
    - Paginación robusta:
        * Enviamos sort_order=D (desc). 
        * Solo aplicamos early-stop si detectamos que el batch llega en DESC (nuevo->viejo).
        * Si el endpoint ignora el orden, seguimos paginando hasta que no haya más páginas.
    - Sin llamadas de detalle (el listado trae lo necesario).
    """
    t0 = time.time()
    list_calls = 0
    created = updated = 0
    status = "ok"
    hit_max_pages = False

    logger.info("CUSTOMERS: START")
    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    if not app_config:
        raise RuntimeError(f"AppConfig not found for zoho_org_id={zoho_org_id}")

    # start_date fallback: last_sync o hoy (UTC)
    if not start_date:
        last_sync = SyncMetadata.get_last_sync_date("last_sync_date_customers")
        if last_sync:
            try:
                base = datetime.strptime(last_sync, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except Exception:
                base = datetime.now(timezone.utc)
        else:
            base = datetime.now(timezone.utc)
        start_date = base.strftime("%Y-%m-%d")

    # Cutoff: medianoche UTC de start_date (formato Zoho: ...T00:00:00+0000)
    start_anchor = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    last_modified_time = _iso_zoho_midnight_utc(start_anchor)
    cutoff_dt = _parse_zoho_ts(last_modified_time)

    logger.info(
        "CUSTOMERS: org=%s start=%s last_modified_time=%s (cutoff=%s)",
        zoho_org_id, start_date, last_modified_time, cutoff_dt.isoformat() if cutoff_dt else None,
    )

    # Headers Zoho
    try:
        headers = helpers.config_headers(zoho_org_id)
    except Exception as e:
        logger.error(f"Error connecting to Zoho API (headers): {e}")
        status = "error"
        set_metrics(
            "customers",
            zoho_org_id=zoho_org_id,
            last_run=now_iso(),
            last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_customers") or "",
            list_calls=list_calls,
            detail_calls=0,
            package_calls=0,
            created=created,
            updated=updated,
            duration_sec=round(time.time() - t0, 3),
            status=status,
        )
        return {"status": "error", "message": str(e)}

    # Parámetros de listado
    url = settings.ZOHO_BOOKS_CUSTOMERS_URL
    sort_column = os.getenv("ZOHO_CUSTOMERS_SORT_COLUMN", "last_modified_time")
    sort_order = os.getenv("ZOHO_CUSTOMERS_SORT_ORDER", "D").upper()  # D=desc, A=asc

    params = {
        "organization_id": app_config.zoho_org_id,
        "per_page": int(os.getenv("ZOHO_LIST_PER_PAGE", "200")),
        "page": 1,
        "sort_column": sort_column,
        "sort_order": sort_order,      # <- IMPORTANTE: forzar descendente
        # Si el endpoint lo soporta, esto filtra desde servidor (mejor performance):
        # "last_modified_time": last_modified_time,
    }

    MAX_PAGES = int(os.getenv("ZOHO_MAX_PAGES", "200"))
    PAGE_DELAY = float(os.getenv("ZOHO_LIST_PAGE_DELAY_SEC", "1"))

    items_list: List[Dict[str, Any]] = []
    page = 1

    # Flags para autodetectar el orden real del batch (por si el endpoint ignora sort_order)
    order_detected = False
    detected_desc = False  # True si vemos first_lm > last_lm en el batch

    with _new_session() as session:
        while True:
            try:
                params["page"] = page
                resp = session.get(url, headers=headers, params=params, timeout=60)
                list_calls += 1

                # Refresh token on 401
                if resp.status_code == 401:
                    new_token = helpers.refresh_zoho_access_token(zoho_org_id)
                    headers["Authorization"] = f"Zoho-oauthtoken {new_token}"
                    resp = session.get(url, headers=headers, params=params, timeout=60)
                    list_calls += 1

                if resp.status_code == 429:
                    ra = resp.headers.get("Retry-After")
                    try:
                        wait_s = float(ra) if ra is not None else 2.0
                    except Exception:
                        wait_s = 2.0
                    logger.warning(f"429 on customers list page={page} -> sleeping {wait_s}s")
                    time.sleep(wait_s)
                    continue

                resp.raise_for_status()
                payload = resp.json() if resp.content else {}
                batch = payload.get("contacts", []) or []
                items_list.extend(batch)

                # --- Telemetría de LM y detección de orden ---
                if batch:
                    ts_vals = [ts for ts in (_lm_customer_any(x) for x in batch) if ts]
                    first_lm = max(ts_vals) if ts_vals else None  # el más nuevo del batch
                    last_lm = min(ts_vals) if ts_vals else None   # el más viejo del batch

                    logger.info(
                        "Customers page=%s got=%s lm_first=%s lm_last=%s cutoff=%s",
                        page, len(batch),
                        first_lm.isoformat() if first_lm else None,
                        last_lm.isoformat() if last_lm else None,
                        cutoff_dt.isoformat() if cutoff_dt else None
                    )

                    # Autodetectar si el batch viene ordenado DESC (nuevo->viejo)
                    if not order_detected and first_lm and last_lm:
                        detected_desc = first_lm > last_lm
                        order_detected = True
                        logger.info("Customers order detected: %s", "DESC" if detected_desc else "ASC/unknown")

                    # Early-stop SOLO si realmente está en DESC (o si el caller lo pidió y coincide)
                    if (detected_desc or sort_order == "D") and last_lm and cutoff_dt and last_lm < cutoff_dt:
                        logger.info("Stopping paging (customers): last_lm < cutoff (page=%s, DESC)", page)
                        break

                page_ctx = payload.get("page_context", {}) or {}
                has_more = bool(page_ctx.get("has_more_page"))
                logger.info("Customers list page=%s got=%s has_more=%s", page, len(batch), has_more)

                if not has_more:
                    break

                page += 1
                if page > MAX_PAGES:
                    logger.warning("Reached MAX_PAGES=%s on customers -> break", MAX_PAGES)
                    hit_max_pages = True
                    break

                time.sleep(PAGE_DELAY)

            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching customers list (page={page}): {e}")
                status = "error"
                set_metrics(
                    "customers",
                    zoho_org_id=zoho_org_id,
                    last_run=now_iso(),
                    last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_customers") or "",
                    list_calls=list_calls,
                    detail_calls=0,
                    package_calls=0,
                    created=created,
                    updated=updated,
                    duration_sec=round(time.time() - t0, 3),
                    status=status,
                )
                return {"status": "error", "message": "Failed to fetch customers"}

    # Orden local (por seguridad) y filtro local por cutoff
    def _lm_dt_c(s: Dict[str, Any]) -> datetime:
        return _lm_customer_any(s) or datetime.min.replace(tzinfo=timezone.utc)

    items_list.sort(key=_lm_dt_c, reverse=True)  # ordenamos DESC localmente

    if cutoff_dt:
        def _lm_or_cutoff(x):
            return _lm_customer_any(x) or cutoff_dt
        items_list = [x for x in items_list if _lm_or_cutoff(x) >= cutoff_dt]

    # Upsert concurrente (sin detalle)
    customers_ids = [it.get("contact_id") for it in items_list if it.get("contact_id")]
    existing_customers = ZohoCustomer.objects(Q(contact_id__in=customers_ids))
    existing_ids = set(existing_customers.distinct("contact_id"))

    new_customers: List[ZohoCustomer] = []
    upd_customers: List[ZohoCustomer] = []

    def _process_customer(data_item: Dict[str, Any]):
        obj = create_books_customers_instance(logger, data_item, zoho_org_id)
        if not obj:
            return
        if obj.contact_id in existing_ids:
            upd_customers.append(obj)
        else:
            new_customers.append(obj)

    workers_customers = int(os.getenv("ZOHO_WORKERS_CUSTOMERS", "6"))
    if items_list:
        with ThreadPoolExecutor(max_workers=workers_customers) as ex:
            futures = [ex.submit(_process_customer, it) for it in items_list]
            for f in as_completed(futures):
                _ = f.result()

    if new_customers:
        ZohoCustomer.objects.insert(new_customers, load_bulk=False)
        created = len(new_customers)

    if upd_customers:
        for c in upd_customers:
            dst = ZohoCustomer.objects(contact_id=c.contact_id).first()
            if not dst:
                continue
            for f in c._fields:
                if f in ("id",):
                    continue
                setattr(dst, f, getattr(c, f))
            dst.save()
        updated = len(upd_customers)

    # Actualizar last_sync_date SOLO si no fue parcial por MAX_PAGES
    if not hit_max_pages and status == "ok":
        SyncMetadata.update_last_sync_date(
            "last_sync_date_customers",
            datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )

    duration = round(time.time() - t0, 3)
    final_status = "partial" if hit_max_pages else status

    set_metrics(
        "customers",
        zoho_org_id=zoho_org_id,
        last_run=now_iso(),
        last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_customers") or "",
        list_calls=list_calls,
        detail_calls=0,
        package_calls=0,
        created=created,
        updated=updated,
        duration_sec=duration,
        status=final_status,
    )

    logger.info(
        "Customers processed: %s created, %s updated (status=%s, hit_max_pages=%s)",
        created, updated, final_status, hit_max_pages
    )
    return {
        "status": final_status,
        "created": created,
        "updated": updated,
        "list_calls": list_calls,
        "detail_calls": 0,
        "package_calls": 0,
        "duration_sec": duration,
        "start_date": start_date,
        "zoho_org_id": zoho_org_id,
        "hit_max_pages": hit_max_pages,
        "cutoff": last_modified_time,
        "sort": {"column": sort_column, "order": sort_order},
        "order_detected": "DESC" if detected_desc else "ASC/unknown",
    }

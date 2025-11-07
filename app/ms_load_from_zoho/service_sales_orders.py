# =========================
# SALES ORDERS (robusto)
# =========================

from __future__ import annotations

import os
import time
import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from app.ms_util.utils import to_tz_iso8601
from mongoengine.queryset.visitor import Q

from ms_load_from_zoho import helpers
from ms_load_from_zoho.manage_instances import create_inventory_sales_order_instance
from ms_load_from_zoho.models import (
    AppConfig,
    SyncMetadata,
    ZohoInventoryShipmentSalesOrder,
)

# métricas (fallback no-op)
try:
    from ms_load_from_zoho.metrics import set_metrics as _set_metrics, now_iso as _now_iso
except Exception:  # pragma: no cover
    def _set_metrics(*args, **kwargs): ...
    def _now_iso():
        return datetime.now(timezone.utc).isoformat()

logger = logging.getLogger(__name__)

# ====== Config por ENV ======
LIST_PER_PAGE                 = int(os.getenv("ZOHO_LIST_PER_PAGE_SO", "200"))
LIST_TIMEOUT_SEC              = float(os.getenv("ZOHO_LIST_TIMEOUT_SEC_SO", "45"))
DETAIL_TIMEOUT_SEC            = float(os.getenv("ZOHO_DETAIL_TIMEOUT_SEC_SO", "12"))
ZOHO_LIST_PAGE_DELAY_SEC      = float(os.getenv("ZOHO_LIST_PAGE_DELAY_SEC_SO", "0.6"))

ZOHO_MAX_PAGES                = int(os.getenv("ZOHO_MAX_PAGES_SO", "100"))
ZOHO_MAX_DETAILS_PER_RUN_SO   = int(os.getenv("ZOHO_MAX_DETAILS_PER_RUN_SO", "150"))
ZOHO_MAX_RUN_SECONDS          = int(os.getenv("ZOHO_MAX_RUN_SECONDS_SO", "900"))  # debe coordinar con soft TL

ZOHO_DETAIL_THROTTLE_SEC      = float(os.getenv("ZOHO_DETAIL_THROTTLE_SEC_SO", "0.05"))
ZOHO_SORT_COLUMN              = os.getenv("ZOHO_SORT_COLUMN_SO", "last_modified_time")
ZOHO_SORT_ORDER               = os.getenv("ZOHO_SORT_ORDER_SO", "D")  # D=desc

MAX_WORKERS                   = int(os.getenv("ZOHO_SO_MAX_WORKERS", "2"))  # 1-2 seguro con rate limit

# ====== Utils ======
def _parse_zoho_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S"):
        try:
            dt_ = datetime.strptime(value, fmt)
            if dt_.tzinfo is None:
                dt_ = dt_.replace(tzinfo=timezone.utc)
            return dt_
        except Exception:
            continue
    return None

def _iso_zoho_midnight_utc(d: datetime) -> str:
    d_utc = d.astimezone(timezone.utc)
    at_midnight = datetime(d_utc.year, d_utc.month, d_utc.day, tzinfo=timezone.utc)
    return at_midnight.strftime("%Y-%m-%dT00:00:00+0000")

def _lm_any(it: Dict[str, Any]) -> Optional[datetime]:
    return (
        _parse_zoho_ts(it.get("last_modified_time"))
        or _parse_zoho_ts(it.get("updated_time"))
        or _parse_zoho_ts(it.get("created_time"))
    )

def _time_left_ok(start_t: float) -> bool:
    return (time.time() - start_t) < ZOHO_MAX_RUN_SECONDS

# ====== Fetch detail (thread-safe) ======
def fetch_sales_order_details(so_id: str, base_headers: Dict[str, str], zoho_org_id: str) -> Optional[Dict[str, Any]]:
    """Crea su propia Session y usa copia de headers para evitar race conditions."""
    if not so_id:
        return None
    url = f"{settings.ZOHO_INVENTORY_SALESORDERS_URL}/{so_id}"

    with helpers._retry_session() as s:
        headers = dict(base_headers)  # copia local
        try:
            resp = s.get(url, headers=headers, timeout=DETAIL_TIMEOUT_SEC)
            if resp.status_code == 401:
                # refresh solo afecta a esta copia de headers
                new_token = helpers.refresh_zoho_access_token(zoho_org_id)
                headers["Authorization"] = f"Zoho-oauthtoken {new_token}"
                resp = s.get(url, headers=headers, timeout=DETAIL_TIMEOUT_SEC)

            if resp.status_code == 429:
                # throttling mínimo y “fail-soft”: mejor saltar que bloquear
                logger.warning("429 detail salesorder_id=%s -> skip", so_id)
                return None

            resp.raise_for_status()
            if ZOHO_DETAIL_THROTTLE_SEC > 0:
                time.sleep(ZOHO_DETAIL_THROTTLE_SEC)
            return (resp.json() or {}).get("salesorder")

        except requests.exceptions.RequestException as e:
            logger.warning("Detail error salesorder_id=%s: %s", so_id, e)
            return None

# ====== Servicio principal ======
def load_sales_orders_service(start_date: Optional[str], zoho_org_id: str) -> Dict[str, Any]:
    t0 = time.time()
    list_calls = detail_calls = 0
    created = updated = 0
    status = "ok"
    hit_max_pages = False

    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    if not app_config:
        return {"status": "error", "message": f"AppConfig not found for zoho_org_id={zoho_org_id}"}

    # cutoff a medianoche UTC
    if not start_date:
        last_sync = SyncMetadata.get_last_sync_date("last_sync_date_salesorders")
        base = datetime.now(timezone.utc)
        if last_sync:
            try:
                base = datetime.strptime(last_sync, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except Exception:
                pass
        start_date = to_tz_iso8601(base)

    start_anchor = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    last_modified_time = to_tz_iso8601(start_anchor)
    cutoff_dt = _parse_zoho_ts(last_modified_time)

    # headers base
    try:
        base_headers = helpers.config_headers(zoho_org_id)
    except Exception as e:
        logger.error("Error connecting to Zoho API (headers): %s", e)
        _set_metrics(
            "salesorders",
            last_run=_now_iso(),
            zoho_org_id=zoho_org_id,
            last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_salesorders") or "",
            list_calls=list_calls, 
            detail_calls=detail_calls, 
            package_calls=0,
            created=created, 
            updated=updated, 
            duration_sec=round(time.time()-t0, 3),
            status="error",
        )
        return {"status": "error", "message": str(e)}

    # -------- Listado con corte temprano --------
    url = settings.ZOHO_INVENTORY_SALESORDERS_URL
    params = {
        "organization_id": app_config.zoho_org_id,
        "per_page": LIST_PER_PAGE,
        "page": 1,
        "last_modified_time": last_modified_time,
        "sort_column": ZOHO_SORT_COLUMN,
        "sort_order": ZOHO_SORT_ORDER,
    }

    items_list: List[Dict[str, Any]] = []
    page = 1
    with helpers._retry_session() as session:
        while True:
            if not _time_left_ok(t0):
                logger.warning("Budget time exhausted on listing -> breaking")
                break
            try:
                params["page"] = page
                resp = session.get(url, headers=base_headers, params=params, timeout=LIST_TIMEOUT_SEC)
                list_calls += 1

                if resp.status_code == 401:
                    new_token = helpers.refresh_zoho_access_token(zoho_org_id)
                    tmp_headers = dict(base_headers, Authorization=f"Zoho-oauthtoken {new_token}")
                    resp = session.get(url, headers=tmp_headers, params=params, timeout=LIST_TIMEOUT_SEC)
                    list_calls += 1
                if resp.status_code == 429:
                    logger.warning("429 list page=%s -> tiny backoff", page)
                    time.sleep(1.0)
                    continue

                resp.raise_for_status()
                payload = resp.json() if resp.content else {}
                batch = payload.get("salesorders", []) or []
                items_list.extend(batch)

                # corte temprano por LM
                if batch:
                    ts_vals = [ts for ts in (_lm_any(x) for x in batch) if ts]
                    first_lm = max(ts_vals) if ts_vals else None
                    last_lm  = min(ts_vals) if ts_vals else None
                    logger.info(
                        "SO page=%s got=%s lm_first=%s lm_last=%s cutoff=%s",
                        page, len(batch),
                        first_lm.isoformat() if first_lm else None,
                        last_lm.isoformat()  if last_lm  else None,
                        cutoff_dt.isoformat() if cutoff_dt else None
                    )
                    if last_lm and cutoff_dt and last_lm < cutoff_dt:
                        logger.info("Stopping paging: last_lm < cutoff (page=%s)", page)
                        break

                page_ctx = payload.get("page_context", {}) or {}
                has_more = bool(page_ctx.get("has_more_page"))
                if not has_more or page >= ZOHO_MAX_PAGES:
                    hit_max_pages = page >= ZOHO_MAX_PAGES and has_more
                    break

                page += 1
                time.sleep(ZOHO_LIST_PAGE_DELAY_SEC)

            except requests.exceptions.RequestException as e:
                logger.error("Error listing sales orders (page=%s): %s", page, e)
                status = "error"
                break

    # orden local por LM desc
    items_list.sort(key=lambda s: _lm_any(s) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    # -------- Decide quién necesita detalle + límites --------
    so_ids_list = [it.get("salesorder_id") for it in items_list if it.get("salesorder_id")]
    existing = ZohoInventoryShipmentSalesOrder.objects(Q(salesorder_id__in=so_ids_list))
    existing_map = {o.salesorder_id: _parse_zoho_ts(o.last_modified_time) for o in existing}

    def _needs_detail(list_item: Dict[str, Any]) -> bool:
        so_id = list_item.get("salesorder_id")
        if not so_id:
            return False
        listed_lm = _lm_any(list_item)
        if cutoff_dt and listed_lm and listed_lm < cutoff_dt:
            return False
        prev_lm = existing_map.get(so_id)
        if prev_lm is None:
            return True
        if listed_lm and prev_lm and listed_lm > prev_lm:
            return True
        return False

    candidates_all = [it for it in items_list if _needs_detail(it)]
    candidates = candidates_all[:ZOHO_MAX_DETAILS_PER_RUN_SO]
    omitted = max(0, len(candidates_all) - len(candidates))
    if omitted:
        logger.warning("SO detail candidates capped: %s omitted (limit=%s)", omitted, ZOHO_MAX_DETAILS_PER_RUN_SO)

    # -------- Detalles (thread-safe) --------
    full_items: List[Dict[str, Any]] = []
    if candidates and _time_left_ok(t0):
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futs = [ex.submit(fetch_sales_order_details, it.get("salesorder_id"), base_headers, zoho_org_id)
                    for it in candidates]
            for fut in as_completed(futs):
                if not _time_left_ok(t0):
                    logger.warning("Budget time exhausted during SO details -> breaking")
                    break
                r = fut.result()
                if r:
                    full_items.append(r)
        detail_calls = len(candidates)

    # -------- Persistencia --------
    exist_ids = set()
    if full_items:
        check_ids = [it.get("salesorder_id") for it in full_items if it.get("salesorder_id")]
        existing2 = ZohoInventoryShipmentSalesOrder.objects(Q(salesorder_id__in=check_ids))
        exist_ids = set(existing2.distinct("salesorder_id"))

    new_docs, upd_docs = [], []
    for data in full_items:
        doc = create_inventory_sales_order_instance(logger, data, zoho_org_id)
        if not doc:
            continue
        if doc.salesorder_id in exist_ids:
            upd_docs.append(doc)
        else:
            new_docs.append(doc)

    if new_docs:
        ZohoInventoryShipmentSalesOrder.objects.insert(new_docs, load_bulk=False)
        created = len(new_docs)

    if upd_docs:
        for d in upd_docs:
            obj = ZohoInventoryShipmentSalesOrder.objects(salesorder_id=d.salesorder_id).first()
            if obj:
                # copiar campos genéricamente
                for f in d._fields:
                    if f in ("id",):
                        continue
                    setattr(obj, f, getattr(d, f))
                obj.save()
        updated = len(upd_docs)

    # actualizar last_sync si no fue parcial por límites o páginas
    partial = omitted > 0 or not _time_left_ok(t0)
    if not (hit_max_pages or partial) and status == "ok":
        SyncMetadata.update_last_sync_date(
            "last_sync_date_salesorders",
            datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )

    duration = round(time.time() - t0, 3)
    final_status = "partial" if (hit_max_pages or partial or status != "ok") else "ok"
    _set_metrics(
        "salesorders",
        last_run=_now_iso(),
        zoho_org_id=zoho_org_id,
        last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_salesorders") or "",
        list_calls=list_calls, 
        detail_calls=detail_calls, 
        package_calls=0,
        created=created, 
        updated=updated, 
        duration_sec=duration, 
        status=final_status,
    )

    logger.info(
        "Sales Orders processed: created=%s updated=%s status=%s (hit_max_pages=%s partial=%s)",
        created, updated, final_status, hit_max_pages, partial
    )

    return {
        "status": final_status,
        "created": created,
        "updated": updated,
        "list_calls": list_calls,
        "detail_calls": detail_calls,
        "duration_sec": duration,
        "start_date": start_date,
        "zoho_org_id": zoho_org_id,
        "cutoff": last_modified_time,
        "limits": {
            "omitted_details": omitted,
            "max_details": ZOHO_MAX_DETAILS_PER_RUN_SO,
            "max_run_seconds": ZOHO_MAX_RUN_SECONDS,
        },
        "sort": {"column": ZOHO_SORT_COLUMN, "order": ZOHO_SORT_ORDER},
    }

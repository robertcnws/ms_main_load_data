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
    ZohoFullInvoice,
    ZohoInventoryShipmentSalesOrder,
    ZohoShipmentOrder,
    ZohoPackage
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
        "CUSTOMERS: org_id=%s start=%s last_modified_time=%s (cutoff=%s)",
        zoho_org_id, start_date, last_modified_time, cutoff_dt.isoformat() if cutoff_dt else None,
    )

    # Headers Zoho
    try:
        headers = helpers.config_headers(zoho_org_id)
    except Exception as e:
        logger.error("Error connecting to Zoho API (headers) for org_id=%s: %s", zoho_org_id, e)
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
                    logger.warning(f"429 on customers list page={page} for org_id={zoho_org_id} -> sleeping {wait_s}s")
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
                        "Customers org_id=%s page=%s got=%s lm_first=%s lm_last=%s cutoff=%s",
                        zoho_org_id, page, len(batch),
                        first_lm.isoformat() if first_lm else None,
                        last_lm.isoformat() if last_lm else None,
                        cutoff_dt.isoformat() if cutoff_dt else None
                    )

                    # Autodetectar si el batch viene ordenado DESC (nuevo->viejo)
                    if not order_detected and first_lm and last_lm:
                        detected_desc = first_lm > last_lm
                        order_detected = True
                        logger.info("Customers order detected for org_id=%s: %s", zoho_org_id, "DESC" if detected_desc else "ASC/unknown" )

                    # Early-stop SOLO si realmente está en DESC (o si el caller lo pidió y coincide)
                    if (detected_desc or sort_order == "D") and last_lm and cutoff_dt and last_lm < cutoff_dt:
                        logger.info("Stopping paging (customers) for org_id=%s: last_lm < cutoff (page=%s, DESC)", zoho_org_id, page)
                        break

                page_ctx = payload.get("page_context", {}) or {}
                has_more = bool(page_ctx.get("has_more_page"))
                logger.info("Customers list for org_id=%s page=%s got=%s has_more=%s", zoho_org_id, page, len(batch), has_more)

                if not has_more:
                    break

                page += 1
                if page > MAX_PAGES:
                    logger.warning("Reached MAX_PAGES=%s on customers for org_id=%s -> break", MAX_PAGES, zoho_org_id)
                    hit_max_pages = True
                    break

                time.sleep(PAGE_DELAY)

            except requests.exceptions.RequestException as e:
                logger.error("Error fetching customers list for org_id=%s (page=%s) : %s", zoho_org_id, page, e)
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
            # Update Related Invoices
            update_related_invoices(dst, zoho_org_id)
            # Update Related Sales Orders
            update_related_sales_orders(dst, zoho_org_id)
            # Update Related Shipments
            update_related_shipments(dst, zoho_org_id)
            # Update Related Packages
            update_related_packages(dst, zoho_org_id)
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
        "Customers processed for org_id=%s: %s created, %s updated (status=%s, hit_max_pages=%s)",
        zoho_org_id, created, updated, final_status, hit_max_pages
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

def update_related_invoices(dst: ZohoCustomer, zoho_org_id: str):
    logger.info("Updating related invoices for customer: %s for org_id=%s", dst.contact_id, zoho_org_id)
    invoices = ZohoFullInvoice.objects(customer_id=dst.contact_id)
    for inv in invoices:
        inv.customer_name = dst.customer_name if dst.customer_name else inv.customer_name
        inv.email = dst.email if dst.email else inv.email
        contact_details = list(inv.contact_persons_details)
        existing_contact = next((cd for cd in contact_details if cd.get("contact_id") == dst.contact_id), None)
        if existing_contact:
            new_contacts = [cd for cd in contact_details if cd.get("contact_id") != dst.contact_id]
            new_contacts.append({
                "first_name": dst.first_name if (dst.first_name and dst.first_name != existing_contact.get("first_name")) else existing_contact.get("first_name"),
                "last_name": dst.last_name if (dst.last_name and dst.last_name != existing_contact.get("last_name")) else existing_contact.get("last_name"),
                "email": dst.email if (dst.email and dst.email != existing_contact.get("email")) else existing_contact.get("email"),
                "phone": dst.phone if (dst.phone and dst.phone != existing_contact.get("phone")) else existing_contact.get("phone"),
                "mobile": dst.mobile if (dst.mobile and dst.mobile != existing_contact.get("mobile")) else existing_contact.get("mobile")
            })
            inv.contact_persons_details = new_contacts
        inv.save()
    logger.info("%s Invoices updated for customer: %s for org_id=%s", len(invoices), dst.contact_id, zoho_org_id)

def update_related_sales_orders(dst: ZohoCustomer, zoho_org_id: str):
    logger.info("Updating related sales orders for customer: %s for org_id=%s", dst.contact_id, zoho_org_id)
    sales_orders = ZohoInventoryShipmentSalesOrder.objects(customer_id=dst.contact_id)
    for so in sales_orders:
        so.customer_name = dst.customer_name if dst.customer_name else so.customer_name
        so.save()
    logger.info("%s Sales orders updated for customer: %s for org_id=%s", len(sales_orders), dst.contact_id, zoho_org_id)
    
def update_related_shipments(dst: ZohoCustomer, zoho_org_id: str):
    logger.info("Updating related shipments for customer: %s for org_id=%s", dst.contact_id, zoho_org_id)
    shipments = ZohoShipmentOrder.objects(customer_id=dst.contact_id)
    for shipment in shipments:
        shipment.customer_name = dst.customer_name if dst.customer_name else shipment.customer_name
        shipment.save()
    logger.info("%s Shipments updated for customer: %s for org_id=%s", len(shipments), dst.contact_id, zoho_org_id)

def update_related_packages(dst: ZohoCustomer, zoho_org_id: str):
    logger.info("Updating related packages for customer: %s for org_id=%s", dst.contact_id, zoho_org_id)
    packages = ZohoPackage.objects(customer_id=dst.contact_id)
    for package in packages:
        package.customer_name = dst.customer_name if dst.customer_name else package.customer_name
        package.email = dst.email if dst.email else package.email
        package.phone = dst.phone if dst.phone else package.phone
        package.mobile = dst.mobile if dst.mobile else package.mobile
        package.save()
    logger.info("%s Packages updated for customer: %s for org_id=%s", len(packages), dst.contact_id, zoho_org_id)
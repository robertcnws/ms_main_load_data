# ms_load_from_zoho/service_invoices.py

from concurrent.futures import ThreadPoolExecutor, as_completed
from mongoengine import Q
from datetime import datetime as dt, timedelta
from django.conf import settings
from django.http import JsonResponse
from ms_load_from_zoho.models import AppConfig, ZohoFullInvoice, SyncMetadata
from ms_load_from_zoho.manage_instances import create_books_invoice_instance
from ms_load_from_zoho.service_shipments import _now_iso, _set_metrics
import ms_load_from_zoho.helpers as helpers
import requests, time, os, logging, json

logger = logging.getLogger(__name__)

MAX_WORKERS = int(os.getenv("ZOHO_INVOICES_WORKERS", "4"))
LIST_PAGE_DELAY = float(os.getenv("ZOHO_LIST_PAGE_DELAY_SEC", "1"))

def _fmt_lm_zoho_books(d: dt) -> str:
    # Books acepta 'YYYY-MM-DD'
    return d.strftime("%Y-%m-%d")

def load_invoices_service(start_date: str, zoho_org_id: str):
    t0 = time.time()
    list_calls = detail_calls = 0
    created = updated = 0
    status = "ok"

    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    if not app_config:
        return JsonResponse({"error": f"AppConfig not found for org={zoho_org_id}"}, status=500)

    # headers con token
    try:
        headers = helpers.config_headers(zoho_org_id)
    except Exception as e:
        logger.error("Error connecting to Zoho API (headers): %s", e)
        status = "error"
        _set_metrics("invoices", last_run=_now_iso(),
                     last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_invoices") or "",
                     list_calls=list_calls, detail_calls=detail_calls, package_calls=0,
                     created=created, updated=updated,
                     duration_sec=round(time.time()-t0, 3), status=status)
        return JsonResponse({"error": f"Auth error: {e}"}, status=500)

    # ---- ventana temporal
    today = dt.today()
    base_str = start_date or today.strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    # base = dt.strptime(base_str, "%Y-%m-%d")
    # last_modified_time = _fmt_lm_zoho_books(base - timedelta(days=2))

    params = {
        "organization_id": app_config.zoho_org_id,
        "page": 1,
        "per_page": 200,
        "date_start": base_str,
        "date_end": today_str,
    }

    invoice_ids = []
    session = helpers._retry_session()

    # ---- LISTADO (acumular IDs primero)
    while True:
        try:
            resp = session.get(settings.ZOHO_BOOKS_INVOICES_URL,
                               headers=headers, params=params, timeout=180)
            list_calls += 1

            if resp.status_code == 401:
                headers["Authorization"] = f"Zoho-oauthtoken {helpers.refresh_zoho_access_token(zoho_org_id)}"
                resp = session.get(settings.ZOHO_BOOKS_INVOICES_URL,
                                   headers=headers, params=params, timeout=180)
                list_calls += 1

            if resp.status_code != 200:
                # log detallado del error de Zoho
                try:
                    err = resp.json()
                except Exception:
                    err = {"raw": resp.text}
                logger.error("Zoho Books list 400/err=%s status=%s", err, resp.status_code)
                status = "error"
                _set_metrics("invoices", last_run=_now_iso(),
                             last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_invoices") or "",
                             list_calls=list_calls, detail_calls=detail_calls, package_calls=0,
                             created=created, updated=updated,
                             duration_sec=round(time.time()-t0, 3), status=status)
                # Devuelve el mismo status que Zoho (p.ej. 400) para ver el problema arriba
                return JsonResponse({"error": "Failed to fetch invoices", "zoho": err},
                                    status=resp.status_code)

            payload = resp.json() if resp.content else {}
            invoices = payload.get("invoices", []) or []
            invoice_ids.extend([i.get("invoice_id") for i in invoices if i.get("invoice_id")])

            page_ctx = payload.get("page_context", {}) or {}
            if not page_ctx.get("has_more_page"):
                break

            params["page"] += 1
            time.sleep(LIST_PAGE_DELAY)

        except requests.exceptions.RequestException as e:
            logger.error("Network error fetching invoices list: %s", e)
            status = "error"
            _set_metrics("invoices", last_run=_now_iso(),
                         last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_invoices") or "",
                         list_calls=list_calls, detail_calls=detail_calls, package_calls=0,
                         created=created, updated=updated,
                         duration_sec=round(time.time()-t0, 3), status=status)
            return JsonResponse({"error": "Network error fetching invoices"}, status=500)

    # Si no hay nada que detallar, devuelve OK con métricas
    if not invoice_ids:
        duration = round(time.time()-t0, 3)
        _set_metrics("invoices", last_run=_now_iso(),
                     last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_invoices") or "",
                     list_calls=list_calls, detail_calls=detail_calls, package_calls=0,
                     created=created, updated=updated,
                     duration_sec=duration, status=status)
        return JsonResponse({"message": "Invoices loaded successfully (empty window)"}, status=200)

    # ---- DETALLES (fuera del while)
    def fetch_full_invoice(invoice_id: str) -> dict | None:
        get_url = f"{settings.ZOHO_BOOKS_INVOICES_URL}/{invoice_id}"
        try:
            r = session.get(get_url,
                            headers=headers,
                            params={"organization_id": app_config.zoho_org_id},
                            timeout=180)
            if r.status_code == 401:
                headers["Authorization"] = f"Zoho-oauthtoken {helpers.refresh_zoho_access_token(zoho_org_id)}"
                r = session.get(get_url,
                                headers=headers,
                                params={"organization_id": app_config.zoho_org_id},
                                timeout=180)
            if r.status_code != 200:
                return None
            return r.json().get("invoice")
        except requests.exceptions.RequestException:
            return None

    invoices_data = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(fetch_full_invoice, iid): iid for iid in invoice_ids}
        for f in as_completed(futs):
            inv = f.result()
            if inv:
                invoices_data.append(inv)
    detail_calls = len(invoice_ids)

    # ---- PERSISTENCIA
    invoices_ids = [it["invoice_id"] for it in invoices_data if it.get("invoice_id")]
    existing = ZohoFullInvoice.objects(Q(invoice_id__in=invoices_ids))
    existing_ids = set(existing.distinct("invoice_id"))

    new_invoices, to_update = [], []
    for data_item in invoices_data:
        new_inv = create_books_invoice_instance(logger, data_item, zoho_org_id)
        if not new_inv:
            continue
        if new_inv.invoice_id in existing_ids:
            to_update.append(new_inv)
        else:
            new_invoices.append(new_inv)

    if new_invoices:
        ZohoFullInvoice.objects.insert(new_invoices, load_bulk=False)
        created = len(new_invoices)

    if to_update:
        for inv in to_update:
            obj = ZohoFullInvoice.objects(invoice_id=inv.invoice_id).first()
            if not obj:
                continue
            # copia de campos (igual que ya tenías)
            for f in inv._fields:
                if f in ("id",):
                    continue
                setattr(obj, f, getattr(inv, f))
            obj.zoho_org_id = zoho_org_id
            obj.save()
        updated = len(to_update)

    # ---- MÉTRICAS + RETURN
    duration = round(time.time()-t0, 3)
    _set_metrics("invoices", last_run=_now_iso(),
                 last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_invoices") or "",
                 list_calls=list_calls, detail_calls=detail_calls, package_calls=0,
                 created=created, updated=updated,
                 duration_sec=duration, status=status)

    logger.info("Invoices processed: %s created, %s updated", created, updated)
    return JsonResponse({"message": "Invoices loaded successfully",
                         "created": created, "updated": updated}, status=200)

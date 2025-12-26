import os
from ms_util.utils import to_tz_iso8601
from ms_load_from_zoho.service_customers import load_customers_service
from ms_load_from_zoho.service_invoices import load_invoices_service
from ms_load_from_zoho.service_items import load_items_service
from ms_load_from_zoho.service_sales_orders import load_sales_orders_service
from ms_load_from_zoho.service_itemgroups import load_itemgroups_service
from ms_load_from_zoho.service_purchaseorders import load_purchaseorders_service
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from datetime import datetime, timedelta
from django.http import HttpRequest
from .models import AppConfig, SyncMetadata, IntegrationMetrics
from django.conf import settings
from ms_load_from_zoho.service_shipments import load_shipments_service
import json
import logging
logger = logging.getLogger(__name__)


def _mk_request(payload: dict) -> HttpRequest:
    request = HttpRequest()
    request.method = 'POST'
    request.content_type = 'application/json'
    request._body = json.dumps(payload or {}).encode('utf-8')
    return request


@shared_task(queue="zoho_catalog")
def task_load_inventory_items():
    logger.info("ZOHO: inventory items TASK START")
    apps = AppConfig.objects.all()
    # last_sync = SyncMetadata.get_last_sync_date('last_sync_date_items')
    # last_sync_date = datetime.strptime(last_sync, "%Y-%m-%d") if last_sync else None
    im_items = IntegrationMetrics.objects(module='items')

    now_date = datetime.now()
    days_before_now = now_date - timedelta(days=settings.TIMEDELTA_ZOHO_ITEMS)
    # days_before = (last_sync_date - timedelta(days=settings.TIMEDELTA_ZOHO_ITEMS)).strftime("%Y-%m-%d") \
    #             if last_sync_date else days_before_now
    for org in apps:
        try:
            last_sync_date = im_items.get(zoho_org_id=org.zoho_org_id).last_run_dt
            days_before = (
                last_sync_date - timedelta(days=settings.TIMEDELTA_ZOHO_ITEMS)
                if last_sync_date else days_before_now
            )
            days_before = to_tz_iso8601(days_before)
            logger.info("Items org=%s -> datetime=%s", org.zoho_org_id, days_before)
            res = load_items_service(start_date=days_before, zoho_org_id=org.zoho_org_id)
            logger.info("Items task org=%s -> %s", org, res)
        except Exception as e:
            logger.exception("Items task failed for org=%s: %s", org, e)

    return "Task Inventory Items Completed"


@shared_task(queue="zoho_catalog")
def task_load_inventory_itemgroups():
    logger.info("ZOHO: inventory itemgroups TASK START")
    apps = AppConfig.objects.all()
    last_sync = SyncMetadata.get_last_sync_date('last_sync_date_itemgroups')
    last_sync_date = datetime.strptime(last_sync, "%Y-%m-%d") if last_sync else None
    days_before = (last_sync_date - timedelta(days=settings.TIMEDELTA_ZOHO_ITEMS)).strftime("%Y-%m-%d") \
                if last_sync_date else None
    for org in apps:
        try:
            res = load_itemgroups_service(start_date=days_before, zoho_org_id=org.zoho_org_id)
            logger.info("Itemgroups task org=%s -> %s", org, res)
        except Exception as e:
            logger.exception("Itemgroups task failed for org=%s: %s", org, e)

    return "Task Inventory Itemgroups Completed"


@shared_task(queue="zoho_catalog")
def task_load_books_customers():
    logger.info("ZOHO: customers TASK START")
    apps = AppConfig.objects.all()
    last_sync = SyncMetadata.get_last_sync_date('last_sync_date_customers')
    last_sync_date = datetime.strptime(last_sync, "%Y-%m-%d") if last_sync else None
    now_date = datetime.now()
    days_before_now = (now_date - timedelta(days=settings.TIMEDELTA_ZOHO_CUSTOMERS)).strftime("%Y-%m-%d")
    days_before = (last_sync_date - timedelta(days=settings.TIMEDELTA_ZOHO_CUSTOMERS)).strftime("%Y-%m-%d") \
                if last_sync_date else days_before_now
    for org in apps:
        try:
            res = load_customers_service(start_date=days_before, zoho_org_id=org.zoho_org_id)
            logger.info("Customers task org=%s -> %s", org, res)
        except Exception as e:
            logger.exception("Customers task failed for org=%s: %s", org, e)

    return "Task Books Customers Completed"


_SO_HARD_TL  = int(os.getenv("CELERY_SO_HARD_TL", 900))   # hard time limit (seg)
_SO_SOFT_TL  = int(os.getenv("CELERY_SO_SOFT_TL", 840))   # soft time limit (seg)

@shared_task(
    queue="zoho_sales",
    autoretry_for=(SoftTimeLimitExceeded,),
    retry_backoff=True,      # backoff exponencial
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    time_limit=_SO_HARD_TL,
    soft_time_limit=_SO_SOFT_TL,
)
def task_load_inventory_sales_orders():
    logger.info("ZOHO: sales orders TASK START")

    try:
        apps = AppConfig.objects.all()

        # last_sync = SyncMetadata.get_last_sync_date('last_sync_date_salesorders')
        # last_sync_date = datetime.strptime(last_sync, "%Y-%m-%d") if last_sync else None

        im_sales_orders = IntegrationMetrics.objects(module='salesorders')

        now_date = datetime.now()
        
        # # Si hay last_sync, retrocede TIMEDELTA desde esa fecha; si no, desde hoy
        # days_before = (
        #     (last_sync_date - timedelta(days=settings.TIMEDELTA_ZOHO_SALES_ORDERS)).strftime("%Y-%m-%d")
        #     if last_sync_date else days_before_now
        # )

        bad_orgs = []

        for org in apps:
            try:
                last_sync_date = im_sales_orders.get(zoho_org_id=org.zoho_org_id).last_run_dt
                timedelta_diff = settings.TIMEDELTA_ZOHO_SALES_ORDERS if org.zoho_org_id == settings.ZOHO_ORG_ID else settings.TIMEDELTA_ZOHO_SALES_ORDERS_NWSHOMES
                days_before_now = now_date - timedelta(days=timedelta_diff)
                days_before = (
                    last_sync_date - timedelta(days=timedelta_diff)
                    if last_sync_date else days_before_now
                )
                days_before = to_tz_iso8601(days_before)
                logger.info("Sales Orders org=%s -> datetime=%s", org.zoho_org_id, days_before)
                res = load_sales_orders_service(start_date=days_before, zoho_org_id=org.zoho_org_id)
                status = res.get("status", "ok")
                logger.info(
                    "Sales Orders org=%s -> status=%s created=%s updated=%s list_calls=%s detail_calls=%s duration=%.2fs",
                    org.zoho_org_id, status, res.get("created"), res.get("updated"),
                    res.get("list_calls"), res.get("detail_calls"), res.get("duration_sec", 0.0),
                )
                if status in ("error", "partial"):
                    # No forzamos retry del task completo (puede haber varias orgs);
                    # solo marcamos y continuamos para no perder progreso.
                    bad_orgs.append((org.zoho_org_id, status))
            except SoftTimeLimitExceeded:
                # Deja que el decorador haga el autoretry
                logger.warning("ZOHO: sales orders soft timeout en org=%s -> autoretry", org.zoho_org_id)
                raise
            except Exception as e:
                logger.exception("Sales Orders task failed for org=%s: %s", org.zoho_org_id, e)
                bad_orgs.append((org.zoho_org_id, "error"))

        if bad_orgs:
            logger.warning("Sales Orders finalizó con incidencias en orgs: %s", bad_orgs)

        return "Task Inventory Sales Orders Completed"

    except SoftTimeLimitExceeded:
        # Propaga para que el decorador haga retry
        logger.warning("ZOHO: sales orders soft timeout (global) -> autoretry")
        raise
    except Exception as e:
        # No autoretry por defecto para otras excepciones globales; se registra y sale.
        logger.exception("ZOHO: sales orders task error (global): %s", e)
        return "Task Inventory Sales Orders Completed (with errors)"


@shared_task(
    queue="zoho_shipments",
    autoretry_for=(Exception,),
    retry_backoff=True,      # backoff exponencial
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
    time_limit=900,          # hard
    soft_time_limit=840,     # soft
)
def task_load_inventory_shipments():
    logger.info("ZOHO: shipments TASK START")

    try:
        apps = AppConfig.objects.all()
        last_sync = SyncMetadata.get_last_sync_date('last_sync_date_shipments')
        last_sync_date = datetime.strptime(last_sync, "%Y-%m-%d") if last_sync else None
        now_date = datetime.now()
        days_before_now = (now_date - timedelta(days=settings.TIMEDELTA_ZOHO_SHIPMENTS)).strftime("%Y-%m-%d")
        days_before = (last_sync_date - timedelta(days=settings.TIMEDELTA_ZOHO_SHIPMENTS)).strftime("%Y-%m-%d") \
                    if last_sync_date else days_before_now
        for app in apps:
            res = load_shipments_service(start_date=days_before, zoho_org_id=app.zoho_org_id)
            if res.get("status") != "ok":
                logger.warning("Shipments service returned error for org=%s: %s", app.zoho_org_id, res)

        return "Task Inventory Shipments Completed"

    except SoftTimeLimitExceeded as e:
        logger.warning("ZOHO: shipments soft timeout -> retrying (%s)", str(e))
        raise

    except Exception as e:
        logger.exception("ZOHO: shipments task error: %s", str(e))
        raise
    

@shared_task(queue="zoho_sales")
def task_load_books_invoices():
    logger.info("ZOHO: invoices TASK START")
    apps = AppConfig.objects.all()
    last_sync = SyncMetadata.get_last_sync_date("last_sync_date_invoices")
    last_sync_date = datetime.strptime(last_sync, "%Y-%m-%d") if last_sync else None
    now_date = datetime.now()
    days_before_now = (now_date - timedelta(days=settings.TIMEDELTA_ZOHO_INVOICES)).strftime("%Y-%m-%d")
    start_date = (last_sync_date - timedelta(days=settings.TIMEDELTA_ZOHO_INVOICES)).strftime("%Y-%m-%d") \
                 if last_sync_date else days_before_now

    for org in apps:
        try:
            res = load_invoices_service(start_date=start_date, zoho_org_id=org.zoho_org_id)
            try:
                logger.info("Invoices task org=%s -> <%s %s>", org, res.status_code, getattr(res, "content", b"")[:200])
            except Exception:
                logger.info("Invoices task org=%s -> %s", org, res)
        except Exception as e:
            logger.exception("Invoices task failed for org=%s: %s", org, e)

    return "Task Books Invoices Completed"


@shared_task(
    queue="zoho_purchases",
    autoretry_for=(SoftTimeLimitExceeded,),
    retry_backoff=True,      # backoff exponencial
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    time_limit=_SO_HARD_TL,
    soft_time_limit=_SO_SOFT_TL,
)
def task_load_inventory_purchaseorders():
    logger.info("ZOHO: purchase orders TASK START")

    try:
        apps = AppConfig.objects.all()

        now_date = datetime.now()
        days_before_now = now_date - timedelta(days=settings.TIMEDELTA_ZOHO_PURCHASE_ORDERS)

        bad_orgs = []

        for org in apps:
            try:
                saved_last_sync = IntegrationMetrics.objects(
                    module="purchaseorders",
                    zoho_org_id=org.zoho_org_id
                ).first()
                last_sync_date = saved_last_sync.last_run_dt if saved_last_sync else None
                days_before = (
                    last_sync_date - timedelta(days=settings.TIMEDELTA_ZOHO_PURCHASE_ORDERS)
                    if last_sync_date else days_before_now
                )
                days_before = to_tz_iso8601(days_before)
                logger.info("Purchase Orders org=%s -> datetime=%s", org.zoho_org_id, days_before)
                res = load_purchaseorders_service(start_date=days_before, zoho_org_id=org.zoho_org_id)
                status = res.get("status", "ok")
                logger.info(
                    "Purchase Orders org=%s -> status=%s created=%s updated=%s list_calls=%s detail_calls=%s duration=%.2fs",
                    org.zoho_org_id, status, res.get("created"), res.get("updated"),
                    res.get("list_calls"), res.get("detail_calls"), res.get("duration_sec", 0.0),
                )
                if status in ("error", "partial"):
                    bad_orgs.append((org.zoho_org_id, status))
            except SoftTimeLimitExceeded:
                logger.warning("ZOHO: purchase orders soft timeout en org=%s -> autoretry", org.zoho_org_id)
                raise
            except Exception as e:
                logger.exception("Purchase Orders task failed for org=%s: %s", org.zoho_org_id, e)
                bad_orgs.append((org.zoho_org_id, "error"))

        if bad_orgs:
            logger.warning("Purchase Orders finalizó con incidencias en orgs: %s", bad_orgs)
        return "Task Inventory Purchase Orders Completed"

    except SoftTimeLimitExceeded:
        logger.warning("ZOHO: purchase orders soft timeout (global) -> autoretry")
        raise
    except Exception as e:
        logger.exception("ZOHO: purchase orders task error (global): %s", e)
        return "Task Inventory Purchase Orders Completed (with errors)"
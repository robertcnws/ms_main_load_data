from ms_load_from_zoho.service_customers import load_customers_service
from ms_load_from_zoho.service_invoices import load_invoices_service
from ms_load_from_zoho.service_items import load_items_service
from ms_load_from_zoho.service_sales_orders import load_sales_orders_service
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from datetime import datetime, timedelta
from django.http import HttpRequest
from .models import AppConfig, SyncMetadata
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
    last_sync = SyncMetadata.get_last_sync_date('last_sync_date_items')
    last_sync_date = datetime.strptime(last_sync, "%Y-%m-%d") if last_sync else None
    now_date = datetime.now()
    days_before_now = (now_date - timedelta(days=settings.TIMEDELTA_ZOHO_ITEMS)).strftime("%Y-%m-%d")
    days_before = (last_sync_date - timedelta(days=settings.TIMEDELTA_ZOHO_ITEMS)).strftime("%Y-%m-%d") \
                if last_sync_date else days_before_now
    for org in apps:
        try:
            res = load_items_service(start_date=days_before, zoho_org_id=org.zoho_org_id)
            logger.info("Items task org=%s -> %s", org, res)
        except Exception as e:
            logger.exception("Items task failed for org=%s: %s", org, e)

    return "Task Inventory Items Completed"


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


@shared_task(queue="zoho_sales")
def task_load_inventory_sales_orders():
    logger.info("ZOHO: sales orders TASK START")
    apps = AppConfig.objects.all()
    last_sync = SyncMetadata.get_last_sync_date('last_sync_date_salesorders')
    last_sync_date = datetime.strptime(last_sync, "%Y-%m-%d") if last_sync else None
    now_date = datetime.now()
    days_before_now = (now_date - timedelta(days=settings.TIMEDELTA_ZOHO_SALES_ORDERS)).strftime("%Y-%m-%d")
    days_before = (last_sync_date - timedelta(days=settings.TIMEDELTA_ZOHO_SALES_ORDERS)).strftime("%Y-%m-%d") \
                if last_sync_date else days_before_now
    for org in apps:
        try:
            res = load_sales_orders_service(start_date=days_before, zoho_org_id=org.zoho_org_id)
            logger.info("Sales Orders task org=%s -> %s", org, res)
        except Exception as e:
            logger.exception("Sales Orders task failed for org=%s: %s", org, e)
    return "Task Inventory Sales Orders Completed"


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
    last_sync = SyncMetadata.get_last_sync_date('last_sync_date_invoices')
    last_sync_date = datetime.strptime(last_sync, "%Y-%m-%d") if last_sync else None
    now_date = datetime.now()
    days_before_now = (now_date - timedelta(days=settings.TIMEDELTA_ZOHO_INVOICES)).strftime("%Y-%m-%d")
    days_before = (last_sync_date - timedelta(days=settings.TIMEDELTA_ZOHO_INVOICES)).strftime("%Y-%m-%d") \
                if last_sync_date else days_before_now
    for org in apps:
        try:
            res = load_invoices_service(start_date=days_before, zoho_org_id=org.zoho_org_id)
            logger.info("Invoices task org=%s -> %s", org, res)
        except Exception as e:
            logger.exception("Invoices task failed for org=%s: %s", org, e)

    return "Task Books Invoices Completed"

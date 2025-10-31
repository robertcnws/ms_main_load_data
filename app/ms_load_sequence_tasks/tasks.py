# sequences.py
from celery import shared_task
from django.conf import settings
from ms_load_from_zoho.tasks import (
    task_load_inventory_items,
    task_load_inventory_sales_orders,
    task_load_inventory_shipments,
    task_load_books_customers,
    task_load_books_invoices,
)
from ms_load_from_senitron.tasks import (
    task_load_senitron_items_assets,
    task_load_senitron_items_assets_logs,
)
import time
import logging
logger = logging.getLogger(__name__)

@shared_task(queue="zoho_shipments")
def tiny_sleep_zoho_shipments(seconds=5):
    time.sleep(seconds)
    return "slept in ZOHO SHIPMENTS (SHIPMENT ORDERS)"

@shared_task(queue="zoho_sales")
def tiny_sleep_zoho_sales(seconds=5):
    time.sleep(seconds)
    return "slept in ZOHO SALES (SALES ORDERS, INVOICES)"

@shared_task(queue="zoho_catalog")
def tiny_sleep_zoho_catalog(seconds=5):
    time.sleep(seconds)
    return "slept in ZOHO CATALOG (CUSTOMERS, ITEMS)"

@shared_task(queue="senitron")
def tiny_sleep_senitron(seconds=5):
    time.sleep(seconds)
    return "slept in SENITRON"


@shared_task(queue="zoho_shipments")
def task_sequence_by_zoho_shipments():
    logger.info("Starting ZOHO shipments chain: -> shipments ")
    s1 = task_load_inventory_shipments.si().set(queue="zoho_shipments")
    pause = tiny_sleep_zoho_shipments.si(2).set(queue="zoho_shipments")
    ar = (s1 | pause).apply_async()
    logger.info("Chain zoho shipments started: id=%s root_id=%s", ar.id, getattr(ar, "parent", None))


@shared_task(queue="zoho_sales")
def task_sequence_by_zoho_sales():
    logger.info("Starting ZOHO sales chain: sales_orders -> invoices ")
    s1 = task_load_inventory_sales_orders.si().set(queue="zoho_sales")
    pause1 = tiny_sleep_zoho_sales.si(2).set(queue="zoho_sales")
    s2 = task_load_books_invoices.si().set(queue="zoho_sales")
    pause2 = tiny_sleep_zoho_sales.si(2).set(queue="zoho_sales")
    ar = (s1 | pause1 | s2 | pause2).apply_async()
    logger.info("Chain zoho sales/invoices started: id=%s root_id=%s", ar.id, getattr(ar, "parent", None))


@shared_task(queue="zoho_catalog")
def task_sequence_by_zoho_customers_items():
    logger.info("Starting ZOHO customers/items chain: customers -> items")
    s1 = task_load_books_customers.si().set(queue="zoho_catalog")
    pause1 = tiny_sleep_zoho_catalog.si(2).set(queue="zoho_catalog")
    s2 = task_load_inventory_items.si().set(queue="zoho_catalog")
    pause2 = tiny_sleep_zoho_catalog.si(2).set(queue="zoho_catalog")
    ar = (s1 | pause1 | s2 | pause2).apply_async()
    logger.info("Chain zoho customers/items started: id=%s root_id=%s", ar.id, getattr(ar, "parent", None))


@shared_task(queue="senitron")
def task_sequence_by_senitron():
    logger.info("Starting SENITRON chain: assets -> logs")
    a = task_load_senitron_items_assets.si().set(queue="senitron")
    pause = tiny_sleep_senitron.si(1).set(queue="senitron")
    b = task_load_senitron_items_assets_logs.si().set(queue="senitron")
    ar = (a | pause | b).apply_async()
    logger.info("Chain senitron started: id=%s root_id=%s", ar.id, getattr(ar, "parent", None))

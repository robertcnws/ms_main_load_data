# sequences.py
from celery import shared_task
from django.conf import settings
from ms_load_from_zoho.tasks import (
    task_load_inventory_itemgroups,
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
def tiny_sleep_zoho_shipments(seconds=5, after=None):
    time.sleep(seconds)
    return f"slept in ZOHO SHIPMENTS worker (SHIPMENT ORDERS) after {after}"

@shared_task(queue="zoho_sales")
def tiny_sleep_zoho_sales(seconds=5, after=None):
    time.sleep(seconds)
    return f"slept in ZOHO SALES worker (SALES ORDERS, INVOICES) after {after}"

@shared_task(queue="zoho_catalog")
def tiny_sleep_zoho_catalog(seconds=5, after=None):
    time.sleep(seconds)
    return f"slept in ZOHO CATALOG worker (CUSTOMERS, ITEMS, ITEMGROUPS) after {after}"

@shared_task(queue="senitron")
def tiny_sleep_senitron(seconds=5, after=None):
    time.sleep(seconds)
    return f"slept in SENITRON worker after {after}"


@shared_task(queue="zoho_shipments")
def task_sequence_by_zoho_shipments():
    logger.info("Starting ZOHO shipments chain: -> shipments ")
    s1 = task_load_inventory_shipments.si().set(queue="zoho_shipments")
    pause = tiny_sleep_zoho_shipments.si(2, after='shipments load').set(queue="zoho_shipments")
    ar = (s1 | pause).apply_async()
    logger.info("Chain zoho shipments started: id=%s root_id=%s", ar.id, getattr(ar, "parent", None))


@shared_task(queue="zoho_sales")
def task_sequence_by_zoho_sales():
    logger.info("Starting ZOHO sales chain: sales_orders -> invoices ")
    s1 = task_load_inventory_sales_orders.si().set(queue="zoho_sales")
    pause1 = tiny_sleep_zoho_sales.si(2, after='sales orders load').set(queue="zoho_sales")
    s2 = task_load_books_invoices.si().set(queue="zoho_sales")
    pause2 = tiny_sleep_zoho_sales.si(2, after='invoices load').set(queue="zoho_sales")
    ar = (s1 | pause1 | s2 | pause2).apply_async()
    logger.info("Chain zoho sales/invoices started: id=%s root_id=%s", ar.id, getattr(ar, "parent", None))


@shared_task(queue="zoho_catalog")
def task_sequence_by_zoho_customers_items():
    logger.info("Starting ZOHO customers/items chain: customers -> items -> itemgroups")
    s1 = task_load_books_customers.si().set(queue="zoho_catalog")
    pause1 = tiny_sleep_zoho_catalog.si(2, after='customers load').set(queue="zoho_catalog")
    s2 = task_load_inventory_items.si().set(queue="zoho_catalog")
    pause2 = tiny_sleep_zoho_catalog.si(2, after='items load').set(queue="zoho_catalog")
    s3 = task_load_inventory_itemgroups.si().set(queue="zoho_catalog")
    pause3 = tiny_sleep_zoho_catalog.si(2, after='itemgroups load').set(queue="zoho_catalog")
    ar = (s1 | pause1 | s2 | pause2 | s3 | pause3).apply_async()
    logger.info("Chain zoho customers/items/itemgroups started: id=%s root_id=%s", ar.id, getattr(ar, "parent", None))


@shared_task(queue="senitron")
def task_sequence_by_senitron():
    logger.info("Starting SENITRON chain: assets -> logs")
    a = task_load_senitron_items_assets.si().set(queue="senitron")
    pause = tiny_sleep_senitron.si(2, after='assets load').set(queue="senitron")
    b = task_load_senitron_items_assets_logs.si().set(queue="senitron")
    pause2 = tiny_sleep_senitron.si(2, after='assets logs load').set(queue="senitron")
    ar = (a | pause | b | pause2).apply_async()
    logger.info("Chain senitron started: id=%s root_id=%s", ar.id, getattr(ar, "parent", None))

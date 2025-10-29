# sequences.py (o donde defines estas cadenas)
from celery import shared_task, chain
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
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

ZOHO_STEP_DELAY = getattr(settings, "ZOHO_STEP_DELAY", 1)  # segundos entre pasos

@shared_task
def task_sequence_by_zoho_sales():
    logger.info(
        "Running task_sequence_by_zoho_sales on MON-SAT: %s past every %s h; SUN: %s past every %s h",
        settings.MINUTE_ZOHO_SALES_MONDAY_TO_SATURDAY,
        settings.HOUR_ZOHO_SALES_MONDAY_TO_SATURDAY,
        settings.MINUTE_ZOHO_SALES_SUNDAY,
        settings.HOUR_ZOHO_SALES_SUNDAY,
    )

    # OPCIONAL: orden recomendado: sales_orders -> shipments -> invoices
    workflow = chain(
        task_load_inventory_sales_orders.si().set(queue="zoho"),
        task_load_inventory_shipments.si().set(queue="zoho", countdown=ZOHO_STEP_DELAY),
        task_load_books_invoices.si().set(queue="zoho", countdown=ZOHO_STEP_DELAY),
    )
    workflow.apply_async()


@shared_task
def task_sequence_by_customers_items():
    logger.info(
        "Running task_sequence_by_hours_customers_items on MON-SAT: %s past every %s h; SUN: %s past every %s h",
        settings.MINUTE_ZOHO_CUSTOMERS_ITEMS_MONDAY_TO_SATURDAY,
        settings.HOUR_ZOHO_CUSTOMERS_ITEMS_MONDAY_TO_SATURDAY,
        settings.MINUTE_ZOHO_CUSTOMERS_ITEMS_SUNDAY,
        settings.HOUR_ZOHO_CUSTOMERS_ITEMS_SUNDAY,
    )

    workflow = chain(
        task_load_books_customers.si().set(queue="zoho"),
        task_load_inventory_items.si().set(queue="zoho", countdown=ZOHO_STEP_DELAY),
    )
    workflow.apply_async()


@shared_task
def task_sequence_by_senitron():
    logger.info(
        "Running task_sequence_by_minutes_senitron on MON-SAT: %s past every %s h; SUN: %s past every %s h",
        settings.MINUTE_SENITRON_MONDAY_TO_SATURDAY,
        settings.HOUR_SENITRON_MONDAY_TO_SATURDAY,
        settings.MINUTE_SENITRON_SUNDAY,
        settings.HOUR_SENITRON_SUNDAY,
    )

    workflow = chain(
        task_load_senitron_items_assets.si().set(queue="senitron"),
        task_load_senitron_items_assets_logs.si().set(queue="senitron", countdown=1),
    )
    workflow.apply_async()

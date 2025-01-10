from celery import shared_task, chain
from django.conf import settings
from ms_load_from_zoho.tasks import (
    task_load_inventory_items,
    task_load_inventory_sales_orders,
    task_load_inventory_shipments,
    task_load_books_customers,
    # task_load_books_customers_details,
    task_load_books_invoices,
)
from ms_load_from_senitron.tasks import (
    task_load_senitron_items_assets,
    task_load_senitron_items_assets_logs,
)

import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@shared_task
def task_sequence_by_zoho_sales():
    
    logger.info(f'Running task_sequence_by_zoho_sales on MONDAY_TO_SATURDAY: \
                {settings.MINUTE_ZOHO_SALES_MONDAY_TO_SATURDAY} minutes past every \
                {settings.HOUR_ZOHO_SALES_MONDAY_TO_SATURDAY} hours')
    logger.info(f'Running task_sequence_by_zoho_sales on SUNDAY: \
                {settings.MINUTE_ZOHO_SALES_SUNDAY} minutes past every \
                {settings.HOUR_ZOHO_SALES_SUNDAY} hours')
    
    workflow = chain(
        task_load_inventory_shipments.si(),
        task_load_inventory_sales_orders.si().set(countdown=settings.CELERY_TASKS_DELAY),
        task_load_books_invoices.si().set(countdown=settings.CELERY_TASKS_DELAY),
    )
    workflow.apply_async()
    

@shared_task
def task_sequence_by_customers_items():
    
    logger.info(f'Running task_sequence_by_hours_customers_items on MONDAY_TO_SATURDAY: \
                {settings.MINUTE_ZOHO_CUSTOMERS_ITEMS_MONDAY_TO_SATURDAY} minutes past every \
                {settings.HOUR_ZOHO_CUSTOMERS_ITEMS_MONDAY_TO_SATURDAY} hours')
    logger.info(f'Running task_sequence_by_hours_customers_items on SUNDAY: \
                {settings.MINUTE_ZOHO_CUSTOMERS_ITEMS_SUNDAY} minutes past every \
                {settings.HOUR_ZOHO_CUSTOMERS_ITEMS_SUNDAY} hours')
    
    workflow = chain(
        task_load_books_customers.si(),
        task_load_inventory_items.si().set(countdown=settings.CELERY_TASKS_DELAY),
        # task_load_books_customers_details.si().set(countdown=settings.CELERY_TASKS_DELAY),
    )
    workflow.apply_async()
    

@shared_task
def task_sequence_by_senitron():
    
    logger.info(f'Running task_sequence_by_minutes_senitron on MONDAY_TO_SATURDAY: \
                {settings.MINUTE_SENITRON_MONDAY_TO_SATURDAY} minutes past every \
                {settings.HOUR_SENITRON_MONDAY_TO_SATURDAY} hours')
    logger.info(f'Running task_sequence_by_minutes_senitron on SUNDAY: \
                {settings.MINUTE_SENITRON_SUNDAY} minutes past every \
                {settings.HOUR_SENITRON_SUNDAY} hours')
    
    workflow = chain(
        task_load_senitron_items_assets.si(),
        task_load_senitron_items_assets_logs.si().set(countdown=settings.CELERY_TASKS_DELAY),
    )
    workflow.apply_async()
    


    


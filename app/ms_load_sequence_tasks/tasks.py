from celery import shared_task, chain
from ms_load_from_zoho.tasks import (
    task_load_inventory_items,
    task_load_inventory_sales_orders,
    task_load_inventory_shipments,
    task_load_books_customers
)

@shared_task
def task_sequence_30_min():
    workflow = chain(
        task_load_inventory_items.si(),
        task_load_books_customers.si(),
        task_load_inventory_shipments.si(),
        task_load_inventory_sales_orders.si()
    )
    workflow.apply_async()

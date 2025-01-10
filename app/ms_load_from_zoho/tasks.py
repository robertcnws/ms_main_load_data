from celery import shared_task
from datetime import datetime
from django.http import HttpRequest
from django.utils import timezone
from .views import (
                    load_inventory_items,
                    load_inventory_sales_orders,
                    load_inventory_shipments,
                    load_books_customers,
                    load_books_customers_details,
                    load_books_invoices,
                   )
import json
    
@shared_task
def task_load_inventory_items():
    request = HttpRequest()
    request.method = 'POST'
    request.content_type = 'application/json'
    request._body = json.dumps({}).encode('utf-8')
    load_inventory_items(request)
    
@shared_task
def task_load_books_customers():
    request = HttpRequest()
    request.method = 'POST'
    request.content_type = 'application/json'
    request._body = json.dumps({}).encode('utf-8')
    load_books_customers(request)


@shared_task
def task_load_inventory_sales_orders():
    start_date = datetime.now().strftime("%Y-%m-%d")
    data = {'start_date': start_date}
    request = HttpRequest()
    request.method = 'POST'
    request.content_type = 'application/json'
    request._body = json.dumps(data).encode('utf-8')
    load_inventory_sales_orders(request)
    
@shared_task
def task_load_inventory_shipments():
    start_date = datetime.now().strftime("%Y-%m-%d")
    data = {'start_date': start_date}
    request = HttpRequest()
    request.method = 'POST'
    request.content_type = 'application/json'
    request._body = json.dumps(data).encode('utf-8')
    load_inventory_shipments(request)
    
    
@shared_task
def task_load_books_invoices():
    start_date = datetime.now().strftime("%Y-%m-%d")
    data = {'start_date': start_date}
    request = HttpRequest()
    request.method = 'POST'
    request.content_type = 'application/json'
    request._body = json.dumps(data).encode('utf-8')
    load_books_invoices(request)
    
# @shared_task
# def task_load_books_customers_details():
#     load_books_customers_details()
    

from celery import shared_task
from datetime import datetime
from django.http import HttpRequest
from .models import AppConfig, SyncMetadata
from .views import (
    load_inventory_items,
    load_inventory_sales_orders,
    load_inventory_shipments,
    load_books_customers,
    load_books_invoices,
)
import json


def _mk_request(payload: dict) -> HttpRequest:
    request = HttpRequest()
    request.method = 'POST'
    request.content_type = 'application/json'
    request._body = json.dumps(payload or {}).encode('utf-8')
    return request


@shared_task
def task_load_inventory_items():
    request = _mk_request({})
    apps = AppConfig.objects.all()
    for app in apps:
        load_inventory_items(request, app.zoho_org_id)


@shared_task
def task_load_books_customers():
    request = _mk_request({})
    apps = AppConfig.objects.all()
    for app in apps:
        load_books_customers(request, app.zoho_org_id)


@shared_task
def task_load_inventory_sales_orders():
    apps = AppConfig.objects.all()
    for app in apps:
        last_sync = SyncMetadata.get_last_sync_date('last_sync_date_salesorders')
        start_date = last_sync or datetime.now().strftime("%Y-%m-%d")
        resp = load_inventory_sales_orders(_mk_request({'start_date': start_date}), app.zoho_org_id)
        if getattr(resp, 'status_code', 500) == 200:
            SyncMetadata.update_last_sync_date('last_sync_date_salesorders', datetime.now().strftime("%Y-%m-%d"))


@shared_task
def task_load_inventory_shipments():
    apps = AppConfig.objects.all()
    for app in apps:
        last_sync = SyncMetadata.get_last_sync_date('last_sync_date_shipments')
        start_date = last_sync or datetime.now().strftime("%Y-%m-%d")
        resp = load_inventory_shipments(_mk_request({'start_date': start_date}), app.zoho_org_id)
        if getattr(resp, 'status_code', 500) == 200:
            SyncMetadata.update_last_sync_date('last_sync_date_shipments', datetime.now().strftime("%Y-%m-%d"))


@shared_task
def task_load_books_invoices():
    apps = AppConfig.objects.all()
    for app in apps:
        last_sync = SyncMetadata.get_last_sync_date('last_sync_date_invoices')
        start_date = last_sync or datetime.now().strftime("%Y-%m-%d")
        resp = load_books_invoices(_mk_request({'start_date': start_date}), app.zoho_org_id)
        if getattr(resp, 'status_code', 500) == 200:
            SyncMetadata.update_last_sync_date('last_sync_date_invoices', datetime.now().strftime("%Y-%m-%d"))

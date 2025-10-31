# =========================
# SALES ORDERS (optimizado)
# =========================

from concurrent.futures import ThreadPoolExecutor, as_completed
from mongoengine import Q
import json
import os
import time
from datetime import datetime, timedelta
from django.conf import settings
from ms_load_from_zoho import helpers
import logging
from django.http import JsonResponse
import requests

from ms_load_from_zoho.manage_instances import create_inventory_sales_order_instance
from ms_load_from_zoho.models import AppConfig, SyncMetadata, ZohoInventoryShipmentSalesOrder
from ms_load_from_zoho.service_shipments import _now_iso, _parse_zoho_ts, _set_metrics

logger = logging.getLogger(__name__)

def fetch_sales_order_details(item, session, headers, zoho_org_id):
    try:
        url = f'{settings.ZOHO_INVENTORY_SALESORDERS_URL}/{item["salesorder_id"]}'
        resp = session.get(url, headers=headers, params={})
        if resp.status_code == 401:
            new_token = helpers.refresh_zoho_access_token(zoho_org_id)
            headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
            resp = session.get(url, headers=headers, params={})
        resp.raise_for_status()
        return resp.json().get('salesorder')
    except Exception as e:
        logger.error(f"Error fetching details for sales order {item['salesorder_id']}: {e}")
        return None

def load_sales_orders_service(start_date, zoho_org_id):
    t0 = time.time()
    list_calls = detail_calls = 0
    created = updated = 0
    status = 'ok'

    MAX_WORKERS = 2
    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    try:
        headers = helpers.config_headers(zoho_org_id)
    except Exception as e:
        logger.error(f"Error connecting to Zoho API: {str(e)}")
        status = 'error'
        _set_metrics('salesorders',
            last_run=_now_iso(),
            last_sync_date=SyncMetadata.get_last_sync_date('last_sync_date_salesorders') or '',
            list_calls=list_calls, detail_calls=detail_calls, package_calls=0,
            created=created, updated=updated, duration_sec=round(time.time()-t0,3),
            status=status)
        return JsonResponse({'error': f"Error connecting to Zoho API (Load Items): {str(e)}"}, status=500)
    
    if not start_date:
        return JsonResponse({'error': 'Start date is required'}, status=400)
    
    start_date = datetime.strptime(start_date, '%Y-%m-%d')
    last_modified_time = start_date.strftime('%Y-%m-%d') + 'T00:00:00+0000'

    params = {
        'organization_id': app_config.zoho_org_id,
        'per_page': 200, 'page': 1,
        'last_modified_time': last_modified_time,
    }

    url = settings.ZOHO_INVENTORY_SALESORDERS_URL
    items_to_get = []
    session = helpers._retry_session()

    while True:
        try:
            resp = session.get(url, headers=headers, params=params)
            list_calls += 1
            if resp.status_code == 401:
                new_token = helpers.refresh_zoho_access_token(zoho_org_id)
                headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                resp = session.get(url, headers=headers, params=params)
                list_calls += 1
            resp.raise_for_status()
            payload = resp.json()
            items_to_get.extend(payload.get('salesorders', []) or [])
            if not payload.get('page_context', {}).get('has_more_page', False):
                break
            params['page'] += 1
            time.sleep(float(os.getenv("ZOHO_LIST_PAGE_DELAY_SEC", "1")))
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching sales orders: {e}")
            status = 'error'
            _set_metrics('salesorders',
                last_run=_now_iso(),
                last_sync_date=SyncMetadata.get_last_sync_date('last_sync_date_salesorders') or '',
                list_calls=list_calls, detail_calls=detail_calls, package_calls=0,
                created=created, updated=updated, duration_sec=round(time.time()-t0,3),
                status=status)
            return JsonResponse({'error': 'Failed to fetch sales orders'}, status=500)

    salesorder_ids_list = [it.get('salesorder_id') for it in items_to_get if it.get('salesorder_id')]
    existing_orders = ZohoInventoryShipmentSalesOrder.objects(Q(salesorder_id__in=salesorder_ids_list))
    existing_map = {o.salesorder_id: _parse_zoho_ts(o.last_modified_time) for o in existing_orders}

    def _needs_detail(list_item):
        so_id = list_item.get('salesorder_id')
        if not so_id: return False
        listed_lm = _parse_zoho_ts(list_item.get('last_modified_time'))
        prev_lm = existing_map.get(so_id)
        if prev_lm is None: return True
        if listed_lm and prev_lm and listed_lm > prev_lm: return True
        return False

    detail_candidates = [it for it in items_to_get if _needs_detail(it)]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_sales_order_details, it, session, headers, zoho_org_id)
                   for it in detail_candidates]
        full_items_to_get = []
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                full_items_to_get.append(r)
        # número de llamadas de detalle intentadas (aprox. = candidatas)
        detail_calls = len(detail_candidates)

    salesorder_ids = [it['salesorder_id'] for it in full_items_to_get]
    existing_orders2 = ZohoInventoryShipmentSalesOrder.objects(Q(salesorder_id__in=salesorder_ids))
    existing_ids = set(existing_orders2.distinct('salesorder_id'))

    new_sales_orders, sales_orders_to_update = [], []
    for data_it in full_items_to_get:
        new_item = create_inventory_sales_order_instance(logger, data_it, zoho_org_id)
        if new_item and new_item.salesorder_id in existing_ids:
            sales_orders_to_update.append(new_item)
        elif new_item:
            new_sales_orders.append(new_item)

    if new_sales_orders:
        ZohoInventoryShipmentSalesOrder.objects.insert(new_sales_orders, load_bulk=False)
        created = len(new_sales_orders)
    if sales_orders_to_update:
        for u in sales_orders_to_update:
            db = ZohoInventoryShipmentSalesOrder.objects(salesorder_id=u.salesorder_id).first()
            if db:
                db.salesorder_number = u.salesorder_number
                db.date = u.date
                db.status = u.status
                db.customer_id = u.customer_id
                db.customer_name = u.customer_name
                db.is_taxable = u.is_taxable
                db.tax_id = u.tax_id
                db.tax_name = u.tax_name
                db.tax_percentage = u.tax_percentage
                db.currency_id = u.currency_id
                db.currency_code = u.currency_code
                db.currency_symbol = u.currency_symbol
                db.exchange_rate = u.exchange_rate
                db.delivery_method = u.delivery_method
                db.total_quantity = u.total_quantity
                db.sub_total = u.sub_total
                db.tax_total = u.tax_total
                db.total = u.total
                db.created_by_email = u.created_by_email
                db.created_by_name = u.created_by_name
                db.salesperson_id = u.salesperson_id
                db.salesperson_name = u.salesperson_name
                db.is_test_order = u.is_test_order
                db.notes = u.notes
                db.payment_terms = u.payment_terms
                db.payment_terms_label = u.payment_terms_label
                db.line_items = u.line_items
                db.shipping_address = u.shipping_address
                db.billing_address = u.billing_address
                db.warehouses = u.warehouses
                db.custom_fields = u.custom_fields
                db.order_sub_statuses = u.order_sub_statuses
                db.shipment_sub_statuses = u.shipment_sub_statuses
                db.created_time = u.created_time
                db.last_modified_time = u.last_modified_time
                db.zoho_org_id = zoho_org_id
                db.save()
        updated = len(sales_orders_to_update)

    duration = round(time.time()-t0, 3)
    _set_metrics('salesorders',
        last_run=_now_iso(),
        last_sync_date=SyncMetadata.get_last_sync_date('last_sync_date_salesorders') or '',
        list_calls=list_calls, detail_calls=detail_calls, package_calls=0,
        created=created, updated=updated,
        duration_sec=duration, status=status)

    logger.info(f"Sales Orders processed successfully: {created} created, {updated} updated")
    return JsonResponse({'message': 'Sales Orders loaded successfully'}, status=200)
from concurrent.futures import ThreadPoolExecutor, as_completed
from mongoengine import Q
from datetime import datetime as dt, timezone as tz, timedelta
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.contrib.auth.decorators import login_required
from threading import Semaphore, Lock
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from .models import (
                      AppConfig,
                      ZohoInventoryItem, 
                      TimelineItem,
                      ZohoInventoryShipmentSalesOrder,
                      ZohoShipmentOrder,
                      ZohoPackage, 
                      ZohoCustomer,
                      ZohoFullInvoice,
                      SyncMetadata,
                    )

from .manage_instances import (
                                create_inventory_item_instance,
                                create_inventory_sales_order_instance,
                                create_inventory_package_instance,
                                create_inventory_shipment_instance,
                                create_books_customers_instance,
                                create_books_invoice_instance,
                             )
import json
import requests
import logging
import time
import ms_load_from_zoho.helpers as helpers


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# =========================
# MÉTRICAS EN MEMORIA
# =========================
METRICS = {
    # Ejemplo de estructura por módulo:
    # 'salesorders': {
    #   'last_run': '2025-10-29T12:34:56Z',
    #   'last_sync_date': '2025-10-29',
    #   'list_calls': 0, 'detail_calls': 0, 'package_calls': 0,
    #   'created': 0, 'updated': 0,
    #   'duration_sec': 0.0, 'status': 'ok'|'error'
    # }
}

def _now_iso():
    return dt.now(tz.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def _parse_zoho_ts(s: str):
    if not s:
        return None
    try:
        return dt.strptime(s, '%Y-%m-%dT%H:%M:%S%z')
    except Exception:
        return None

def _set_metrics(mod, **kwargs):
    entry = METRICS.get(mod, {})
    entry.update(kwargs)
    METRICS[mod] = entry

# =========================
# AUTH / SETTINGS (igual)
# =========================

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def generate_auth_url(request, zoho_org_id):
    return helpers.generate_auth_url(zoho_org_id)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def get_refresh_token(request, zoho_org_id):
    return helpers.get_refresh_token(request, zoho_org_id)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def zoho_api_settings(request, zoho_org_id):
    return helpers.zoho_api_settings(zoho_org_id)

@login_required(login_url='login')
def zoho_api_connect(request, zoho_org_id):
    return helpers.zoho_api_connect(request, zoho_org_id)
    

# =========================
# INVENTORY ITEMS
# =========================

@api_view(['POST'])
@permission_classes([AllowAny])
def load_inventory_items(request, zoho_org_id):
    t0 = time.time()
    list_calls = 0
    created = updated = 0
    status = 'ok'

    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    logger.debug(f"AppConfig: {app_config}")
    try:
        headers = helpers.config_headers(zoho_org_id)
    except Exception as e:
        logger.error(f"Error connecting to Zoho API: {str(e)}")
        status = 'error'
        _set_metrics('items',
            last_run=_now_iso(),
            last_sync_date=SyncMetadata.get_last_sync_date('last_sync_date_items') or '',
            list_calls=list_calls, detail_calls=0, package_calls=0,
            created=created, updated=updated,
            duration_sec=round(time.time()-t0, 3), status=status)
        return JsonResponse({'error': f"Error connecting to Zoho API (Load Items): {str(e)}"}, status=500)

    data = json.loads(request.body) if request.body else {}
    item_number = data.get('item_number')

    session = helpers._retry_session()

    def fetch_page(single_url, single_headers, single_params):
        nonlocal list_calls
        try:
            resp = session.get(single_url, headers=single_headers, params=single_params)
            list_calls += 1
            if resp.status_code == 401:
                new_token = helpers.refresh_zoho_access_token(zoho_org_id)
                single_headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                resp = session.get(single_url, headers=single_headers, params=single_params)
                list_calls += 1
            resp.raise_for_status()
            d = resp.json()
            items = d.get('items', [])
            has_more_page = d.get('page_context', {}).get('has_more_page', False)
            return items, has_more_page
        except requests.RequestException as e:
            logger.error(f"Error fetching data: {e}")
            return [], False

    def fetch_single(single_url, single_headers, single_params):
        nonlocal list_calls
        try:
            resp = session.get(single_url, headers=single_headers, params=single_params)
            list_calls += 1
            if resp.status_code == 401:
                new_token = helpers.refresh_zoho_access_token(zoho_org_id)
                single_headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                resp = session.get(single_url, headers=single_headers, params=single_params)
                list_calls += 1
            resp.raise_for_status()
            return resp.json().get('item', {})
        except requests.RequestException as e:
            logger.error(f"Error fetching single item: {e}")
            return {}

    params = {'organization_id': app_config.zoho_org_id}
    if not item_number:
        params.update({'per_page': 200, 'page': 1})
        url = settings.ZOHO_INVENTORY_ITEMS_URL
        items_to_get = []
        page = 1
        has_more = True
        while has_more:
            cur = params.copy(); cur['page'] = page
            page_items, has_more = fetch_page(url, headers.copy(), cur)
            items_to_get.extend(page_items)
            page += 1
    else:
        url = f"{settings.ZOHO_INVENTORY_ITEMS_URL}/{item_number}"
        items_to_get = []
        single = fetch_single(url, headers.copy(), params.copy())
        if single: items_to_get.append(single)

    logger.debug(f"Total items fetched: {len(items_to_get)}")

    item_ids = [it['item_id'] for it in items_to_get]
    existing_items = ZohoInventoryItem.objects(item_id__in=item_ids)
    existing_map = {ei.item_id: ei for ei in existing_items}

    new_items, items_to_update, timeline_items = [], [], []
    for data_item in items_to_get:
        new_item = create_inventory_item_instance(logger, data_item, zoho_org_id)
        prev_item = existing_map.get(new_item.item_id)
        if prev_item:
            prev_status = prev_item.status
            prev_stock = prev_item.stock_on_hand
            items_to_update.append(new_item)
            if prev_status != new_item.status:
                timeline_items.append(TimelineItem(
                    item_number=new_item.item_id,
                    previous_status_zoho=prev_status,
                    date_previous_status_zoho=prev_item.last_modified_time or prev_item.created_time,
                    actual_status_zoho=new_item.status,
                    date_actual_status_zoho=new_item.last_modified_time or new_item.created_time,
                    text=f"{new_item.sku or '-'} status changed -> From {prev_status} to {new_item.status}"
                ))
            if int(prev_stock) != int(new_item.stock_on_hand):
                change = 'added' if new_item.stock_on_hand > prev_stock else 'removed'
                abs_value = abs(new_item.stock_on_hand - prev_stock)
                timeline_items.append(TimelineItem(
                    item_number=new_item.item_id,
                    previous_stock_on_hand=prev_stock,
                    date_previous_stock_on_hand=prev_item.last_modified_time or prev_item.created_time,
                    actual_stock_on_hand=new_item.stock_on_hand,
                    date_actual_stock_on_hand=new_item.last_modified_time or new_item.created_time,
                    text=f"{new_item.sku or '-'} : {int(abs_value)} unit(s) {change} -> New stock on hand: {int(new_item.stock_on_hand)}"
                ))
        else:
            new_items.append(new_item)
            timeline_items.append(TimelineItem(
                item_number=new_item.item_id,
                actual_stock_on_hand=new_item.stock_on_hand,
                date_actual_stock_on_hand=new_item.last_modified_time or new_item.created_time,
                actual_status_zoho=new_item.status,
                date_actual_status_zoho=new_item.last_modified_time or new_item.created_time,
                text=f"{new_item.sku or '-'} created -> On hand: {int(new_item.stock_on_hand)}, Status: {new_item.status}"
            ))

    if new_items:
        ZohoInventoryItem.objects.insert(new_items)
        created = len(new_items)
    if items_to_update:
        for upd in items_to_update:
            db = ZohoInventoryItem.objects(item_id=upd.item_id).first()
            if db:
                db.status = upd.status
                db.stock_on_hand = upd.stock_on_hand
                db.last_modified_time = upd.last_modified_time
                db.save()
        updated = len(items_to_update)
    if timeline_items:
        TimelineItem.objects.insert(timeline_items)

    duration = round(time.time()-t0, 3)
    _set_metrics('items',
        last_run=_now_iso(),
        last_sync_date=SyncMetadata.get_last_sync_date('last_sync_date_items') or '',
        list_calls=list_calls, detail_calls=0, package_calls=0,
        created=created, updated=updated,
        duration_sec=duration, status=status)

    logger.info(f"Items processed successfully: {created} created, {updated} updated")
    return JsonResponse({'message': 'Items loaded successfully'}, status=200)


# ----------------------------------------------------------

# =========================
# SALES ORDERS (optimizado)
# =========================

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

@api_view(['POST'])
@permission_classes([AllowAny])
def load_inventory_sales_orders(request, zoho_org_id):
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

    data = json.loads(request.body if request.body else '{}')
    start_date = data.get('start_date', None)
    end_date = data.get('end_date', None)
    if not start_date:
        return JsonResponse({'error': 'Start date is required'}, status=400)
    try:
        dt.strptime(start_date, '%Y-%m-%d')
        if end_date: dt.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    yesterday = dt.strptime(start_date, '%Y-%m-%d') - timedelta(days=0)
    last_modified_time = yesterday.strftime('%Y-%m-%d') + 'T00:00:00+0000'

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


@api_view(['POST'])
@permission_classes([AllowAny])
def load_inventory_sales_orders_by_customer_name(request, zoho_org_id):
    MAX_WORKERS = 2
    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    logger.debug(app_config)
    try:
        headers = helpers.config_headers(zoho_org_id)
    except Exception as e:
        logger.error(f"Error connecting to Zoho API: {str(e)}")
        return JsonResponse({'error': f"Error connecting to Zoho API (Load Items): {str(e)}"}, status=500)

    data = json.loads(request.body)
    customer_name = data.get('customer_name')
    
    params = {
        'organization_id': app_config.zoho_org_id,
        'per_page': 200,
        'page': 1,
        'customer_name_contains': customer_name
    }

    url = settings.ZOHO_INVENTORY_SALESORDERS_URL
    items_to_get = []
    session = requests.Session()

    while True:
        try:
            response = session.get(url, headers=headers, params=params)
            if response.status_code == 401:
                new_token = helpers.refresh_zoho_access_token(zoho_org_id)
                headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                response = session.get(url, headers=headers, params=params)
            response.raise_for_status()
            items = response.json()
            items_to_get.extend(items.get('salesorders', []))
            if not items.get('page_context', {}).get('has_more_page', False):
                break
            params['page'] += 1
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching sales orders: {e}")
            return JsonResponse({'error': 'Failed to fetch sales orders'}, status=500)
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_sales_order_details, item, session, headers, zoho_org_id) for item in items_to_get]
        full_items_to_get = [future.result() for future in as_completed(futures) if future.result()]
    
    salesorder_ids = [item['salesorder_id'] for item in full_items_to_get]
    existing_orders = ZohoInventoryShipmentSalesOrder.objects(Q(salesorder_id__in=salesorder_ids))
    existing_salesorder_ids = set(existing_orders.distinct('salesorder_id'))

    new_sales_orders = []
    sales_orders_to_update = []
    
    for data in full_items_to_get:
        new_item = create_inventory_sales_order_instance(logger, data, zoho_org_id)
        if new_item and new_item.salesorder_id in existing_salesorder_ids:
            sales_orders_to_update.append(new_item)
        elif new_item:
            new_sales_orders.append(new_item)

    if new_sales_orders:
        ZohoInventoryShipmentSalesOrder.objects.insert(new_sales_orders, load_bulk=False)

    if sales_orders_to_update:
        for updated_item in sales_orders_to_update:
            db_sales_order = ZohoInventoryShipmentSalesOrder.objects(salesorder_id=updated_item.salesorder_id).first()
            if db_sales_order is not None:
                db_sales_order.salesorder_number = updated_item.salesorder_number
                db_sales_order.date = updated_item.date
                db_sales_order.status = updated_item.status
                db_sales_order.customer_id = updated_item.customer_id
                db_sales_order.customer_name = updated_item.customer_name
                db_sales_order.is_taxable = updated_item.is_taxable
                db_sales_order.tax_id = updated_item.tax_id
                db_sales_order.tax_name = updated_item.tax_name
                db_sales_order.tax_percentage = updated_item.tax_percentage
                db_sales_order.currency_id = updated_item.currency_id
                db_sales_order.currency_code = updated_item.currency_code
                db_sales_order.currency_symbol = updated_item.currency_symbol
                db_sales_order.exchange_rate = updated_item.exchange_rate
                db_sales_order.delivery_method = updated_item.delivery_method
                db_sales_order.total_quantity = updated_item.total_quantity
                db_sales_order.sub_total = updated_item.sub_total
                db_sales_order.tax_total = updated_item.tax_total
                db_sales_order.total = updated_item.total
                db_sales_order.created_by_email = updated_item.created_by_email
                db_sales_order.created_by_name = updated_item.created_by_name
                db_sales_order.salesperson_id = updated_item.salesperson_id
                db_sales_order.salesperson_name = updated_item.salesperson_name
                db_sales_order.is_test_order = updated_item.is_test_order
                db_sales_order.notes = updated_item.notes
                db_sales_order.payment_terms = updated_item.payment_terms
                db_sales_order.payment_terms_label = updated_item.payment_terms_label
                db_sales_order.line_items = updated_item.line_items
                db_sales_order.shipping_address = updated_item.shipping_address
                db_sales_order.billing_address = updated_item.billing_address
                db_sales_order.warehouses = updated_item.warehouses
                db_sales_order.custom_fields = updated_item.custom_fields
                db_sales_order.order_sub_statuses = updated_item.order_sub_statuses
                db_sales_order.shipment_sub_statuses = updated_item.shipment_sub_statuses
                db_sales_order.created_time = updated_item.created_time
                db_sales_order.last_modified_time = updated_item.last_modified_time
                db_sales_order.zoho_org_id = zoho_org_id
                db_sales_order.save()
                
    logger.info(f"Sales Orders processed successfully: {len(new_sales_orders)} created, {len(sales_orders_to_update)} updated")
    
    return JsonResponse({'message': 'Sales Orders loaded successfully'}, status=200)


@api_view(['POST'])
@permission_classes([AllowAny])
def load_inventory_sales_orders_to_qbwc(request, zoho_org_id):
    MAX_WORKERS = 2
    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    logger.info(f'App Config: {app_config}')
    try:
        headers = helpers.config_headers(zoho_org_id)
    except Exception as e:
        logger.error(f"Error connecting to Zoho API: {str(e)}")
        return JsonResponse({'error': f"Error connecting to Zoho API (Load Items): {str(e)}"}, status=500)

    data = json.loads(request.body if request.body else '{}')
    date = data.get('date', None)

    if not date:
        return JsonResponse({'error': 'Date is required'}, status=400)

    try:
        dt.strptime(date, '%Y-%m-%d')
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    params = {
        'organization_id': app_config.zoho_org_id,
        'per_page': 200,
        'page': 1,
        'date': date,
    }

    url = settings.ZOHO_INVENTORY_SALESORDERS_URL
    items_to_get = []
    session = requests.Session()

    while True:
        try:
            response = session.get(url, headers=headers, params=params)
            if response.status_code == 401:
                new_token = helpers.refresh_zoho_access_token(zoho_org_id)
                headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                response = session.get(url, headers=headers, params=params)
            response.raise_for_status()
            items = response.json()
            items_to_get.extend(items.get('salesorders', []))
            if not items.get('page_context', {}).get('has_more_page', False):
                break
            params['page'] += 1
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching sales orders: {e}")
            return JsonResponse({'error': 'Failed to fetch sales orders'}, status=500)
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_sales_order_details, item, session, headers, zoho_org_id) for item in items_to_get]
        full_items_to_get = [future.result() for future in as_completed(futures) if future.result()]

    return JsonResponse({
        'message': 'Sales Orders loaded successfully to QBWC', 
        'count': len(full_items_to_get),
        'data': full_items_to_get
    }, status=200)


# =========================
# SHIPMENTS + PACKAGES (optimizado)
# =========================

@retry(retry=retry_if_exception_type(requests.exceptions.RequestException),
       wait=wait_exponential(multiplier=1, min=4, max=60),
       stop=stop_after_attempt(5))
def fetch_package(package_id, session, headers, zoho_org_id):
    if not package_id: return None
    url = f'{settings.ZOHO_INVENTORY_PACKAGES_URL}/{package_id}'
    try:
        resp = helpers.zoho_get(session, url, headers, params={}, zoho_org_id=zoho_org_id, logger=logger, timeout=50)
        return resp.json().get('package')
    except Exception as e:
        logger.error(f"Error fetching package {package_id}: {e}")
        return None

@retry(retry=retry_if_exception_type(requests.exceptions.RequestException),
       wait=wait_exponential(multiplier=1, min=4, max=60),
       stop=stop_after_attempt(5))
def fetch_shipment_details(item, session, headers, zoho_org_id):
    sid = item.get("shipment_id")
    if not sid: return None
    url = f'{settings.ZOHO_INVENTORY_SHIPMENTS_URL}/{sid}'
    try:
        resp = helpers.zoho_get(session, url, headers, params={}, zoho_org_id=zoho_org_id, logger=logger, timeout=50)
        return resp.json().get('shipmentorder')
    except Exception as e:
        logger.error(f"Error fetching details for shipment {sid}: {e}")
        return None

@api_view(['POST'])
@permission_classes([AllowAny])
def load_inventory_shipments(request, zoho_org_id):
    t0 = time.time()
    list_calls = shipment_detail_calls = package_calls = 0
    created = updated = 0
    status = 'ok'

    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    try:
        headers = helpers.config_headers(zoho_org_id)
    except Exception as e:
        logger.error(f"Error connecting to Zoho API: {str(e)}")
        status = 'error'
        _set_metrics('shipments',
            last_run=_now_iso(),
            last_sync_date=SyncMetadata.get_last_sync_date('last_sync_date_shipments') or '',
            list_calls=list_calls, detail_calls=shipment_detail_calls, package_calls=package_calls,
            created=created, updated=updated, duration_sec=round(time.time()-t0,3),
            status=status)
        return JsonResponse({'error': f"Error connecting to Zoho API (Load Shipments): {str(e)}"}, status=500)

    data = json.loads(request.body)
    start_date = data.get('start_date', None)

    yesterday = dt.strptime(start_date, '%Y-%m-%d') - timedelta(days=1)
    last_modified_time = yesterday.strftime('%Y-%m-%d') + 'T00:00:00+0000'
    logger.debug(f"Fetching shipments from last_modified_time: {last_modified_time}")

    params = {
        'organization_id': app_config.zoho_org_id,
        'per_page': 200, 'page': 1,
        'last_modified_time': last_modified_time,
    }
    url = settings.ZOHO_INVENTORY_SHIPMENTS_URL
    items_to_get = []

    session = helpers._retry_session()

    while True:
        try:
            resp = helpers.zoho_get(session, url, headers, params, zoho_org_id, logger, timeout=60)
            list_calls += 1
            payload = resp.json()
            items_to_get.extend(payload.get('shipmentorders', []) or [])
            if not payload.get('page_context', {}).get('has_more_page', False):
                break
            params['page'] += 1
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching shipments: {e}")
            status = 'error'
            _set_metrics('shipments',
                last_run=_now_iso(),
                last_sync_date=SyncMetadata.get_last_sync_date('last_sync_date_shipments') or '',
                list_calls=list_calls, detail_calls=shipment_detail_calls, package_calls=package_calls,
                created=created, updated=updated, duration_sec=round(time.time()-t0,3),
                status=status)
            return JsonResponse({'error': 'Failed to fetch shipments'}, status=500)

    def _lm(s): return s.get("last_modified_time") or s.get("created_time") or ""
    items_to_get.sort(key=_lm, reverse=True)

    shipment_ids_list = [it.get('shipment_id') for it in items_to_get if it.get('shipment_id')]
    existing_shipments = ZohoShipmentOrder.objects(Q(shipment_id__in=shipment_ids_list))
    existing_map = {s.shipment_id: _parse_zoho_ts(s.last_modified_time) for s in existing_shipments}

    def _needs_shipment_detail(list_item):
        sid = list_item.get('shipment_id')
        if not sid: return False
        listed_lm = _parse_zoho_ts(list_item.get('last_modified_time'))
        prev_lm = existing_map.get(sid)
        if prev_lm is None: return True
        if listed_lm and prev_lm and listed_lm > prev_lm: return True
        return False

    detail_candidates = [it for it in items_to_get if _needs_shipment_detail(it)]

    with ThreadPoolExecutor(max_workers=helpers.ZOHO_WORKERS_SHIP) as executor:
        futures = [executor.submit(fetch_shipment_details, it, session, headers, zoho_org_id)
                   for it in detail_candidates]
        full_items_to_get = []
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                full_items_to_get.append(r)
        shipment_detail_calls = len(detail_candidates)

    # PACKAGES (obligado)
    all_package_ids = []
    for sh in full_items_to_get:
        for pkg in (sh.get("packages") or []):
            pid = pkg.get("package_id") if isinstance(pkg, dict) else pkg
            if pid:
                all_package_ids.append(pid)
    all_package_ids = sorted(set(all_package_ids))

    all_packages_data = []
    if all_package_ids:
        with ThreadPoolExecutor(max_workers=helpers.ZOHO_WORKERS_PKG) as executor:
            fut2pkg = {executor.submit(fetch_package, pid, session, headers, zoho_org_id): pid for pid in all_package_ids}
            for fut in as_completed(fut2pkg):
                pkg_data = fut.result()
                if pkg_data:
                    all_packages_data.append(pkg_data)
        package_calls = len(all_package_ids)

    # Persistencia (igual)
    if all_package_ids:
        existing_packages = ZohoPackage.objects(package_id__in=all_package_ids)
        existing_packages_ids = set(existing_packages.distinct('package_id'))
    else:
        existing_packages_ids = set()

    new_packages, packages_to_update = [], []
    for pkg_data in all_packages_data:
        new_pkg = create_inventory_package_instance(logger, pkg_data, zoho_org_id)
        if not new_pkg: continue
        if new_pkg.package_id in existing_packages_ids:
            packages_to_update.append(new_pkg)
        else:
            new_packages.append(new_pkg)

    shipments_ids = [it['shipment_id'] for it in full_items_to_get if it.get('shipment_id')]
    if shipments_ids:
        existing_shipments2 = ZohoShipmentOrder.objects(Q(shipment_id__in=shipments_ids))
        existing_shipments_ids = set(existing_shipments2.distinct('shipment_id'))
    else:
        existing_shipments_ids = set()

    new_shipments, shipments_to_update = [], []
    for data_item in full_items_to_get:
        new_item = create_inventory_shipment_instance(logger, data_item, zoho_org_id)
        if new_item and new_item.shipment_id in existing_shipments_ids:
            shipments_to_update.append(new_item)
        elif new_item:
            new_shipments.append(new_item)

    if new_shipments:
        ZohoShipmentOrder.objects.insert(new_shipments, load_bulk=False)
        created = len(new_shipments)
    if shipments_to_update:
        for shipment in shipments_to_update:
            obj = ZohoShipmentOrder.objects(shipment_id=shipment.shipment_id).first()
            if obj:
                # (todos tus campos exactos)
                obj.salesorder_id = shipment.salesorder_id
                obj.salesorder_number = shipment.salesorder_number
                obj.salesorder_date = shipment.salesorder_date
                obj.salesorder_fulfilment_status = shipment.salesorder_fulfilment_status
                obj.sales_channel = shipment.sales_channel
                obj.sales_channel_formatted = shipment.sales_channel_formatted
                obj.shipment_number = shipment.shipment_number
                obj.date = shipment.date
                obj.shipment_status = shipment.shipment_status
                obj.shipment_sub_status = shipment.shipment_sub_status
                obj.status = shipment.status
                obj.detailed_status = shipment.detailed_status
                obj.status_message = shipment.status_message
                obj.carrier = shipment.carrier
                obj.tracking_carrier_code = shipment.tracking_carrier_code
                obj.service = shipment.service
                obj.delivery_days = shipment.delivery_days
                obj.source_id = shipment.source_id
                obj.label_format = shipment.label_format
                obj.source_name = shipment.source_name
                obj.delivery_guarantee = shipment.delivery_guarantee
                obj.reference_number = shipment.reference_number
                obj.customer_id = shipment.customer_id
                obj.customer_name = shipment.customer_name
                obj.is_taxable = shipment.is_taxable
                obj.tax_id = shipment.tax_id
                obj.tax_name = shipment.tax_name
                obj.tax_percentage = shipment.tax_percentage
                obj.currency_id = shipment.currency_id
                obj.currency_code = shipment.currency_code
                obj.currency_symbol = shipment.currency_symbol
                obj.exchange_rate = shipment.exchange_rate
                obj.discount = shipment.discount
                obj.is_discount_before_tax = shipment.is_discount_before_tax
                obj.discount_type = shipment.discount_type
                obj.estimate_id = shipment.estimate_id
                obj.delivery_method = shipment.delivery_method
                obj.delivery_method_id = shipment.delivery_method_id
                obj.tracking_number = shipment.tracking_number
                obj.tracking_link = shipment.tracking_link
                obj.last_tracking_update_date = shipment.last_tracking_update_date
                obj.expected_delivery_date = shipment.expected_delivery_date
                obj.shipment_delivered_date = shipment.shipment_delivered_date
                obj.shipment_type = shipment.shipment_type
                obj.is_carrier_shipment = shipment.is_carrier_shipment
                obj.is_tracking_enabled = shipment.is_tracking_enabled
                obj.is_forms_available = shipment.is_forms_available
                obj.shipping_charge = shipment.shipping_charge
                obj.sub_total = shipment.sub_total
                obj.tax_total = shipment.tax_total
                obj.total = shipment.total
                obj.price_precision = shipment.price_precision
                obj.is_emailed = shipment.is_emailed
                obj.notes = shipment.notes
                obj.template_id = shipment.template_id
                obj.template_name = shipment.template_name
                obj.template_type = shipment.template_type
                obj.created_time = shipment.created_time
                obj.last_modified_time = shipment.last_modified_time
                obj.associated_packages_count = shipment.associated_packages_count
                obj.created_by_id = shipment.created_by_id
                obj.last_modified_by_id = shipment.last_modified_by_id
                obj.contact_persons = shipment.contact_persons
                obj.invoices = shipment.invoices
                obj.line_items = shipment.line_items
                obj.packages = shipment.packages
                obj.billing_address = shipment.billing_address
                obj.shipping_address = shipment.shipping_address
                obj.custom_fields = shipment.custom_fields
                obj.custom_field_hash = shipment.custom_field_hash
                obj.documents = shipment.documents
                obj.taxes = shipment.taxes
                obj.tracking_statuses = shipment.tracking_statuses
                obj.multipiece_shipments = shipment.multipiece_shipments
                obj.zoho_org_id = zoho_org_id
                obj.save()
        updated = len(shipments_to_update)

    duration = round(time.time()-t0, 3)
    _set_metrics('shipments',
        last_run=_now_iso(),
        last_sync_date=SyncMetadata.get_last_sync_date('last_sync_date_shipments') or '',
        list_calls=list_calls, detail_calls=shipment_detail_calls, package_calls=package_calls,
        created=created, updated=updated,
        duration_sec=duration, status=status)

    logger.info(f"Shipments processed successfully: {created} created, {updated} updated")
    return JsonResponse({'message': 'Shipments loaded successfully'}, status=200)


# =========================
# BOOKS CUSTOMERS (métrica básica)
# =========================

CONCURRENT_WORKERS = 50

def fetch_customers_from_api(headers, params, last_sync_date, zoho_org_id, counters):
    customers_to_get = []
    url = f'{settings.ZOHO_BOOKS_CUSTOMERS_URL}'
    if last_sync_date.tzinfo is None:
        last_sync_date = last_sync_date.replace(tzinfo=tz.utc)

    session = helpers._retry_session()
    while True:
        try:
            resp = session.get(url, headers=headers, params=params)
            counters['list_calls'] += 1
            if resp.status_code == 401:
                new_token = helpers.refresh_zoho_access_token(zoho_org_id)
                headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                resp = session.get(url, headers=headers, params=params)
                counters['list_calls'] += 1
            if resp.status_code != 200:
                logger.error(f"Error fetching customers: {resp.text}")
                break
            customers = resp.json()
            recent = [
                c for c in customers.get('contacts', [])
                if dt.strptime(c['last_modified_time'], '%Y-%m-%dT%H:%M:%S%z') > last_sync_date
            ]
            if recent:
                customers_to_get.extend(recent)
            if customers.get('page_context', {}).get('has_more_page', False):
                params['page'] += 1
            else:
                break
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching customers: {e}")
            break
    return customers_to_get

def process_customers_concurrently(customers_to_get, zoho_org_id):
    customers_ids = [item['contact_id'] for item in customers_to_get if item.get('contact_id')]
    existing_customers = ZohoCustomer.objects(Q(contact_id__in=customers_ids))
    existing_ids = set(existing_customers.distinct('contact_id'))
    new_customers, customers_to_update = [], []

    def process_customer(data_item, zoho_org_id):
        new_item = create_books_customers_instance(logger, data_item, zoho_org_id)
        if new_item and new_item.contact_id in existing_ids:
            customers_to_update.append(new_item)
        elif new_item:
            new_customers.append(new_item)

    with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
        futures = [executor.submit(process_customer, it, zoho_org_id) for it in customers_to_get]
        for f in as_completed(futures): f.result()

    if new_customers:
        ZohoCustomer.objects.insert(new_customers, load_bulk=False)
    if customers_to_update:
        for c in customers_to_update:
            obj = ZohoCustomer.objects(contact_id=c.contact_id).first()
            if obj:
                for field, value in c.to_mongo().to_dict().items():
                    if field != '_id':
                        setattr(obj, field, value)
                obj.save()
    return len(new_customers), len(customers_to_update)

@api_view(['POST'])
@permission_classes([AllowAny])
def load_books_customers(request, zoho_org_id):
    t0 = time.time()
    counters = {'list_calls': 0}
    created = updated = 0
    status = 'ok'

    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    try:
        headers = helpers.config_headers(zoho_org_id)
    except Exception as e:
        logger.error(f"Error connecting to Zoho API: {str(e)}")
        status = 'error'
        _set_metrics('customers',
            last_run=_now_iso(),
            last_sync_date=SyncMetadata.get_last_sync_date('last_sync_date_customers') or '',
            list_calls=counters['list_calls'], detail_calls=0, package_calls=0,
            created=created, updated=updated,
            duration_sec=round(time.time()-t0,3), status=status)
        return JsonResponse({'error': f"Error connecting to Zoho API: {str(e)}"}, status=500)

    params = {
        'page': 1, 'per_page': 200,
        'organization_id': app_config.zoho_org_id,
        'sort_column': 'last_modified_time',
    }

    last_sync_date = SyncMetadata.get_last_sync_date('last_sync_date_customers')
    if not last_sync_date:
        return JsonResponse({'error': 'last_sync_date is missing'}, status=400)
    try:
        if 'T' not in last_sync_date:
            last_sync_date += 'T00:00:00Z'
        last_sync_date = dt.strptime(last_sync_date, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        return JsonResponse({'error': 'Invalid last_sync_date format'}, status=400)

    customers_to_get = fetch_customers_from_api(headers, params, last_sync_date, zoho_org_id, counters)
    c_new, c_upd = process_customers_concurrently(customers_to_get, zoho_org_id)
    created, updated = c_new, c_upd

    SyncMetadata.update_last_sync_date('last_sync_date_customers', timezone.now().strftime("%Y-%m-%d"))
    duration = round(time.time()-t0, 3)
    _set_metrics('customers',
        last_run=_now_iso(),
        last_sync_date=SyncMetadata.get_last_sync_date('last_sync_date_customers') or '',
        list_calls=counters['list_calls'], detail_calls=0, package_calls=0,
        created=created, updated=updated,
        duration_sec=duration, status=status)

    logger.info(f"Customers processed successfully: {len(customers_to_get)}")
    return JsonResponse({'message': 'Customers loaded successfully'}, status=200)


#############################################
# LOAD BOOKS CUSTOMERS DETAILS
#############################################

CONCURRENT_WORKERS = 3
CALLS_PER_MINUTE = 100
RETRY_LIMIT = 3
BATCH_SIZE = 100

rate_limit_lock = Lock()
rate_limit_counter = 0
semaphore = Semaphore(CALLS_PER_MINUTE)


def fetch_customer_details(contact_id, headers, zoho_org_id):
    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    params = {
        'organization_id': app_config.zoho_org_id,
    }
    retries = 0
    while retries < RETRY_LIMIT:
        try:
            with semaphore:
                global rate_limit_counter
                with rate_limit_lock:
                    if rate_limit_counter >= CALLS_PER_MINUTE:
                        logger.warning("Rate limit reached. Pausing for 60 seconds.")
                        time.sleep(60)
                        rate_limit_counter = 0

                url = f'{settings.ZOHO_BOOKS_CUSTOMERS_URL}/{contact_id}'
                response = requests.get(url, headers=headers, params=params)

                with rate_limit_lock:
                    rate_limit_counter += 1

                if response.status_code == 401:
                    new_token = helpers.refresh_zoho_access_token(zoho_org_id)
                    headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                    response = requests.get(url, headers=headers, params=params)

                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limit exceeded for contact {contact_id}. Retrying in {retry_after} seconds.")
                    time.sleep(retry_after)
                    retries += 1
                    continue

                response.raise_for_status()
                full_item = response.json()
                return full_item.get('contact', None)
        except Exception as e:
            logger.error(f"Error fetching details for contact {contact_id}: {str(e)}")
            retries += 1

    logger.error(f"Max retries exceeded for contact {contact_id}")
    return None


def process_customers_in_batches(customers_ids, headers, zoho_org_id):
    results = []

    def process_customer(contact_id, zoho_org_id):
        return fetch_customer_details(contact_id, headers, zoho_org_id)

    with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
        futures = {executor.submit(process_customer, contact_id, zoho_org_id): contact_id for contact_id in customers_ids}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    return results


def load_books_customers_details(zoho_org_id):
    try:
        headers = helpers.config_headers(zoho_org_id)
    except Exception as e:
        logger.error(f"Error connecting to Zoho API: {str(e)}")
        return JsonResponse({'error': f"Error connecting to Zoho API: {str(e)}"}, status=500)

    customers = ZohoCustomer.objects.all()
    customers_ids = list(customers.distinct('contact_id'))

    all_results = []
    for i in range(0, len(customers_ids), BATCH_SIZE):
        batch = customers_ids[i:i + BATCH_SIZE]
        results = process_customers_in_batches(batch, headers, zoho_org_id)
        all_results.extend(results)

    for result in all_results:
        new_item = create_books_customers_instance(logger, result, zoho_org_id)
        if new_item:
            ZohoCustomer.objects(contact_id=new_item.contact_id).update_one(**new_item.to_mongo().to_dict(), upsert=True)

    logger.info(f"Customers details processed successfully: {len(all_results)}")
    return JsonResponse({'message': 'Customers details loaded successfully'}, status=200)

#############################################
# LOAD BOOKS INVOICES
#############################################

@api_view(['POST'])
@permission_classes([AllowAny])
def load_books_invoices_by_customer_name(request, zoho_org_id):
    if request:
        app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
        try:
            headers = helpers.config_headers(zoho_org_id)
        except Exception as e:
            logger.error(f"Error connecting to Zoho API: {str(e)}")
            return JsonResponse({'error': f"Error connecting to Zoho API: {str(e)}"}, status=500)
        
        data = json.loads(request.body)
        customer_name = data.get('customer_name', None)
        
        params = {
            'organization_id': app_config.zoho_org_id,
            'page': 1,
            'per_page': 200,
            'customer_name': customer_name,
        }
        
        url = f'{settings.ZOHO_BOOKS_INVOICES_URL}'
        invoice_ids = fetch_invoices(url, headers, params, zoho_org_id)
        if invoice_ids is None:
            return JsonResponse({"error": "Failed to fetch customer invoices"}, status=500)
        
        invoices_to_save = fetch_full_invoices_parallel(invoice_ids, headers, zoho_org_id)

        process_and_save_fetched_invoices(invoices_to_save, zoho_org_id)

        return JsonResponse({'message': 'Customer Invoices loaded successfully'}, status=200)

    return JsonResponse({'error': 'Invalid request'}, status=400)

# =========================
# INVOICES (métrica de list + details)
# =========================

@api_view(['POST'])
@permission_classes([AllowAny])
def load_books_invoices(request, zoho_org_id):
    t0 = time.time()
    list_calls = detail_calls = 0
    created = updated = 0
    status = 'ok'

    if request:
        app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
        try:
            headers = helpers.config_headers(zoho_org_id)
        except Exception as e:
            logger.error(f"Error connecting to Zoho API: {str(e)}")
            status = 'error'
            _set_metrics('invoices',
                last_run=_now_iso(),
                last_sync_date=SyncMetadata.get_last_sync_date('last_sync_date_invoices') or '',
                list_calls=list_calls, detail_calls=detail_calls, package_calls=0,
                created=created, updated=updated,
                duration_sec=round(time.time()-t0,3), status=status)
            return JsonResponse({'error': f"Error connecting to Zoho API: {str(e)}"}, status=500)

        data = json.loads(request.body)
        date_to_query = data.get('start_date', None) or dt.today().strftime('%Y-%m-%d')

        yesterday = dt.strptime(date_to_query, '%Y-%m-%d') - timedelta(days=2)
        last_modified_time = yesterday.strftime('%Y-%m-%d') + 'T00:00:00+0000'

        params = {
            'organization_id': app_config.zoho_org_id,
            'page': 1, 'per_page': 200,
            'last_modified_time': last_modified_time,
        }

        # --- listado
        invoice_ids = []
        session = helpers._retry_session()
        while True:
            try:
                resp = session.get(settings.ZOHO_BOOKS_INVOICES_URL, headers=headers, params=params, timeout=180)
                list_calls += 1
                if resp.status_code == 401:
                    headers['Authorization'] = f'Zoho-oauthtoken {helpers.refresh_zoho_access_token(zoho_org_id)}'
                    resp = session.get(settings.ZOHO_BOOKS_INVOICES_URL, headers=headers, params=params, timeout=180)
                    list_calls += 1
                if resp.status_code != 200:
                    logger.error(f"Error fetching invoices: {resp.text}")
                    _set_metrics('invoices',
                        last_run=_now_iso(),
                        last_sync_date=SyncMetadata.get_last_sync_date('last_sync_date_invoices') or '',
                        list_calls=list_calls, detail_calls=detail_calls, package_calls=0,
                        created=created, updated=updated,
                        duration_sec=round(time.time()-t0,3), status='error')
                    return JsonResponse({"error": "Failed to fetch invoices"}, status=500)
                invoices = resp.json().get('invoices', [])
                invoice_ids.extend([inv.get('invoice_id') for inv in invoices if inv.get('invoice_id')])
                page_context = resp.json().get('page_context', {})
                if not page_context.get('has_more_page', False):
                    break
                params['page'] += 1
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching invoices: {e}")
                _set_metrics('invoices',
                    last_run=_now_iso(),
                    last_sync_date=SyncMetadata.get_last_sync_date('last_sync_date_invoices') or '',
                    list_calls=list_calls, detail_calls=detail_calls, package_calls=0,
                    created=created, updated=updated,
                    duration_sec=round(time.time()-t0,3), status='error')
                return JsonResponse({"error": "Failed to fetch invoices"}, status=500)

        # --- detalles
        invoices_data = []
        def fetch_full_invoice(invoice_id, headers, zoho_org_id):
            get_url = f'{settings.ZOHO_BOOKS_INVOICES_URL}/{invoice_id}/?organization_id={zoho_org_id}'
            try:
                r = session.get(get_url, headers=headers, timeout=180)
                return r.json().get('invoice') if r.status_code == 200 else None
            except requests.exceptions.RequestException:
                return None

        with ThreadPoolExecutor(max_workers=10) as executor:
            futs = {executor.submit(fetch_full_invoice, iid, headers, zoho_org_id): iid for iid in invoice_ids}
            for f in as_completed(futs):
                inv = f.result()
                if inv: invoices_data.append(inv)
        detail_calls = len(invoice_ids)

        # --- persistencia (igual a tu lógica)
        invoices_ids = [it['invoice_id'] for it in invoices_data if it.get('invoice_id')]
        existing_invoices = ZohoFullInvoice.objects(Q(invoice_id__in=invoices_ids))
        existing_ids = set(existing_invoices.distinct('invoice_id'))

        new_invoices, invoices_to_update = [], []
        for data_item in invoices_data:
            new_invoice = create_books_invoice_instance(logger, data_item, zoho_org_id)
            if new_invoice and new_invoice.invoice_id in existing_ids:
                invoices_to_update.append(new_invoice)
            elif new_invoice:
                new_invoices.append(new_invoice)

        if new_invoices:
            ZohoFullInvoice.objects.insert(new_invoices, load_bulk=False)
            created = len(new_invoices)
        if invoices_to_update:
            for inv in invoices_to_update:
                obj = ZohoFullInvoice.objects(invoice_id=inv.invoice_id).first()
                if obj:
                    # (mismos campos exactos que ya tenías)
                    obj.invoice_id = inv.invoice_id
                    obj.invoice_number = inv.invoice_number
                    obj.date = inv.date
                    obj.due_date = inv.due_date
                    obj.customer_id = inv.customer_id
                    obj.customer_name = inv.customer_name
                    obj.email = inv.email
                    obj.status = inv.status
                    obj.recurring_invoice_id = inv.recurring_invoice_id
                    obj.payment_terms = inv.payment_terms
                    obj.payment_terms_label = inv.payment_terms_label
                    obj.payment_reminder_enabled = inv.payment_reminder_enabled
                    obj.payment_discount = inv.payment_discount
                    obj.credits_applied = inv.credits_applied
                    obj.payment_made = inv.payment_made
                    obj.reference_number = inv.reference_number
                    obj.line_items = inv.line_items
                    obj.allow_partial_payments = inv.allow_partial_payments
                    obj.price_precision = inv.price_precision
                    obj.sub_total = inv.sub_total
                    obj.tax_total = inv.tax_total
                    obj.discount_total = inv.discount_total
                    obj.discount_percent = inv.discount_percent
                    obj.discount = inv.discount
                    obj.discount_applied_on_amount = inv.discount_applied_on_amount
                    obj.discount_type = inv.discount_type
                    obj.tax_override_preference = inv.tax_override_preference
                    obj.is_discount_before_tax = inv.is_discount_before_tax
                    obj.adjustment = inv.adjustment
                    obj.adjustment_description = inv.adjustment_description
                    obj.total = inv.total
                    obj.balance = inv.balance
                    obj.is_inclusive_tax = inv.is_inclusive_tax
                    obj.sub_total_inclusive_of_tax = inv.sub_total_inclusive_of_tax
                    obj.contact_category = inv.contact_category
                    obj.tax_rounding = inv.tax_rounding
                    obj.taxes = inv.taxes
                    obj.tds_calculation_type = inv.tds_calculation_type
                    obj.last_payment_date = inv.last_payment_date
                    obj.contact_persons = inv.contact_persons
                    obj.salesorder_id = inv.salesorder_id
                    obj.salesorder_number = inv.salesorder_number
                    obj.salesorders = inv.salesorders
                    obj.contact_persons_details = inv.contact_persons_details
                    obj.created_time = inv.created_time
                    obj.last_modified_time = inv.last_modified_time
                    obj.created_date = inv.created_date
                    obj.created_by_name = inv.created_by_name
                    obj.estimate_id = inv.estimate_id
                    obj.customer_default_billing_address = inv.customer_default_billing_address
                    obj.notes = inv.notes
                    obj.terms = inv.terms
                    obj.billing_address = inv.billing_address
                    obj.shipping_address = inv.shipping_address
                    obj.contact = inv.contact
                    obj.inserted_in_qb = inv.inserted_in_qb
                    obj.items_unmatched = inv.items_unmatched
                    obj.customer_unmatched = inv.customer_unmatched
                    obj.force_to_sync = inv.force_to_sync
                    obj.last_sync_date = inv.last_sync_date
                    obj.number_of_times_synced = inv.number_of_times_synced
                    obj.all_items_matched = inv.all_items_matched
                    obj.all_customer_matched = inv.all_customer_matched
                    obj.qb_customer_list_id = inv.qb_customer_list_id
                    obj.zoho_org_id = zoho_org_id
                    obj.save()
            updated = len(invoices_to_update)

        duration = round(time.time()-t0, 3)
        _set_metrics('invoices',
            last_run=_now_iso(),
            last_sync_date=SyncMetadata.get_last_sync_date('last_sync_date_invoices') or '',
            list_calls=list_calls, detail_calls=detail_calls, package_calls=0,
            created=created, updated=updated,
            duration_sec=duration, status=status)

        return JsonResponse({'message': 'Invoices loaded successfully'}, status=200)

    return JsonResponse({'error': 'Invalid request'}, status=400)


def fetch_invoices(url, headers, params, zoho_org_id):
    invoice_ids = []
    while True:
        try:
            response = requests.get(url, headers=headers, params=params, timeout=180)
            if response.status_code == 401:
                headers['Authorization'] = f'Zoho-oauthtoken {helpers.refresh_zoho_access_token(zoho_org_id)}'
                response = requests.get(url, headers=headers, params=params, timeout=180)

            if response.status_code != 200:
                logger.error(f"Error fetching invoices: {response.text}")
                return None

            invoices = response.json().get('invoices', [])
            invoice_ids.extend([invoice.get('invoice_id') for invoice in invoices])
            
            page_context = response.json().get('page_context', {})
            if not page_context.get('has_more_page', False):
                break
            params['page'] += 1
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching invoices: {e}")
            return None
    
    return invoice_ids


def fetch_full_invoices_parallel(invoice_ids, headers, zoho_org_id, max_workers=10):
    invoices_data = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_invoice = {executor.submit(fetch_full_invoice, invoice_id, headers, zoho_org_id): invoice_id for invoice_id in invoice_ids}
        for future in as_completed(future_to_invoice):
            invoice_data = future.result()
            if invoice_data:
                invoices_data.append(invoice_data)
    return invoices_data


def fetch_full_invoice(invoice_id, headers, zoho_org_id):
    get_url = f'{settings.ZOHO_BOOKS_INVOICES_URL}/{invoice_id}/?organization_id={zoho_org_id}'
    try:
        response = requests.get(get_url, headers=headers, timeout=180)
        if response.status_code == 200:
            return response.json().get('invoice')
        else:
            logger.error(f"Error fetching full invoice {invoice_id}: {response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching full invoice {invoice_id}: {e}")
    return None


def process_and_save_fetched_invoices(invoices_to_get, zoho_org_id):
    invoices_ids = [item['invoice_id'] for item in invoices_to_get if item.get('invoice_id')]
    existing_invoices = ZohoFullInvoice.objects(Q(invoice_id__in=invoices_ids))
    existing_invoices_ids = set(existing_invoices.distinct('invoice_id'))

    new_invoices = []
    invoices_to_update = []
    for data_item in invoices_to_get:
        new_invoice = create_books_invoice_instance(logger, data_item, zoho_org_id)
        if new_invoice and new_invoice.invoice_id in existing_invoices_ids:
            invoices_to_update.append(new_invoice)
        elif new_invoice:
            new_invoices.append(new_invoice)
            
    logger.info(f"New Invoices: {len(new_invoices)}, Invoices to update: {len(invoices_to_update)}")
    
    if new_invoices:
        ZohoFullInvoice.objects.insert(new_invoices, load_bulk=False)
    if invoices_to_update:
        for invoice in invoices_to_update:
            obj = ZohoFullInvoice.objects(invoice_id=invoice.invoice_id).first()
            if obj:
                obj.invoice_id = invoice.invoice_id
                obj.invoice_number = invoice.invoice_number
                obj.date = invoice.date
                obj.due_date = invoice.due_date
                obj.customer_id = invoice.customer_id
                obj.customer_name = invoice.customer_name
                obj.email = invoice.email
                obj.status = invoice.status
                obj.recurring_invoice_id = invoice.recurring_invoice_id
                obj.payment_terms = invoice.payment_terms
                obj.payment_terms_label = invoice.payment_terms_label
                obj.payment_reminder_enabled = invoice.payment_reminder_enabled
                obj.payment_discount = invoice.payment_discount
                obj.credits_applied = invoice.credits_applied
                obj.payment_made = invoice.payment_made
                obj.reference_number = invoice.reference_number
                obj.line_items = invoice.line_items
                obj.allow_partial_payments = invoice.allow_partial_payments
                obj.price_precision = invoice.price_precision
                obj.sub_total = invoice.sub_total
                obj.tax_total = invoice.tax_total
                obj.discount_total = invoice.discount_total
                obj.discount_percent = invoice.discount_percent
                obj.discount = invoice.discount
                obj.discount_applied_on_amount = invoice.discount_applied_on_amount
                obj.discount_type = invoice.discount_type
                obj.tax_override_preference = invoice.tax_override_preference
                obj.is_discount_before_tax = invoice.is_discount_before_tax
                obj.adjustment = invoice.adjustment
                obj.adjustment_description = invoice.adjustment_description
                obj.total = invoice.total
                obj.balance = invoice.balance
                obj.is_inclusive_tax = invoice.is_inclusive_tax
                obj.sub_total_inclusive_of_tax = invoice.sub_total_inclusive_of_tax
                obj.contact_category = invoice.contact_category
                obj.tax_rounding = invoice.tax_rounding
                obj.taxes = invoice.taxes
                obj.tds_calculation_type = invoice.tds_calculation_type
                obj.last_payment_date = invoice.last_payment_date
                obj.contact_persons = invoice.contact_persons
                obj.salesorder_id = invoice.salesorder_id
                obj.salesorder_number = invoice.salesorder_number
                obj.salesorders = invoice.salesorders
                obj.contact_persons_details = invoice.contact_persons_details
                obj.created_time = invoice.created_time
                obj.last_modified_time = invoice.last_modified_time
                obj.created_date = invoice.created_date
                obj.created_by_name = invoice.created_by_name
                obj.estimate_id = invoice.estimate_id
                obj.customer_default_billing_address = invoice.customer_default_billing_address
                obj.notes = invoice.notes
                obj.terms = invoice.terms
                obj.billing_address = invoice.billing_address
                obj.shipping_address = invoice.shipping_address
                obj.contact = invoice.contact
                obj.inserted_in_qb = invoice.inserted_in_qb
                obj.items_unmatched = invoice.items_unmatched
                obj.customer_unmatched = invoice.customer_unmatched
                obj.force_to_sync = invoice.force_to_sync
                obj.last_sync_date = invoice.last_sync_date
                obj.number_of_times_synced = invoice.number_of_times_synced
                obj.all_items_matched = invoice.all_items_matched
                obj.all_customer_matched = invoice.all_customer_matched
                obj.qb_customer_list_id = invoice.qb_customer_list_id
                obj.zoho_org_id = zoho_org_id
                obj.save()
    return new_invoices, invoices_to_update
            
# =========================
# MÉTRICAS PANEL (JSON/HTML)
# =========================

@api_view(['GET'])
@permission_classes([AllowAny])
def metrics_panel(request):
    fmt = request.GET.get('format', 'json').lower()
    # añadir last_sync_date faltantes con lectura de SyncMetadata (si alguien llama sin haber corrido nada)
    def _lsd(key):
        return SyncMetadata.get_last_sync_date(key) or ''

    defaults = {
        'items':        {'last_sync_date': _lsd('last_sync_date_items')},
        'salesorders':  {'last_sync_date': _lsd('last_sync_date_salesorders')},
        'shipments':    {'last_sync_date': _lsd('last_sync_date_shipments')},
        'invoices':     {'last_sync_date': _lsd('last_sync_date_invoices')},
        'customers':    {'last_sync_date': _lsd('last_sync_date_customers')},
    }
    # completa campos por defecto si aún no hay runs
    data = {}
    for mod in ['items','salesorders','shipments','invoices','customers']:
        base = {
            'last_run': '',
            'last_sync_date': defaults.get(mod,{}).get('last_sync_date',''),
            'list_calls': 0, 'detail_calls': 0, 'package_calls': 0,
            'created': 0, 'updated': 0,
            'duration_sec': 0.0, 'status': ''
        }
        base.update(METRICS.get(mod, {}))
        data[mod] = base

    if fmt == 'html':
        rows = []
        header = """
        <tr>
          <th>Módulo</th><th>Last Run</th><th>Last Sync</th>
          <th>List Calls</th><th>Detail Calls</th><th>Package Calls</th>
          <th>Created</th><th>Updated</th><th>Duration (s)</th><th>Status</th>
        </tr>"""
        for mod, m in data.items():
            rows.append(f"""
            <tr>
              <td>{mod}</td>
              <td>{m['last_run']}</td>
              <td>{m['last_sync_date']}</td>
              <td>{m['list_calls']}</td>
              <td>{m['detail_calls']}</td>
              <td>{m['package_calls']}</td>
              <td>{m['created']}</td>
              <td>{m['updated']}</td>
              <td>{m['duration_sec']}</td>
              <td>{m['status']}</td>
            </tr>""")
        html = f"""
        <html><head><title>Métricas NWS</title>
        <style>
          body{{font-family:Arial,Helvetica,sans-serif;padding:16px}}
          table{{border-collapse:collapse;width:100%}}
          th,td{{border:1px solid #ddd;padding:8px;text-align:center}}
          th{{background:#f5f5f5}}
        </style></head>
        <body>
          <h2>Métricas de Integraciones (última corrida)</h2>
          <table>{header}{''.join(rows)}</table>
          <p style="margin-top:12px;color:#666">Actualiza esta página para ver la métrica de la corrida más reciente.</p>
        </body></html>"""
        return HttpResponse(html)

    return JsonResponse(data, status=200)   
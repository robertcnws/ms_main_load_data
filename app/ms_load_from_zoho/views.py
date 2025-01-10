from rest_framework_mongoengine.viewsets import ModelViewSet
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter, Retry
from mongoengine import Q
from datetime import datetime as dt, timezone as tz
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import redirect
from django.contrib import messages
from django.core import serializers
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from threading import Semaphore, Lock
from requests.packages.urllib3.util.retry import Retry
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from urllib.parse import quote
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


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

#############################################
# GET AUTH URL
#############################################

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def generate_auth_url(request):
    app_config = AppConfig.objects.first()
    client_id = app_config.zoho_client_id
    redirect_uri = app_config.zoho_redirect_uri
    scopes = ",".join(settings.ZOHO_SCOPES)
    auth_url = f"https://accounts.zoho.com/oauth/v2/auth?scope={scopes}&client_id={client_id}&response_type=code&access_type=offline&redirect_uri={redirect_uri}"
    return JsonResponse({'auth_url': auth_url}, status=200)

#############################################
# GET ACCESS TOKEN
#############################################

def get_access_token(client_id, client_secret, refresh_token):
    logger.info('Getting access token')
    token_url = settings.ZOHO_TOKEN_URL
    if not refresh_token:
        raise Exception("Refresh token is missing")
        # refresh_token = get_refresh_token()
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    response = requests.post(token_url, data=payload)
    if response.status_code == 200:
        access_token = response.json()["access_token"]
    else:
        raise Exception("Error retrieving access token")
    return access_token

#############################################
# GET REFRESH TOKEN
#############################################

def refresh_zoho_access_token():
    app_config = AppConfig.objects.first()
    refresh_url = settings.ZOHO_TOKEN_URL
    payload = {
        'refresh_token': app_config.zoho_refresh_token,
        'client_id': app_config.zoho_client_id,
        'client_secret': app_config.zoho_client_secret,
        'grant_type': 'refresh_token'
    }
    response = requests.post(refresh_url, data=payload)
    if response.status_code == 200:
        new_token = response.json().get('access_token')
        return new_token
    else:
        raise Exception("Failed to refresh Zoho token")

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def get_refresh_token(request):
    authorization_code = request.GET.get("code", None)
    if not authorization_code:
        return JsonResponse({'error': 'Authorization code is missing'}, status=400)
    
    app_config = AppConfig.objects.first()
    token_url = "https://accounts.zoho.com/oauth/v2/token"
    data = {
        "code": authorization_code,
        "client_id": app_config.zoho_client_id,
        "client_secret": app_config.zoho_client_secret,
        "redirect_uri": app_config.zoho_redirect_uri,
        "grant_type": "authorization_code",
    }
    
    try:
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        response_json = response.json()
        access_token = response_json.get("access_token", None)
        refresh_token = response_json.get("refresh_token", None)

        if access_token and refresh_token:
            app_config.zoho_refresh_token = refresh_token
            app_config.save()
            return redirect(f'{settings.FRONTEND_URL}')
        else:
            return JsonResponse({'error': 'Failed to obtain access_token and/or refresh_token'}, status=400)

    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f'An error occurred: {str(e)}'}, status=500)


#############################################
# ZOHO API SETTINGS
#############################################

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def zoho_api_settings(request): 
    app_config = AppConfig.objects.first()
    if not app_config:
        app_config = AppConfig()
        app_config.save()

    connected = (
        app_config.zoho_connection_configured
        and app_config.zoho_refresh_token is not None
        or ""
    )
    
    auth_url = None
    if not connected:
        auth_url = reverse("ms_load_from_zoho:generate_auth_url")
    app_config_data = app_config.to_mongo().to_dict()
    app_config_data.pop('_id', None)  

    data = {
        "app_config": app_config_data,
        "connected": connected,
        "auth_url": auth_url,
        "zoho_connection_configured": app_config.zoho_connection_configured,
    }

    return JsonResponse(data, status=200)


#############################################
# ZOHO API CONNECT
#############################################

@login_required(login_url='login')
def zoho_api_connect(request):
    app_config = AppConfig.objects.first()
    if app_config.zoho_connection_configured:
        try:
            get_access_token(
                app_config.zoho_client_id,
                app_config.zoho_client_secret,
                app_config.zoho_refresh_token,
            )
            messages.success(request, "Zoho API connected successfully.")
        except Exception as e:
            messages.error(request, f"Error connecting to Zoho API: {str(e)}")
    else:
        messages.warning(request, "Zoho API connection is not configured yet.")
    return JsonResponse({'message': 'Zoho API connected successfully.'}, status=200)


def config_headers():
    app_config = AppConfig.objects.first()
    access_token = get_access_token(
        app_config.zoho_client_id,
        app_config.zoho_client_secret,
        app_config.zoho_refresh_token,
    )
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}"
    }
    return headers

#############################################
# LOAD INVENTORY ITEMS
#############################################

@api_view(['POST'])
@permission_classes([AllowAny])
def load_inventory_items(request):
    app_config = AppConfig.objects.first()
    logger.debug(f"AppConfig: {app_config}")
    try:
        headers = config_headers()
    except Exception as e:
        logger.error(f"Error connecting to Zoho API: {str(e)}")
        return JsonResponse({'error': f"Error connecting to Zoho API (Load Items): {str(e)}"}, status=500)

    data = json.loads(request.body) if request.body else {}
    item_number = data.get('item_number')
    username = data.get('username', None)

    if item_number:
        params = {
            'organization_id': app_config.zoho_org_id,
        }
        url = f"{settings.ZOHO_INVENTORY_ITEMS_URL}/{item_number}"
    else:
        params = {
            'organization_id': app_config.zoho_org_id,
            'per_page': 200,
            'page': 1
        }
        url = settings.ZOHO_INVENTORY_ITEMS_URL

    items_to_get = []

    retry_strategy = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)

    with requests.Session() as session:
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        def fetch_page(single_url, single_headers, single_params):
            try:
                response = session.get(single_url, headers=single_headers, params=single_params)
                if response.status_code == 401:
                    new_token = refresh_zoho_access_token()
                    single_headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                    response = session.get(single_url, headers=single_headers, params=single_params)
                response.raise_for_status()
                resp_data = response.json()
                items = resp_data.get('items', [])
                page_context = resp_data.get('page_context', {})
                has_more_page = page_context.get('has_more_page', False)
                return items, has_more_page
            except requests.RequestException as e:
                logger.error(f"Error fetching data: {e}")
                return [], False

        def fetch_single(single_url, single_headers, single_params):
            try:
                response = session.get(single_url, headers=single_headers, params=single_params)
                if response.status_code == 401:
                    new_token = refresh_zoho_access_token()
                    single_headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                    response = session.get(single_url, headers=single_headers, params=single_params)
                response.raise_for_status()
                resp_data = response.json()
                return resp_data.get('item', {})
            except requests.RequestException as e:
                logger.error(f"Error fetching single item: {e}")
                return {}

        if not item_number:
            page = 1
            has_more_page = True
            while has_more_page:
                current_params = params.copy()
                current_params['page'] = page
                page_items, has_more_page = fetch_page(url, headers.copy(), current_params)
                items_to_get.extend(page_items)
                page += 1
        else:
            single_item = fetch_single(url, headers.copy(), params.copy())
            if single_item:
                items_to_get.append(single_item)

    logger.debug(f"Total items fetched: {len(items_to_get)}")

    item_ids = [item['item_id'] for item in items_to_get]
    existing_items = ZohoInventoryItem.objects(item_id__in=item_ids)
    existing_items_map = {ei.item_id: ei for ei in existing_items}

    new_items = []
    items_to_update = []
    timeline_items = []

    for data_item in items_to_get:
        new_item = create_inventory_item_instance(logger, data_item)
        prev_item = existing_items_map.get(new_item.item_id)

        if prev_item:
            prev_status = prev_item.status
            prev_stock = prev_item.stock_on_hand
            items_to_update.append(new_item)
            
            if prev_status != new_item.status:
                timeline_items.append(
                    TimelineItem(
                        item_number=new_item.item_id,
                        previous_status_zoho=prev_status,
                        date_previous_status_zoho=prev_item.last_modified_time or prev_item.created_time,
                        actual_status_zoho=new_item.status,
                        date_actual_status_zoho=new_item.last_modified_time or new_item.created_time,
                        text=f"{new_item.sku or '-'} status changed -> From {prev_status} to {new_item.status}"
                    )
                )
            
            if int(prev_stock) != int(new_item.stock_on_hand):
                change = 'added' if new_item.stock_on_hand > prev_stock else 'removed'
                abs_value = abs(new_item.stock_on_hand - prev_stock)
                timeline_items.append(
                    TimelineItem(
                        item_number=new_item.item_id,
                        previous_stock_on_hand=prev_stock,
                        date_previous_stock_on_hand=prev_item.last_modified_time or prev_item.created_time,
                        actual_stock_on_hand=new_item.stock_on_hand,
                        date_actual_stock_on_hand=new_item.last_modified_time or new_item.created_time,
                        text=f"{new_item.sku or '-'} : {int(abs_value)} unit(s) {change} -> New stock on hand: {int(new_item.stock_on_hand)}"
                    )
                )
        else:
            new_items.append(new_item)
            timeline_items.append(
                TimelineItem(
                    item_number=new_item.item_id,
                    actual_stock_on_hand=new_item.stock_on_hand,
                    date_actual_stock_on_hand=new_item.last_modified_time or new_item.created_time,
                    actual_status_zoho=new_item.status,
                    date_actual_status_zoho=new_item.last_modified_time or new_item.created_time,
                    text=f"{new_item.sku or '-'} created -> On hand: {int(new_item.stock_on_hand)}, Status: {new_item.status}"
                )
            )
    
    if new_items:
        ZohoInventoryItem.objects.insert(new_items)
    
    for updated_item in items_to_update:
        db_item = ZohoInventoryItem.objects(item_id=updated_item.item_id).first()
        if db_item is not None:
            db_item.status = updated_item.status
            db_item.stock_on_hand = updated_item.stock_on_hand
            db_item.last_modified_time = updated_item.last_modified_time
            db_item.save()
    
    if timeline_items:
        TimelineItem.objects.insert(timeline_items)

    logger.info(f"Items processed successfully: {len(new_items)} created, {len(items_to_update)} updated")

    # if username:
    #     create_notification('zoho_item', 'has loaded new info from Zoho Items', 'load', username)
    #     create_notification('system_timeline', 'has added new info about timelines in Zoho Items', 'create_timeline', username)

    return JsonResponse({'message': 'Items loaded successfully'}, status=200)


# ----------------------------------------------------------

#############################################
# LOAD SALES ORDERS
#############################################

def fetch_sales_order_details(item, session, headers):
    try:
        url = f'{settings.ZOHO_INVENTORY_SALESORDERS_URL}/{item["salesorder_id"]}'
        response = session.get(url, headers=headers, params={})
        if response.status_code == 401:
            new_token = refresh_zoho_access_token()
            headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
            response = session.get(url, headers=headers, params={})
        response.raise_for_status()
        full_item = response.json()
        return full_item.get('salesorder', None)
    except Exception as e:
        logger.error(f"Error fetching details for sales order {item['salesorder_id']}: {e}")
        return None


@api_view(['POST'])
@permission_classes([AllowAny])
def load_inventory_sales_orders(request):
    MAX_WORKERS = 10
    app_config = AppConfig.objects.first()
    logger.debug(app_config)
    try:
        headers = config_headers()
    except Exception as e:
        logger.error(f"Error connecting to Zoho API: {str(e)}")
        return JsonResponse({'error': f"Error connecting to Zoho API (Load Items): {str(e)}"}, status=500)

    data = json.loads(request.body)
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    username = data.get('username', None)

    if not start_date:
        return JsonResponse({'error': 'Date is missing'}, status=400)
    try:
        dt.strptime(start_date, '%Y-%m-%d')
        if end_date:
            dt.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    params = {
        'organization_id': app_config.zoho_org_id,
        'per_page': 200,
        'page': 1
    }
    if end_date:
        params.update({'date_start': start_date, 'date_end': end_date})
    else:
        params['date'] = start_date

    url = settings.ZOHO_INVENTORY_SALESORDERS_URL
    items_to_get = []
    session = requests.Session()

    while True:
        try:
            response = session.get(url, headers=headers, params=params)
            if response.status_code == 401:
                new_token = refresh_zoho_access_token()
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
        futures = [executor.submit(fetch_sales_order_details, item, session, headers) for item in items_to_get]
        full_items_to_get = [future.result() for future in as_completed(futures) if future.result()]
    
    salesorder_ids = [item['salesorder_id'] for item in full_items_to_get]
    existing_orders = ZohoInventoryShipmentSalesOrder.objects(Q(salesorder_id__in=salesorder_ids))
    existing_salesorder_ids = set(existing_orders.distinct('salesorder_id'))

    new_sales_orders = []
    sales_orders_to_update = []
    
    for data in full_items_to_get:
        new_item = create_inventory_sales_order_instance(logger, data)
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
                db_sales_order.save()
                
    logger.info(f"Sales Orders processed successfully: {len(new_sales_orders)} created, {len(sales_orders_to_update)} updated")
    
    return JsonResponse({'message': 'Sales Orders loaded successfully'}, status=200)


#############################################
# LOAD SHIPMENTS AND PACKAGES
#############################################

@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5)
)
def fetch_package(package_id, session, headers):
    url = f'{settings.ZOHO_INVENTORY_PACKAGES_URL}/{package_id}'
    try:
        response = session.get(url, headers=headers, params={})
        if response.status_code == 401:
            new_token = refresh_zoho_access_token()
            headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
            response = session.get(url, headers=headers, params={})
        if response.status_code == 429:
            logger.warning(f"Rate limit exceeded when fetching package {package_id}. Retrying...")
            time.sleep(10)
            response.raise_for_status()
        if response.status_code >= 400:
            logger.error(f"Error 1 fetching the package: {response.text}")
            return JsonResponse({'error': 'Failed to fetch shipments'}, status=500)
        response.raise_for_status()
        item = response.json()
        return item.get('package', None)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error 2 fetching shipments: {e}")
        raise
        # return JsonResponse({'error': 'Failed to fetch shipments'}, status=500)
    
@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5)
)
def fetch_shipment_details(item, session, headers):
    try:
        url = f'{settings.ZOHO_INVENTORY_SHIPMENTS_URL}/{item["shipment_id"]}'
        response = session.get(url, headers=headers, params={})
        if response.status_code == 401:
            new_token = refresh_zoho_access_token()
            headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
            response = session.get(url, headers=headers, params={})
        if response.status_code == 429:
            logger.warning(f"Rate limit exceeded when fetching shipment {item['shipment_id']}. Retrying...")
            time.sleep(10)
            response.raise_for_status()
        response.raise_for_status()
        full_item = response.json()
        return full_item.get('shipmentorder', None)
    except Exception as e:
        logger.error(f"Error fetching details for shipment {item['shipment_id']}: {e}")
        raise
        # return None
    

@api_view(['POST'])
@permission_classes([AllowAny])
def load_inventory_shipments(request):
    MAX_WORKERS = 5
    app_config = AppConfig.objects.first()
    logger.debug(app_config)
    try:
        headers = config_headers()
    except Exception as e:
        logger.error(f"Error connecting to Zoho API: {str(e)}")
        return JsonResponse({'error': f"Error connecting to Zoho API (Load Shipments): {str(e)}"}, status=500)

    data = json.loads(request.body)
    start_date = data.get('start_date', None)
    end_date = data.get('end_date', None)
    username = data.get('username', None)
    
    logger.debug(f"Start date: {start_date}, End date: {end_date}")
    
    try:
        if start_date:
            dt.strptime(start_date, '%Y-%m-%d')
        if end_date:
            dt.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        logger.error('Invalid date format')
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    params = {
        'organization_id': app_config.zoho_org_id,
        'per_page': 200,
        'page': 1,
    }
    if end_date and start_date:
        params.update({'date_start': start_date, 'date_end': end_date})
    elif start_date:
        params['date'] = start_date

    url = settings.ZOHO_INVENTORY_SHIPMENTS_URL
    items_to_get = []
    session = requests.Session()
    
    while True:
        try:
            response = session.get(url, headers=headers, params=params)
            if response.status_code == 401:
                new_token = refresh_zoho_access_token()
                headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                response = session.get(url, headers=headers, params=params)
            if response.status_code >= 400:
                logger.error(f"Error fetching shipments: {response.text}")
                return JsonResponse({'error': 'Failed to fetch shipments'}, status=500)
            items = response.json()
            items_to_get.extend(items.get('shipmentorders', []))
            if not items.get('page_context', {}).get('has_more_page', False):
                break
            params['page'] += 1
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching shipments: {e}")
            return JsonResponse({'error': 'Failed to fetch shipments'}, status=500)
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_shipment_details, item, session, headers) for item in items_to_get]
        full_items_to_get = [future.result() for future in as_completed(futures) if future.result()]
    
    all_package_ids = []
    for data_item in full_items_to_get:
        pkg_info = data_item.get('packages', [])
        if pkg_info:
            package_ids = [pkg.get('package_id') for pkg in pkg_info if pkg.get('package_id')]
            all_package_ids.extend(package_ids)
    
    all_package_ids = list(set(all_package_ids))
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_package_id = {executor.submit(fetch_package, pkg_id, session, headers): pkg_id for pkg_id in all_package_ids}
        all_packages_data = []
        for future in as_completed(future_to_package_id):
            pkg_id = future_to_package_id[future]
            try:
                pkg_data = future.result()
                if pkg_data:
                    all_packages_data.append(pkg_data)
            except Exception as exc:
                logger.error(f"Error fetching package {pkg_id}: {exc}")
    
    existing_packages = ZohoPackage.objects(Q(package_id__in=all_package_ids))
    existing_packages_ids = set(existing_packages.distinct('package_id'))
    
    new_packages = []
    packages_to_update = []
    for pkg_data in all_packages_data:
        new_pkg = create_inventory_package_instance(logger, pkg_data)
        if new_pkg and new_pkg.package_id in existing_packages_ids:
            packages_to_update.append(new_pkg)
        elif new_pkg:
            new_packages.append(new_pkg)
    
    shipments_ids = [item['shipment_id'] for item in full_items_to_get if item.get('shipment_id')]
    existing_shipments = ZohoShipmentOrder.objects(Q(shipment_id__in=shipments_ids))
    existing_shipments_ids = set(existing_shipments.distinct('shipment_id'))

    new_shipments = []
    shipments_to_update = []
    for data_item in full_items_to_get:
        new_item = create_inventory_shipment_instance(logger, data_item)
        if new_item and new_item.shipment_id in existing_shipments_ids:
            shipments_to_update.append(new_item)
        elif new_item:
            new_shipments.append(new_item)
    
    logger.info(f"New shipments: {len(new_shipments)}, Shipments to update: {len(shipments_to_update)}")
    
    
    if new_shipments:
        ZohoShipmentOrder.objects.insert(new_shipments, load_bulk=False)
    if shipments_to_update:
        for shipment in shipments_to_update:
            obj = ZohoShipmentOrder.objects(shipment_id=shipment.shipment_id).first()
            if obj:
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
                    obj.is_email_notification_enabled = shipment.is_email_notification_enabled
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
                    obj.save()
    if new_packages:
        ZohoPackage.objects.insert(new_packages, load_bulk=False)
    if packages_to_update:
        for package in packages_to_update:
            obj = ZohoPackage.objects(package_id=package.package_id).first()
            if obj:
                    obj.salesorder_id = package.salesorder_id
                    obj.salesorder_number = package.salesorder_number
                    obj.salesorder_date = package.salesorder_date
                    obj.sales_channel = package.sales_channel
                    obj.sales_channel_formatted = package.sales_channel_formatted
                    obj.salesorder_fulfilment_status = package.salesorder_fulfilment_status
                    obj.shipment_id = package.shipment_id
                    obj.shipment_number = package.shipment_number
                    obj.shipment_order = package.shipment_order
                    obj.package_number = package.package_number
                    obj.date = package.date
                    obj.shipping_date = package.shipping_date
                    obj.delivery_method = package.delivery_method
                    obj.delivery_method_id = package.delivery_method_id
                    obj.tracking_number = package.tracking_number
                    obj.tracking_link = package.tracking_link
                    obj.expected_delivery_date = package.expected_delivery_date
                    obj.shipment_delivered_date = package.shipment_delivered_date
                    obj.status = package.status
                    obj.detailed_status = package.detailed_status
                    obj.status_message = package.status_message
                    obj.carrier = package.carrier
                    obj.service = package.service
                    obj.delivery_days = package.delivery_days
                    obj.delivery_guarantee = package.delivery_guarantee
                    obj.total_quantity = package.total_quantity
                    obj.customer_id = package.customer_id
                    obj.customer_name = package.customer_name
                    obj.email = package.email
                    obj.phone = package.phone
                    obj.mobile = package.mobile
                    obj.contact_persons = package.contact_persons
                    obj.created_by_id = package.created_by_id
                    obj.last_modified_by_id = package.last_modified_by_id
                    obj.created_time = package.created_time
                    obj.last_modified_time = package.last_modified_time
                    obj.notes = package.notes
                    obj.terms = package.terms
                    obj.is_emailed = package.is_emailed
                    obj.is_advanced_tracking_missing = package.is_advanced_tracking_missing
                    obj.line_items = package.line_items
                    obj.custom_fields = package.custom_fields
                    obj.custom_field_hash = package.custom_field_hash
                    obj.shipmentorder_custom_fields = package.shipmentorder_custom_fields
                    obj.billing_address = package.billing_address
                    obj.shipping_address = package.shipping_address
                    obj.picklists = package.picklists
                    obj.template_id = package.template_id
                    obj.template_name = package.template_name
                    obj.template_type = package.template_type
                    obj.zoho_shipment = package.zoho_shipment
                    obj.save()
                    
    # previous_day = timezone.now()
    
    # JobsUpdatingTimes.objects(last_updated__lt=previous_day).delete()
            
    # JobsUpdatingTimes.objects.create(last_updated=timezone.now())
    
    # if username:
    #     module='zoho_shipment'
    #     info='has loaded new info from Zoho Shipments'
    #     type='load'
    #     create_notification(module, info, type, username)
            
    logger.info(f"Shipments processed successfully: {len(new_shipments)} created, {len(shipments_to_update)} updated")
    
    return JsonResponse({'message': 'Shipments loaded successfully'}, status=200)


#############################################
# LOAD BOOKS CUSTOMERS
#############################################

CONCURRENT_WORKERS = 50

def fetch_customers_from_api(headers, params, last_sync_date):
    customers_to_get = []
    url = f'{settings.ZOHO_BOOKS_CUSTOMERS_URL}'
    
    if last_sync_date.tzinfo is None:
        last_sync_date = last_sync_date.replace(tzinfo=tz.utc)

    while True:
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 401:
                new_token = refresh_zoho_access_token()
                headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                response = requests.get(url, headers=headers, params=params)
            if response.status_code != 200:
                logger.error(f"Error fetching customers: {response.text}")
                break
            response.raise_for_status()
            customers = response.json()
            recent_contacts = [
                contact for contact in customers.get('contacts', [])
                if dt.strptime(contact['last_modified_time'], '%Y-%m-%dT%H:%M:%S%z') > last_sync_date
            ]
            if recent_contacts:
                customers_to_get.extend(recent_contacts)
            if customers.get('page_context', {}).get('has_more_page', False):
                params['page'] += 1
            else:
                break
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching customers: {e}")
            break
    return customers_to_get

def process_customers_concurrently(customers_to_get):
    customers_ids = [item['contact_id'] for item in customers_to_get if item.get('contact_id')]
    existing_customers = ZohoCustomer.objects(Q(contact_id__in=customers_ids))
    existing_customers_ids = set(existing_customers.distinct('contact_id'))

    new_customers = []
    customers_to_update = []

    def process_customer(data_item):
        new_item = create_books_customers_instance(logger, data_item)
        if new_item and new_item.contact_id in existing_customers_ids:
            customers_to_update.append(new_item)
        elif new_item:
            new_customers.append(new_item)

    with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
        futures = [executor.submit(process_customer, item) for item in customers_to_get]
        for future in as_completed(futures):
            future.result()

    if new_customers:
        ZohoCustomer.objects.insert(new_customers, load_bulk=False)

    if customers_to_update:
        for customer in customers_to_update:
            obj = ZohoCustomer.objects(contact_id=customer.contact_id).first()
            if obj:
                for field, value in customer.to_mongo().to_dict().items():
                    if field != '_id':
                        setattr(obj, field, value)
                obj.save()

@api_view(['POST'])
@permission_classes([AllowAny])
def load_books_customers(request):
    app_config = AppConfig.objects.first()
    try:
        headers = config_headers()
    except Exception as e:
        logger.error(f"Error connecting to Zoho API: {str(e)}")
        return JsonResponse({'error': f"Error connecting to Zoho API: {str(e)}"}, status=500)

    params = {
        'page': 1,
        'per_page': 200,
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

    customers_to_get = fetch_customers_from_api(headers, params, last_sync_date)
    process_customers_concurrently(customers_to_get)
    
    date_str = timezone.now().strftime("%Y-%m-%d")
    SyncMetadata.update_last_sync_date('last_sync_date_customers', date_str)

    logger.info(f"Customers processed successfully: {len(customers_to_get)}")
    return JsonResponse({'message': 'Customers loaded successfully'}, status=200)


#############################################
# LOAD BOOKS CUSTOMERS DETAILS
#############################################

CONCURRENT_WORKERS = 10
CALLS_PER_MINUTE = 100
RETRY_LIMIT = 3
BATCH_SIZE = 100

rate_limit_lock = Lock()
rate_limit_counter = 0
semaphore = Semaphore(CALLS_PER_MINUTE)


def fetch_customer_details(contact_id, headers):
    app_config = AppConfig.objects.first()
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
                    new_token = refresh_zoho_access_token()
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


def process_customers_in_batches(customers_ids, headers):
    results = []

    def process_customer(contact_id):
        return fetch_customer_details(contact_id, headers)

    with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
        futures = {executor.submit(process_customer, contact_id): contact_id for contact_id in customers_ids}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    return results


def load_books_customers_details():
    try:
        headers = config_headers()
    except Exception as e:
        logger.error(f"Error connecting to Zoho API: {str(e)}")
        return JsonResponse({'error': f"Error connecting to Zoho API: {str(e)}"}, status=500)

    customers = ZohoCustomer.objects.all()
    customers_ids = list(customers.distinct('contact_id'))

    all_results = []
    for i in range(0, len(customers_ids), BATCH_SIZE):
        batch = customers_ids[i:i + BATCH_SIZE]
        results = process_customers_in_batches(batch, headers)
        all_results.extend(results)

    for result in all_results:
        new_item = create_books_customers_instance(logger, result)
        if new_item:
            ZohoCustomer.objects(contact_id=new_item.contact_id).update_one(**new_item.to_mongo().to_dict(), upsert=True)

    logger.info(f"Customers details processed successfully: {len(all_results)}")
    return JsonResponse({'message': 'Customers details loaded successfully'}, status=200)


# @api_view(['POST'])
# @permission_classes([AllowAny])
# def load_books_customers(request):
#     app_config = AppConfig.objects.first()
#     username = request.data.get('username', '')
#     try:
#         headers = config_headers() 
#     except Exception as e:
#         logger.error(f"Error connecting to Zoho API: {str(e)}")
#         return JsonResponse({'error': f"Error connecting to Zoho API (Load Customers): {str(e)}"}, status=500)

#     params = {
#         'page': 1,
#         'per_page': 200, 
#         'organization_id': app_config.zoho_org_id,
#     } 
        
#     url = f'{settings.ZOHO_BOOKS_CUSTOMERS_URL}'
#     customers_to_get = []

#     while True:
#         try:
#             response = requests.get(url, headers=headers, params=params)
#             if response.status_code == 401:  
#                 new_zoho_token = refresh_zoho_access_token()()
#                 headers['Authorization'] = f'Zoho-oauthtoken {new_zoho_token}'
#                 response = requests.get(url, headers=headers, params=params) 
#             elif response.status_code != 200:
#                 logger.error(f"Error fetching customers: {response.text}")
#                 return {'error': response.text, 'status_code': response.status_code}
#             else:
#                 response.raise_for_status()
#                 customers = response.json()
#                 if customers.get('contacts', []):
#                     customers_to_get.extend(customers['contacts'])
#                 if 'page_context' in customers and 'has_more_page' in customers['page_context'] and customers['page_context']['has_more_page']:
#                     params['page'] += 1 
#                 else:
#                     break 
#         except requests.exceptions.RequestException as e:
#             logger.error(f"Error fetching customers: {e}")
#             return {"error": "Failed to fetch customers", "status": 500}
    
#     customers_ids = [item['contact_id'] for item in customers_to_get if item.get('contact_id')]
#     existing_customers = ZohoCustomer.objects(Q(contact_id__in=customers_ids))
#     existing_customers_ids = set(existing_customers.distinct('contact_id'))

#     new_customers = []
#     customers_to_update = []
#     for data_item in customers_to_get:
        
#         new_item = create_books_customers_instance(logger, data_item)
#         if new_item and new_item.contact_id in existing_customers_ids:
#             customers_to_update.append(new_item)
#         elif new_item:
#             new_customers.append(new_item)
    
#     logger.info(f"New Customers: {len(new_customers)}, Customers to update: {len(customers_to_update)}")
    
#     if new_customers:
#         ZohoCustomer.objects.insert(new_customers, load_bulk=False)
#     if customers_to_update:
#         for customer in customers_to_update:
#             obj = ZohoCustomer.objects(contact_id=customer.contact_id).first()
#             if obj:
#                 obj.contact_id = customer.contact_id
#                 obj.contact_name = customer.contact_name
#                 obj.customer_name = customer.customer_name
#                 obj.company_name = customer.company_name
#                 obj.status = customer.status
#                 obj.first_name = customer.first_name
#                 obj.last_name = customer.last_name
#                 obj.email = customer.email
#                 obj.phone = customer.phone
#                 obj.mobile = customer.mobile
#                 obj.created_time = customer.created_time
#                 obj.created_time_formatted = customer.created_time_formatted
#                 obj.last_modified_time = customer.last_modified_time
#                 obj.last_modified_time_formatted = customer.last_modified_time_formatted
#                 obj.qb_list_id = customer.qb_list_id
#                 obj.contact_type=customer.contact_type,
#                 obj.has_transaction=customer.has_transaction,
#                 obj.is_linked_with_zohocrm=customer.is_linked_with_zohocrm,
#                 obj.website=customer.website,
#                 obj.primary_contact_id=customer.primary_contact_id,
#                 obj.payment_terms=customer.payment_terms,
#                 obj.payment_terms_label=customer.payment_terms_label,
#                 obj.currency_id=customer.currency_id,
#                 obj.currency_code=customer.currency_code,
#                 obj.currency_symbol=customer.currency_symbol,
#                 obj.outstanding_receivable_amount=customer.outstanding_receivable_amount,
#                 obj.outstanding_receivable_amount_bcy=customer.outstanding_receivable_amount_bcy,
#                 obj.unused_credits_receivable_amount=customer.unused_credits_receivable_amount,
#                 obj.unused_credits_receivable_amount_bcy=customer.unused_credits_receivable_amount_bcy,
#                 obj.facebook=customer.facebook,
#                 obj.twitter=customer.twitter,
#                 obj.payment_remainder_enabled=customer.payment_remainder_enabled,
#                 obj.notes=customer.notes,
#                 obj.is_taxable=customer.is_taxable,
#                 obj.tax_id=customer.tax_id,
#                 obj.tax_name=customer.tax_name,
#                 obj.tax_percentage=customer.tax_percentage,
#                 obj.tax_authority_id=customer.tax_authority_id,
#                 obj.tax_exemption_id=customer.tax_exemption_id,
#                 obj.tax_authority_name=customer.tax_authority_name,
#                 obj.tax_exemption_code=customer.tax_exemption_code,
#                 obj.place_of_contact=customer.place_of_contact,
#                 obj.gst_no=customer.gst_no,
#                 obj.tax_treatment=customer.tax_treatment,
#                 obj.tax_regime=customer.tax_regime,
#                 obj.legal_name=customer.legal_name,
#                 obj.is_tds_applicable=customer.is_tds_applicable,
#                 obj.vst_treatment=customer.vst_treatment,
#                 obj.gst_treatment=customer.gst_treatment,
#                 obj.custom_fields=customer.custom_fields,
#                 obj.billing_address=customer.billing_address,
#                 obj.shipping_address=customer.shipping_address,
#                 obj.contact_persons=customer.contact_persons,
#                 obj.default_templates=customer.default_templates,
#                 obj.save()
            
#     logger.info(f"Customers processed successfully: {len(new_customers)} created, {len(customers_to_update)} updated")
    
#     return JsonResponse({'message': 'Customers loaded successfully'}, status=200)


#############################################
# LOAD BOOKS INVOICES
#############################################

@api_view(['POST'])
@permission_classes([AllowAny])
def load_books_invoices(request):
    if request:
        app_config = AppConfig.objects.first()
        try:
            headers = config_headers()
        except Exception as e:
            logger.error(f"Error connecting to Zoho API: {str(e)}")
            return JsonResponse({'error': f"Error connecting to Zoho API: {str(e)}"}, status=500)
        
        data = json.loads(request.body)
        date_to_query = data.get('start_date', None)
        username = data.get('username', None)
        if not date_to_query:
            date_to_query = dt.today().strftime('%Y-%m-%d')
        

        params = {
            'organization_id': app_config.zoho_org_id,
            'page': 1,
            'per_page': 200,
            'date_start': date_to_query,
            'date_end': date_to_query
        }
        
        url = f'{settings.ZOHO_BOOKS_INVOICES_URL}'
        invoice_ids = fetch_invoices(url, headers, params)
        if invoice_ids is None:
            return JsonResponse({"error": "Failed to fetch invoices"}, status=500)
        
        invoices_to_save = fetch_full_invoices_parallel(invoice_ids, headers)

        process_and_save_fetched_invoices(invoices_to_save)

        return JsonResponse({'message': 'Invoices loaded successfully'}, status=200)

    return JsonResponse({'error': 'Invalid request'}, status=400)


def fetch_invoices(url, headers, params):
    invoice_ids = []
    while True:
        try:
            response = requests.get(url, headers=headers, params=params, timeout=180)
            if response.status_code == 401:
                headers['Authorization'] = f'Zoho-oauthtoken {refresh_zoho_access_token()}'
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


def fetch_full_invoices_parallel(invoice_ids, headers, max_workers=10):
    invoices_data = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_invoice = {executor.submit(fetch_full_invoice, invoice_id, headers): invoice_id for invoice_id in invoice_ids}
        for future in as_completed(future_to_invoice):
            invoice_data = future.result()
            if invoice_data:
                invoices_data.append(invoice_data)
    return invoices_data


def fetch_full_invoice(invoice_id, headers):
    get_url = f'{settings.ZOHO_BOOKS_INVOICES_URL}/{invoice_id}/?organization_id={AppConfig.objects.first().zoho_org_id}'
    try:
        response = requests.get(get_url, headers=headers, timeout=180)
        if response.status_code == 200:
            return response.json().get('invoice')
        else:
            logger.error(f"Error fetching full invoice {invoice_id}: {response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching full invoice {invoice_id}: {e}")
    return None


def process_and_save_fetched_invoices(invoices_to_get):
    invoices_ids = [item['invoice_id'] for item in invoices_to_get if item.get('invoice_id')]
    existing_invoices = ZohoFullInvoice.objects(Q(invoice_id__in=invoices_ids))
    existing_invoices_ids = set(existing_invoices.distinct('invoice_id'))

    new_invoices = []
    invoices_to_update = []
    for data_item in invoices_to_get:
        new_invoice = create_books_invoice_instance(logger, data_item)
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
                obj.save()
    return new_invoices, invoices_to_update
            
    
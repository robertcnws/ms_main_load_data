from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from ms_load_from_zoho.service_sales_orders import fetch_sales_order_details
from mongoengine import Q
from datetime import datetime as dt
from django.http import JsonResponse
from django.conf import settings
from django.http import JsonResponse
from threading import Semaphore, Lock
from .models import (
                      AppConfig,
                      ZohoFullInvoice,
                      ZohoInventoryShipmentSalesOrder,
                      ZohoCustomer,
                    )

from .manage_instances import (
                                create_books_invoice_instance,
                                create_inventory_sales_order_instance,
                                create_books_customers_instance,
                             )

import json
import requests
import logging
import time
import ms_load_from_zoho.helpers as helpers


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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
            time.sleep(float(os.getenv("ZOHO_LIST_PAGE_DELAY_SEC", "1")))
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
            time.sleep(float(os.getenv("ZOHO_LIST_PAGE_DELAY_SEC", "1")))
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
            time.sleep(float(os.getenv("ZOHO_LIST_PAGE_DELAY_SEC", "1")))
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
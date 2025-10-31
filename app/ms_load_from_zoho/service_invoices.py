from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from ms_load_from_zoho.service_shipments import _now_iso, _set_metrics
from mongoengine import Q
from datetime import datetime as dt, timedelta
from django.http import JsonResponse
from django.conf import settings
from django.http import JsonResponse
from .models import (
                      AppConfig,
                      ZohoFullInvoice,
                      SyncMetadata,
                    )

from .manage_instances import (
                                create_books_invoice_instance,
                             )

import json
import requests
import logging
import time
import ms_load_from_zoho.helpers as helpers


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def load_invoices_service(start_date, zoho_org_id):
    t0 = time.time()
    list_calls = detail_calls = 0
    created = updated = 0
    status = 'ok'
    
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
    
    date_to_query = start_date or dt.today().strftime('%Y-%m-%d')

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
            time.sleep(float(os.getenv("ZOHO_LIST_PAGE_DELAY_SEC", "1")))
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
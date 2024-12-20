from datetime import datetime as dt
from django.utils import timezone
from mongoengine import DoesNotExist, ValidationError
from .models import (
                        ZohoInventoryItem,
                        ZohoInventoryShipmentSalesOrder,
                        ZohoShipmentOrder,
                        ZohoPackage,
                        ZohoCustomer,
                    )  

def create_inventory_item_instance(logger, data):
    current_timezone = timezone.get_current_timezone()
    
    created_time_str = data.get('created_time')
    created_time = dt.strptime(created_time_str, '%Y-%m-%dT%H:%M:%S%z') if created_time_str else None
    if created_time and created_time.tzinfo is None:
        created_time = current_timezone.localize(created_time)
    
    last_modified_time_str = data.get('last_modified_time')
    last_modified_time = dt.strptime(last_modified_time_str, '%Y-%m-%dT%H:%M:%S%z') if last_modified_time_str else None
    if last_modified_time and last_modified_time.tzinfo is None:
        last_modified_time = current_timezone.localize(last_modified_time)

    item_id = data.get('item_id', '')
    
    defaults = {
        'group_id': data.get('group_id', 0),
        'group_name': data.get('group_name', ''),
        'name': data.get('name', ''),
        'status': data.get('status', ''),
        'source': data.get('source', ''),
        'is_linked_with_zohocrm': data.get('is_linked_with_zohocrm', False),
        'item_type': data.get('item_type', ''),
        'description': data.get('description', ''),
        'rate': data.get('rate', 0),
        'is_taxable': data.get('is_taxable', False),
        'tax_id': data.get('tax_id') if isinstance(data.get('tax_id'), (int, float)) else 0,
        'tax_name': data.get('tax_name', ''),
        'tax_percentage': data.get('tax_percentage', 0),
        'purchase_description': data.get('purchase_description', ''),
        'purchase_rate': data.get('purchase_rate', 0),
        'is_combo_product': data.get('is_combo_product', False),
        'product_type': data.get('product_type', ''),
        'attribute_id1': data.get('attribute_id1') if isinstance(data.get('attribute_id1'), (int, float)) else 0,
        'attribute_name1': data.get('attribute_name1', ''),
        'reorder_level': data.get('reorder_level') if isinstance(data.get('reorder_level'), (int, float)) else 0,
        'stock_on_hand': data.get('stock_on_hand', 0),
        'available_stock': data.get('available_stock', 0),
        'actual_available_stock': data.get('actual_available_stock', 0),
        'sku': data.get('sku', ''),
        'upc': data.get('upc') if isinstance(data.get('upc'), (int, float)) else 0,
        'ean': data.get('ean') if isinstance(data.get('ean'), (int, float)) else 0,
        'isbn': data.get('isbn') if isinstance(data.get('isbn'), (int, float)) else 0,
        'part_number': data.get('part_number') if isinstance(data.get('part_number'), (int, float)) else 0,
        'attribute_option_id1': data.get('attribute_option_id1') if isinstance(data.get('attribute_option_id1'), (int, float)) else 0,
        'attribute_option_name1': data.get('attribute_option_name1', ''),
        'image_name': data.get('image_name', ''),
        'image_type': data.get('image_type', ''),
        'created_time': created_time,
        'last_modified_time': last_modified_time,
        'hsn_or_sac': data.get('hsn_or_sac') if isinstance(data.get('hsn_or_sac'), (int, float)) else 0,
        'sat_item_key_code': data.get('sat_item_key_code', ''),
        'unitkey_code': data.get('unitkey_code', ''),
    }
    
    existing_item = ZohoInventoryItem.objects(item_id=item_id).first()

    if existing_item:
        for field, value in defaults.items():
            setattr(existing_item, field, value)
        return existing_item
    else:
        new_item = ZohoInventoryItem(item_id=item_id, **defaults)
        return new_item
    

# ----------------------------------------------------------

def create_inventory_sales_order_instance(logger, data):
    
    current_timezone = timezone.get_current_timezone()
    
    date_str = data.get('date', None)
    date = dt.strptime(date_str, '%Y-%m-%d').date() if date_str else None
    
    created_time_str = data.get('created_time', None)
    created_time = dt.strptime(created_time_str, '%Y-%m-%dT%H:%M:%S%z') if created_time_str else None
    
    if created_time and created_time.tzinfo is None:
        created_time = current_timezone.localize(created_time)
    
    last_modified_time_str = data.get('last_modified_time', None)
    last_modified_time = dt.strptime(last_modified_time_str, '%Y-%m-%dT%H:%M:%S%z') if last_modified_time_str else None
    
    if last_modified_time and last_modified_time.tzinfo is None:
        last_modified_time = current_timezone.localize(last_modified_time)
    
    salesorder_id = data.get('salesorder_id', '')
    salesorder_number = data.get('salesorder_number', '')
    status = data.get('status', '')
    customer_id = data.get('customer_id', '')
    customer_name = data.get('customer_name', '')
    is_taxable = data.get('is_taxable', True)
    tax_id = data.get('tax_id', '')
    tax_name = data.get('tax_name', '')
    tax_percentage = data.get('tax_percentage', 0.0)
    currency_id = data.get('currency_id', '')
    currency_code = data.get('currency_code', '')
    currency_symbol = data.get('currency_symbol', '')
    exchange_rate = data.get('exchange_rate', 1.0)
    delivery_method = data.get('delivery_method', '')
    total_quantity = data.get('total_quantity', 0.0)
    sub_total = data.get('sub_total', 0.0)
    tax_total = data.get('tax_total', 0.0)
    total = data.get('total', 0.0)
    created_by_email = data.get('created_by_email', '')
    created_by_name = data.get('created_by_name', '')
    salesperson_id = data.get('salesperson_id', '')
    salesperson_name = data.get('salesperson_name', '')
    is_test_order = data.get('is_test_order', False)
    notes = data.get('notes', '')
    payment_terms = data.get('payment_terms', 0)
    payment_terms_label = data.get('payment_terms_label', '')

    # JSON Fields
    line_items = data.get('line_items', [])
    shipping_address = data.get('shipping_address', {})
    billing_address = data.get('billing_address', {})
    warehouses = data.get('warehouses', [])
    custom_fields = data.get('custom_fields', [])
    order_sub_statuses = data.get('order_sub_statuses', [])
    shipment_sub_statuses = data.get('shipment_sub_statuses', [])
    
    if not salesorder_id:
        logger.error("Missing salesorder_id")
        return None
    
    sales_order = ZohoInventoryShipmentSalesOrder(
        salesorder_id=salesorder_id,
        salesorder_number=salesorder_number,
        date=date,
        status=status,
        customer_id=customer_id,
        customer_name=customer_name,
        is_taxable=is_taxable,
        tax_id=tax_id,
        tax_name=tax_name,
        tax_percentage=tax_percentage,
        currency_id=currency_id,
        currency_code=currency_code,
        currency_symbol=currency_symbol,
        exchange_rate=exchange_rate,
        delivery_method=delivery_method,
        total_quantity=total_quantity,
        sub_total=sub_total,
        tax_total=tax_total,
        total=total,
        created_by_email=created_by_email,
        created_by_name=created_by_name,
        salesperson_id=salesperson_id,
        salesperson_name=salesperson_name,
        is_test_order=is_test_order,
        notes=notes,
        payment_terms=payment_terms,
        payment_terms_label=payment_terms_label,
        line_items=line_items,
        shipping_address=shipping_address,
        billing_address=billing_address,
        warehouses=warehouses,
        custom_fields=custom_fields,
        order_sub_statuses=order_sub_statuses,
        shipment_sub_statuses=shipment_sub_statuses,
        created_time=created_time,
        last_modified_time=last_modified_time,
    )
    
    return sales_order


def create_inventory_shipment_instance(logger, data):
    
    current_timezone = timezone.get_current_timezone()
    
    def parse_datetime(datetime_str):
        if not datetime_str:
            return None
        for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S%z'):
            try:
                return dt.strptime(datetime_str, fmt)
            except ValueError:
                continue
        logger.error(f"Invalid datetime format: {datetime_str}")
        return None
    
    created_time_str = data.get('created_time', dt.now().strftime('%Y-%m-%dT%H:%M:%S%z'))
    created_time = parse_datetime(created_time_str)

    if created_time and created_time.tzinfo is None:
        created_time = current_timezone.localize(created_time)
    elif created_time and created_time.tzinfo is not None:
        created_time = created_time.astimezone(current_timezone)
    
    last_modified_time_str = data.get('last_modified_time', dt.now().strftime('%Y-%m-%dT%H:%M:%S%z'))
    last_modified_time = parse_datetime(last_modified_time_str)

    if last_modified_time and last_modified_time.tzinfo is None:
        last_modified_time = current_timezone.localize(last_modified_time)
    elif last_modified_time and last_modified_time.tzinfo is not None:
        last_modified_time = last_modified_time.astimezone(current_timezone)
    
    salesorder_date_str = data.get('salesorder_date', None)
    salesorder_date = dt.strptime(salesorder_date_str, '%Y-%m-%d') if salesorder_date_str else None

    if salesorder_date:
        salesorder_date = timezone.make_aware(dt.combine(salesorder_date, dt.min.time()), timezone=current_timezone)

    date_str = data.get('date', None)
    date = dt.strptime(date_str, '%Y-%m-%d') if date_str else None

    if date:
        date = timezone.make_aware(dt.combine(date, dt.min.time()), timezone=current_timezone)

    shipment_id = data.get('shipment_id', '')
    salesorder_id=data.get('salesorder_id', '')
    salesorder_number=data.get('salesorder_number', '')
    salesorder_date=salesorder_date
    salesorder_fulfilment_status=data.get('salesorder_fulfilment_status', '')
    sales_channel=data.get('sales_channel', '')
    sales_channel_formatted=data.get('sales_channel_formatted', '')
    shipment_number=data.get('shipment_number', '')
    date=date
    shipment_status=data.get('shipment_status', '')
    shipment_sub_status=data.get('shipment_sub_status', '')
    status=data.get('status', '')
    detailed_status=data.get('detailed_status', '')
    status_message=data.get('status_message', '')
    carrier=data.get('carrier', '')
    tracking_carrier_code=data.get('tracking_carrier_code', '')
    service=data.get('service', '')
    delivery_days=data.get('delivery_days', '')
    source_id=data.get('source_id', '')
    label_format=data.get('label_format', '')
    source_name=data.get('source_name', '')
    delivery_guarantee=data.get('delivery_guarantee', False)
    reference_number=data.get('reference_number', '')
    customer_id=data.get('customer_id', '')
    customer_name=data.get('customer_name', '')
    is_taxable=data.get('is_taxable', True)
    tax_id=data.get('tax_id', '')
    tax_name=data.get('tax_name', '')
    tax_percentage=data.get('tax_percentage', 0)
    currency_id=data.get('currency_id', '')
    currency_code=data.get('currency_code', '')
    currency_symbol=data.get('currency_symbol', '')
    exchange_rate=data.get('exchange_rate', 1)
    discount=data.get('discount', 0)
    is_discount_before_tax=data.get('is_discount_before_tax', False)
    discount_type=data.get('discount_type', '')
    estimate_id=data.get('estimate_id', '')
    delivery_method=data.get('delivery_method', '')
    delivery_method_id=data.get('delivery_method_id', '')
    tracking_number=data.get('tracking_number', '')
    tracking_link=data.get('tracking_link', '')
    last_tracking_update_date=data.get('last_tracking_update_date', '')
    expected_delivery_date=data.get('expected_delivery_date', '')
    shipment_delivered_date=data.get('shipment_delivered_date', '')
    shipment_type=data.get('shipment_type', '')
    is_carrier_shipment=data.get('is_carrier_shipment', False)
    is_tracking_enabled=data.get('is_tracking_enabled', False)
    is_forms_available=data.get('is_forms_available', False)
    is_email_notification_enabled=data.get('is_email_notification_enabled', False)
    shipping_charge=data.get('shipping_charge', 0)
    sub_total=data.get('sub_total', 0)
    tax_total=data.get('tax_total', 0)
    total=data.get('total', 0)
    price_precision=data.get('price_precision', 0)
    is_emailed=data.get('is_emailed', False)
    notes=data.get('notes', '')
    template_id=data.get('template_id', '')
    template_name=data.get('template_name', '')
    template_type=data.get('template_type', '')
    created_time=created_time
    last_modified_time=last_modified_time
    associated_packages_count=data.get('associated_packages_count', 0)
    created_by_id=data.get('created_by_id', '')
    last_modified_by_id=data.get('last_modified_by_id', '')
    contact_persons=data.get('contact_persons', [])
    invoices=data.get('invoices', [])
    line_items=data.get('line_items', [])
    packages=data.get('packages', [])
    billing_address=data.get('billing_address', {})
    shipping_address=data.get('shipping_address', {})
    custom_fields=data.get('custom_fields', [])
    custom_field_hash=data.get('custom_field_hash', {})
    documents=data.get('documents', [])
    taxes=data.get('taxes', [])
    tracking_statuses=data.get('tracking_statuses', [])
    multipiece_shipments=data.get('multipiece_shipments', [])
    
    if not shipment_id:
        logger.error("Missing shipment_id")
        return None
    
    shipment = ZohoShipmentOrder(
        shipment_id=shipment_id,
        salesorder_id=salesorder_id,
        salesorder_number=salesorder_number,
        salesorder_date=salesorder_date,
        salesorder_fulfilment_status=salesorder_fulfilment_status,
        sales_channel=sales_channel,
        sales_channel_formatted=sales_channel_formatted,
        shipment_number=shipment_number,
        date=date,
        shipment_status=shipment_status,
        shipment_sub_status=shipment_sub_status,
        status=status,
        detailed_status=detailed_status,
        status_message=status_message,
        carrier=carrier,
        tracking_carrier_code=tracking_carrier_code,
        service=service,
        delivery_days=delivery_days,
        source_id=source_id,
        label_format=label_format,
        source_name=source_name,
        delivery_guarantee=delivery_guarantee,
        reference_number=reference_number,
        customer_id=customer_id,
        customer_name=customer_name,
        is_taxable=is_taxable,
        tax_id=tax_id,
        tax_name=tax_name,
        tax_percentage=tax_percentage,
        currency_id=currency_id,
        currency_code=currency_code,
        currency_symbol=currency_symbol,
        exchange_rate=exchange_rate,
        discount=discount,
        is_discount_before_tax=is_discount_before_tax,
        discount_type=discount_type,
        estimate_id=estimate_id,
        delivery_method=delivery_method,
        delivery_method_id=delivery_method_id,
        tracking_number=tracking_number,
        tracking_link=tracking_link,
        last_tracking_update_date=last_tracking_update_date,
        expected_delivery_date=expected_delivery_date,
        shipment_delivered_date=shipment_delivered_date,
        shipment_type=shipment_type,
        is_carrier_shipment=is_carrier_shipment,
        is_tracking_enabled=is_tracking_enabled,
        is_forms_available=is_forms_available,
        is_email_notification_enabled=is_email_notification_enabled,
        shipping_charge=shipping_charge,
        sub_total=sub_total,
        tax_total=tax_total,
        total=total,
        price_precision=price_precision,
        is_emailed=is_emailed,
        notes=notes,
        template_id=template_id,
        template_name=template_name,
        template_type=template_type,
        created_time=created_time,
        last_modified_time=last_modified_time,
        associated_packages_count=associated_packages_count,
        created_by_id=created_by_id,
        last_modified_by_id=last_modified_by_id,
        contact_persons=contact_persons,
        invoices=invoices,
        line_items=line_items,
        packages=packages,
        billing_address=billing_address,
        shipping_address=shipping_address,
        custom_fields=custom_fields,
        custom_field_hash=custom_field_hash,
        documents=documents,
        taxes=taxes,
        tracking_statuses=tracking_statuses,
        multipiece_shipments=multipiece_shipments,
    )

    return shipment


def create_inventory_package_instance(logger, data, zoho_shipment=None):
    current_timezone = timezone.get_current_timezone()
    
    def parse_date(date_str):
        if date_str:
            try:
                return dt.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                logger.error(f"Invalid date format: {date_str}")
        return None

    def parse_datetime(datetime_str):
        if datetime_str:
            try:
                return dt.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S%z')
            except ValueError:
                logger.error(f"Invalid datetime format: {datetime_str}")
        return None
    
    salesorder_date = parse_date(data.get('salesorder_date'))
    date = parse_date(data.get('date'))
    shipping_date = parse_date(data.get('shipping_date'))
    created_time = parse_datetime(data.get('created_time'))
    last_modified_time = parse_datetime(data.get('last_modified_time'))

    if created_time:
        created_time = created_time.astimezone(current_timezone)
    else:
        created_time = timezone.now()

    if last_modified_time:
        last_modified_time = last_modified_time.astimezone(current_timezone)
    else:
        last_modified_time = timezone.now()
    
    package_id = data.get('package_id', '')
    
    if not package_id:
        logger.error("Missing package_id")
        return None
    
    salesorder_id = data.get('salesorder_id', '')
    salesorder_number = data.get('salesorder_number', '')
    salesorder_date = salesorder_date
    sales_channel = data.get('sales_channel', '')
    sales_channel_formatted = data.get('sales_channel_formatted', '')
    salesorder_fulfilment_status = data.get('salesorder_fulfilment_status', '')
    shipment_id = data.get('shipment_id', '')
    shipment_number = data.get('shipment_number', '')
    shipment_order = data.get('shipment_order', {})
    package_number = data.get('package_number', '')
    date = date
    shipping_date = shipping_date
    delivery_method = data.get('delivery_method', '')
    delivery_method_id = data.get('delivery_method_id', '')
    tracking_number = data.get('tracking_number', '')
    tracking_link = data.get('tracking_link', '')
    expected_delivery_date = data.get('expected_delivery_date', '')
    shipment_delivered_date = data.get('shipment_delivered_date', '')
    status = data.get('status', '')
    detailed_status = data.get('detailed_status', '')
    status_message = data.get('status_message', '')
    carrier = data.get('carrier', '')
    service = data.get('service', '')
    delivery_days = data.get('delivery_days', '')
    delivery_guarantee = data.get('delivery_guarantee', False)
    total_quantity = data.get('total_quantity', 0)
    customer_id = data.get('customer_id', '')
    customer_name = data.get('customer_name', '')
    email = data.get('email', '')
    phone = data.get('phone', '')
    mobile = data.get('mobile', '')
    contact_persons = data.get('contact_persons', [])
    created_by_id = data.get('created_by_id', '')
    last_modified_by_id = data.get('last_modified_by_id', '')
    created_time = created_time
    last_modified_time = last_modified_time
    notes = data.get('notes', '')
    terms = data.get('terms', '')
    is_emailed = data.get('is_emailed', False)
    is_advanced_tracking_missing = data.get('is_advanced_tracking_missing', False)
    line_items = data.get('line_items', [])
    custom_fields = data.get('custom_fields', [])
    custom_field_hash = data.get('custom_field_hash', {})
    shipmentorder_custom_fields = data.get('shipmentorder_custom_fields', [])
    billing_address = data.get('billing_address', {})
    shipping_address = data.get('shipping_address', {})
    picklists = data.get('picklists', [])
    template_id = data.get('template_id', '')
    template_name = data.get('template_name', '')
    template_type = data.get('template_type', '')
    zoho_shipment = zoho_shipment
    
    package = ZohoPackage(
        package_id=package_id,
        salesorder_id=salesorder_id,
        salesorder_number=salesorder_number,
        salesorder_date=salesorder_date,
        sales_channel=sales_channel,
        sales_channel_formatted=sales_channel_formatted,
        salesorder_fulfilment_status=salesorder_fulfilment_status,
        shipment_id=shipment_id,
        shipment_number=shipment_number,
        shipment_order=shipment_order,
        package_number=package_number,
        date=date,
        shipping_date=shipping_date,
        delivery_method=delivery_method,
        delivery_method_id=delivery_method_id,
        tracking_number=tracking_number,
        tracking_link=tracking_link,
        expected_delivery_date=expected_delivery_date,
        shipment_delivered_date=shipment_delivered_date,
        status=status,
        detailed_status=detailed_status,
        status_message=status_message,
        carrier=carrier,
        service=service,
        delivery_days=delivery_days,
        delivery_guarantee=delivery_guarantee,
        total_quantity=total_quantity,
        customer_id=customer_id,
        customer_name=customer_name,
        email=email,
        phone=phone,
        mobile=mobile,
        contact_persons=contact_persons,
        created_by_id=created_by_id,
        last_modified_by_id=last_modified_by_id,
        created_time=created_time,
        last_modified_time=last_modified_time,
        notes=notes,
        terms=terms,
        is_emailed=is_emailed,
        is_advanced_tracking_missing=is_advanced_tracking_missing,
        line_items=line_items,
        custom_fields=custom_fields,
        custom_field_hash=custom_field_hash,
        shipmentorder_custom_fields=shipmentorder_custom_fields,
        billing_address=billing_address,
        shipping_address=shipping_address,
        picklists=picklists,
        template_id=template_id,
        template_name=template_name,
        template_type=template_type,
        zoho_shipment=zoho_shipment,
    )
    return package


def create_books_customers_instance(logger, data):
    current_timezone = timezone.get_current_timezone()

    def parse_datetime(datetime_str):
        if datetime_str:
            try:
                return dt.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S%z')
            except ValueError:
                logger.error(f"Invalid datetime format: {datetime_str}")
        return None
    
    created_time = parse_datetime(data.get('created_time'))
    last_modified_time = parse_datetime(data.get('last_modified_time'))

    if created_time:
        created_time = created_time.astimezone(current_timezone)
    else:
        created_time = timezone.now()

    if last_modified_time:
        last_modified_time = last_modified_time.astimezone(current_timezone)
    else:
        last_modified_time = timezone.now()
    
    contact_id = data.get('contact_id', '')
    
    if not contact_id:
        logger.error("Missing contact_id")
        return None
    
    contact_name = data.get('contact_name', '')
    customer_name = data.get('customer_name', '')
    company_name = data.get('company_name', '')
    status = data.get('status', '')
    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    email = data.get('email', '')
    phone = data.get('phone', '')
    mobile = data.get('mobile', '')
    created_time = data.get('created_time', '')
    created_time_formatted = data.get('created_time_formatted', '')
    last_modified_time = data.get('last_modified_time', '')
    last_modified_time_formatted = data.get('last_modified_time_formatted', '')
    qb_list_id = data.get('qb_list_id', '')
    
    customer = ZohoCustomer(
        contact_id=contact_id,
        contact_name=contact_name,
        customer_name=customer_name,
        company_name=company_name,
        status=status,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        mobile=mobile,
        created_time=created_time,
        created_time_formatted=created_time_formatted,
        last_modified_time=last_modified_time,
        last_modified_time_formatted=last_modified_time_formatted,
        qb_list_id=qb_list_id,
    )
    
    return customer
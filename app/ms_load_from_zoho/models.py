from mongoengine import (
                            Document, 
                            StringField, 
                            BooleanField, 
                            DateTimeField, 
                            IntField, 
                            DecimalField, 
                            DateTimeField, 
                            BooleanField, 
                            StringField, 
                            DateTimeField, 
                            BooleanField, 
                            StringField, 
                            DateTimeField,
                            ListField,
                            DynamicField,
                            DictField,
                            FloatField,
                            ReferenceField,
                            EmailField,
                        )
from mongoengine import fields

from django.utils import timezone

class AppConfig(Document):
    zoho_client_id = StringField(max_length=255, null=True)
    zoho_client_secret = StringField(max_length=255, null=True)
    zoho_org_id = StringField(max_length=255, null=True)
    zoho_redirect_uri = StringField(max_length=255, null=True)
    zoho_refresh_time = fields.IntField(null=True) 
    zoho_refresh_token = StringField(max_length=255, null=True)
    zoho_connection_configured = BooleanField(default=False)
    zoho_last_sync_time = DateTimeField(null=True)

    meta = {
        'collection': 'app_config'
    }

    def save(self, *args, **kwargs):
        if not self.pk:
            existing = AppConfig.objects.first()
            if existing:
                self.id = existing.id

        required_fields = [
            self.zoho_client_id,
            self.zoho_client_secret,
            self.zoho_org_id,
            self.zoho_redirect_uri,
        ]

        self.zoho_connection_configured = all(field for field in required_fields if field is not None and field.strip() != "")

        return super(AppConfig, self).save(*args, **kwargs)

    def __str__(self):
        return f"App Configuration for {self.zoho_org_id or 'Unknown'}"


class ZohoInventoryItem(Document):
    group_id = IntField(null=True)  
    group_name = StringField(max_length=255)
    item_id = StringField(max_length=255, unique=True)  
    name = StringField(max_length=255)
    status = StringField(max_length=50)
    source = StringField(max_length=255)
    is_linked_with_zohocrm = BooleanField()
    item_type = StringField(max_length=50)
    description = StringField(null=True)  
    rate = DecimalField(precision=2)  
    is_taxable = BooleanField()
    tax_id = IntField(null=True)
    tax_name = StringField(max_length=255, null=True)
    tax_percentage = DecimalField(precision=2, null=True)  
    purchase_description = StringField(null=True)
    purchase_rate = DecimalField(precision=2, null=True)  
    is_combo_product = BooleanField()
    product_type = StringField(max_length=50)
    attribute_id1 = IntField(null=True)
    attribute_name1 = StringField(max_length=255, null=True)
    reorder_level = IntField(null=True)
    stock_on_hand = IntField()
    available_stock = IntField()
    actual_available_stock = IntField()
    sku = StringField(max_length=255, null=True)
    upc = IntField(null=True)
    ean = IntField(null=True)
    isbn = IntField(null=True)
    part_number = IntField(null=True)
    attribute_option_id1 = IntField(null=True)
    attribute_option_name1 = StringField(max_length=255, null=True)
    image_name = StringField(max_length=255, null=True)
    image_type = StringField(max_length=50, null=True)
    created_time = DateTimeField()
    last_modified_time = DateTimeField()
    hsn_or_sac = IntField(null=True)
    sat_item_key_code = StringField(max_length=255, null=True)
    unitkey_code = StringField(max_length=255, null=True)
    synced_with_senitron = BooleanField(default=False)
    ignore_errors = BooleanField(default=False)

    meta = {
        'collection': 'zoho_inventory_item'
    }

    def __str__(self):
        return self.name

class ZohoInventoryShipmentSalesOrder(Document):
    salesorder_id = StringField(max_length=255, unique=True)
    salesorder_number = StringField(max_length=255, null=True)
    date = DateTimeField(null=True) 
    status = StringField(max_length=100, null=True)
    customer_id = StringField(max_length=255, null=True)
    customer_name = StringField(max_length=255, null=True)
    is_taxable = BooleanField(default=True)
    tax_id = StringField(max_length=255, null=True)
    tax_name = StringField(max_length=255, null=True)
    tax_percentage = FloatField(null=True)
    currency_id = StringField(max_length=255, null=True)
    currency_code = StringField(max_length=10, null=True)
    currency_symbol = StringField(max_length=5, null=True)
    exchange_rate = FloatField(default=1.0, null=True)
    delivery_method = StringField(max_length=255, null=True)
    total_quantity = FloatField(default=0, null=True)
    sub_total = FloatField(default=0, null=True)
    tax_total = FloatField(default=0, null=True)
    total = FloatField(default=0, null=True)
    created_by_email = StringField(max_length=255, null=True) 
    created_by_name = StringField(max_length=255, null=True)
    salesperson_id = StringField(max_length=255, null=True)
    salesperson_name = StringField(max_length=255, null=True)
    is_test_order = BooleanField(default=False)
    notes = StringField(null=True) 
    payment_terms = IntField(default=0)
    payment_terms_label = StringField(max_length=255, null=True)

    # JSONFields
    line_items = ListField(DynamicField(), default=list, null=True)
    shipping_address = DynamicField(null=True)
    billing_address = DynamicField(null=True)
    warehouses = ListField(DynamicField(), default=list, null=True)
    custom_fields = ListField(DynamicField(), default=list, null=True)
    order_sub_statuses = ListField(DynamicField(), default=list, null=True)
    shipment_sub_statuses = ListField(DynamicField(), default=list, null=True)

    created_time = DateTimeField(null=True)
    last_modified_time = DateTimeField(null=True)

    meta = {
        'collection': 'zoho_inventory_shipment_sales_order',
        'indexes': [
            'salesorder_id', 'salesorder_number'
        ],
        'verbose_name': 'Zoho Inventory Sales Order',
        'verbose_name_plural': 'Zoho Inventory Sales Orders'
    }

    def __str__(self):
        return f"Sales Order {self.salesorder_number} - {self.customer_name}"


class ZohoShipmentOrder(Document):
    shipment_id = StringField(max_length=255, unique=True)
    salesorder_id = StringField(max_length=255, null=True)
    salesorder_number = StringField(max_length=255, null=True)
    salesorder_date = DateTimeField(null=True)
    salesorder_fulfilment_status = StringField(max_length=255, null=True)
    sales_channel = StringField(max_length=255, null=True)
    sales_channel_formatted = StringField(max_length=255, null=True)
    shipment_number = StringField(max_length=255, null=True)
    date = DateTimeField(null=True)
    shipment_status = StringField(max_length=255, null=True)
    shipment_sub_status = StringField(max_length=255, null=True)
    status = StringField(max_length=255, null=True)
    detailed_status = StringField(max_length=255, null=True)
    status_message = StringField(max_length=255, null=True)
    carrier = StringField(max_length=255, null=True)
    tracking_carrier_code = StringField(max_length=255, null=True)
    service = StringField(max_length=255, null=True)
    delivery_days = StringField(max_length=255, null=True)
    source_id = StringField(max_length=255, null=True)
    label_format = StringField(max_length=255, null=True)
    source_name = StringField(max_length=255, null=True)
    delivery_guarantee = BooleanField()
    reference_number = StringField(max_length=255, null=True)
    customer_id = StringField(max_length=255, null=True)
    customer_name = StringField(max_length=255, null=True)
    is_taxable = BooleanField(default=True)
    tax_id = StringField(max_length=255, null=True)
    tax_name = StringField(max_length=255, null=True)
    tax_percentage = DecimalField(precision=2, default=0)  
    currency_id = StringField(max_length=255, null=True)
    currency_code = StringField(max_length=255, null=True)
    currency_symbol = StringField(max_length=255, null=True)
    exchange_rate = DecimalField(precision=4, default=1) 
    discount = DecimalField(precision=2, default=0)
    is_discount_before_tax = BooleanField()
    discount_type = StringField(max_length=255, null=True)
    estimate_id = StringField(max_length=255, null=True)
    delivery_method = StringField(max_length=255, null=True)
    delivery_method_id = StringField(max_length=255, null=True)
    tracking_number = StringField(max_length=255, null=True)
    tracking_link = StringField(null=True)
    last_tracking_update_date = StringField(max_length=255, null=True)
    expected_delivery_date = StringField(max_length=255, null=True)
    shipment_delivered_date = StringField(max_length=255, null=True)
    shipment_type = StringField(max_length=255)
    is_carrier_shipment = BooleanField(default=False)
    is_tracking_enabled = BooleanField(default=False)
    is_forms_available = BooleanField(default=False)
    is_email_notification_enabled = BooleanField(default=False)
    shipping_charge = DecimalField(precision=2, default=0)
    sub_total = DecimalField(precision=2, default=0)
    tax_total = DecimalField(precision=2, default=0)
    total = DecimalField(precision=2, default=0)
    price_precision = IntField(default=0)
    is_emailed = BooleanField(default=False)
    notes = StringField(null=True)
    template_id = StringField(max_length=255, null=True)
    template_name = StringField(max_length=255, null=True)
    template_type = StringField(max_length=255, null=True)
    created_time = DateTimeField(null=True)
    last_modified_time = DateTimeField(null=True)
    associated_packages_count = IntField(default=0)
    created_by_id = StringField(max_length=255, null=True)
    last_modified_by_id = StringField(max_length=255, null=True)

    contact_persons = ListField(DynamicField(), default=list, null=True)
    invoices = ListField(DynamicField(), default=list, null=True)
    line_items = ListField(DynamicField(), default=list, null=True)
    packages = ListField(DynamicField(), default=list, null=True)
    billing_address = DynamicField(null=True)
    shipping_address = DynamicField(null=True)
    custom_fields = ListField(DynamicField(), default=list, null=True)
    custom_field_hash = DynamicField(null=True)
    documents = ListField(DynamicField(), default=list, null=True)
    taxes = ListField(DynamicField(), default=list, null=True)
    tracking_statuses = ListField(DynamicField(), default=list, null=True)
    multipiece_shipments = ListField(DynamicField(), default=list, null=True)

    meta = {
        'collection': 'zoho_shipment_order',
        'indexes': [
            'shipment_id', 'shipment_number'
        ],
        'verbose_name': 'Zoho Inventory Shipment',
        'verbose_name_plural': 'Zoho Inventory Shipment'
    }

    def __str__(self):
        return f"ShipmentOrder {self.shipment_number}"


class ZohoPackage(Document):
    package_id = StringField(max_length=255, unique=True)
    salesorder_id = StringField(max_length=255, null=True)
    salesorder_number = StringField(max_length=255, null=True)
    salesorder_date = DateTimeField(null=True)
    sales_channel = StringField(max_length=255, null=True)
    sales_channel_formatted = StringField(max_length=255, null=True)
    salesorder_fulfilment_status = StringField(max_length=255, null=True)
    shipment_id = StringField(max_length=255, null=True)
    shipment_number = StringField(max_length=255, null=True)
    shipment_order = DynamicField(null=True)
    package_number = StringField(max_length=255, null=True)
    date = DateTimeField(null=True)
    shipping_date = DateTimeField(null=True)
    delivery_method = StringField(max_length=255, null=True)
    delivery_method_id = StringField(max_length=255, null=True)
    tracking_number = StringField(max_length=255, null=True)
    tracking_link = StringField(null=True)
    expected_delivery_date = StringField(max_length=255, null=True)
    shipment_delivered_date = StringField(max_length=255, null=True)
    status = StringField(max_length=255, null=True)
    detailed_status = StringField(max_length=255, null=True)
    status_message = StringField(max_length=255, null=True)
    carrier = StringField(max_length=255, null=True)
    service = StringField(max_length=255, null=True)
    delivery_days = StringField(max_length=255, null=True)
    delivery_guarantee = BooleanField(default=False)
    total_quantity = DecimalField(precision=2, default=0)
    customer_id = StringField(max_length=255, null=True)
    customer_name = StringField(max_length=255, null=True)
    email = StringField(null=True)  # EmailField → StringField
    phone = StringField(max_length=255, null=True)
    mobile = StringField(max_length=255, null=True)
    contact_persons = DynamicField(null=True)
    created_by_id = StringField(max_length=255, null=True)
    last_modified_by_id = StringField(max_length=255, null=True)
    created_time = DateTimeField(null=True)
    last_modified_time = DateTimeField(null=True)
    notes = StringField(null=True)
    terms = StringField(null=True)
    is_emailed = BooleanField(default=False)
    is_advanced_tracking_missing = BooleanField(default=False)
    line_items = DynamicField(null=True)
    custom_fields = DynamicField(null=True)
    custom_field_hash = DynamicField(null=True)
    shipmentorder_custom_fields = DynamicField(null=True)
    billing_address = DynamicField(null=True)
    shipping_address = DynamicField(null=True)
    picklists = DynamicField(null=True)
    template_id = StringField(max_length=255, null=True)
    template_name = StringField(max_length=255, null=True)
    template_type = StringField(max_length=255, null=True)
    
    zoho_shipment = ReferenceField('ZohoShipmentOrder', null=True)

    meta = {
        'collection': 'zoho_package',
        'indexes': [
            'package_id', 'package_number'
        ],
        'verbose_name': 'Zoho Inventory Package',
        'verbose_name_plural': 'Zoho Inventory Package'
    }

    def __str__(self):
        return f"ZohoPackage {self.package_number}"


class ZohoCustomer(Document):
    contact_id = StringField(max_length=255, unique=True, required=True)
    contact_name = StringField(max_length=255, required=True)
    customer_name = StringField(max_length=255, required=True)
    company_name = StringField(max_length=255, null=True)
    status = StringField(max_length=255, required=True)
    first_name = StringField(max_length=255, required=True)
    last_name = StringField(max_length=255, required=True)
    email = StringField(max_length=255, required=True)
    phone = StringField(max_length=255, required=True)
    mobile = StringField(max_length=255, null=True)
    created_time = DateTimeField(required=True)
    created_time_formatted = StringField(max_length=255, required=True)
    last_modified_time = DateTimeField(required=True)
    last_modified_time_formatted = StringField(max_length=255, required=True)
    qb_list_id = StringField(max_length=255, null=True)
    
    contact_type = StringField(max_length=50, required=True)
    has_transaction = BooleanField(default=False)
    is_linked_with_zohocrm = BooleanField(default=False)
    website = StringField(max_length=255, null=True)
    primary_contact_id = StringField(max_length=255, null=True)
    payment_terms = IntField(null=True)
    payment_terms_label = StringField(max_length=255, null=True)
    currency_id = IntField(null=True)
    currency_code = StringField(max_length=10, null=True)
    currency_symbol = StringField(max_length=10, null=True)
    outstanding_receivable_amount = FloatField(default=0.0)
    outstanding_receivable_amount_bcy = FloatField(default=0.0)
    unused_credits_receivable_amount = FloatField(default=0.0)
    unused_credits_receivable_amount_bcy = FloatField(default=0.0)
    facebook = StringField(max_length=255, null=True)
    twitter = StringField(max_length=255, null=True)
    payment_remainder_enabled = BooleanField(default=False)
    notes = StringField(max_length=1024, null=True)
    is_taxable = BooleanField(default=False)
    tax_id = StringField(null=True)
    tax_name = StringField(max_length=255, null=True)
    tax_percentage = FloatField(null=True)
    tax_authority_id = StringField(null=True)
    tax_exemption_id = StringField(max_length=255, null=True)
    tax_authority_name = StringField(max_length=255, null=True)
    tax_exemption_code = StringField(max_length=255, null=True)
    place_of_contact = StringField(max_length=255, null=True)
    gst_no = StringField(max_length=50, null=True)
    tax_treatment = StringField(max_length=255, null=True)
    tax_regime = StringField(max_length=255, null=True)
    legal_name = StringField(max_length=255, null=True)
    is_tds_applicable = BooleanField(default=False)
    vst_treatment = StringField(max_length=255, null=True)
    gst_treatment = StringField(max_length=255, null=True)
    
    custom_fields = ListField(DynamicField(), default=list)
    billing_address = DynamicField()
    shipping_address = DynamicField()
    contact_persons = ListField(DynamicField(), default=list)
    default_templates = DynamicField()

    meta = {
        'collection': 'zoho_customer',
        'indexes': [
            'contact_id',
            'email',
        ],
        'verbose_name': 'Zoho Books Customer',
        'verbose_name_plural': 'Zoho Books Customers',
        'strict': False  # Permite campos no definidos explícitamente
    }

    def save(self, *args, **kwargs):
        if self.pk:
            return super(ZohoCustomer, self).save(*args, **kwargs)
        else:
            if not ZohoCustomer.objects(contact_id=self.contact_id).first() and not ZohoCustomer.objects(email=self.email).first():
                return super(ZohoCustomer, self).save(*args, **kwargs)
            else:
                # Manejar el caso donde el cliente ya existe
                pass

    def __str__(self):
        return self.contact_name


class TimelineItem(Document):
    item_number = StringField(max_length=255, required=True)
    previous_stock_on_hand = IntField(null=True)
    date_previous_stock_on_hand = DateTimeField(null=True)
    actual_stock_on_hand = IntField(null=True)
    date_actual_stock_on_hand = DateTimeField(null=True)
    previous_status_zoho = StringField(max_length=255, null=True)
    date_previous_status_zoho = DateTimeField(null=True)
    actual_status_zoho = StringField(max_length=255, null=True)
    date_actual_status_zoho = DateTimeField(null=True)
    text = StringField(null=True)

    meta = {
        'collection': 'timeline_item'
    }

    def __str__(self):
        return f"Item {self.item_number} - {self.actual_stock_on_hand or 'N/A'} - {self.date_actual_stock_on_hand or 'N/A'}"
    
    
class ZohoFullInvoice(Document):
    invoice_id = StringField(max_length=255, unique=True)
    invoice_number = StringField(max_length=255, required=True)
    date = DateTimeField(null=True)
    due_date = DateTimeField(null=True)
    customer_id = StringField(max_length=255, null=True)
    customer_name = StringField(max_length=255, null=True)
    email = StringField(max_length=255, null=True)
    status = StringField(max_length=255, null=True)
    recurring_invoice_id = StringField(max_length=255, null=True)
    payment_terms = IntField(null=True)
    payment_terms_label = StringField(max_length=255, null=True)
    payment_reminder_enabled = BooleanField(default=False)
    
    payment_discount = DecimalField(precision=2, default=0.0)
    credits_applied = DecimalField(precision=2, default=0.0)
    payment_made = DecimalField(precision=2, default=0.0)
    reference_number = StringField(max_length=255, null=True)
    
    line_items = ListField(DynamicField(), default=list, null=True)

    allow_partial_payments = BooleanField(default=False)
    price_precision = IntField(default=2, null=True)
    sub_total = DecimalField(precision=2, default=0.0)
    tax_total = DecimalField(precision=2, default=0.0)
    discount_total = DecimalField(precision=2, default=0.0)
    discount_percent = DecimalField(precision=2, default=0.0)
    discount = DecimalField(precision=2, default=0.0)
    discount_applied_on_amount = DecimalField(precision=2, default=0.0)
    discount_type = StringField(max_length=255, null=True)
    tax_override_preference = StringField(max_length=255, null=True)
    is_discount_before_tax = BooleanField(default=True)
    adjustment = DecimalField(precision=2, default=0.0)
    adjustment_description = StringField(max_length=255, null=True)
    total = DecimalField(precision=2, default=0.0)
    balance = DecimalField(precision=2, default=0.0)
    is_inclusive_tax = BooleanField(default=False)
    sub_total_inclusive_of_tax = DecimalField(precision=2, default=0.0)
    contact_category = StringField(max_length=255, null=True)
    tax_rounding = StringField(max_length=255, null=True)
    
    taxes = ListField(DynamicField(), default=list, null=True)
    tds_calculation_type = StringField(max_length=255, null=True)
    last_payment_date = DateTimeField(null=True)
    contact_persons = ListField(DynamicField(), default=list, null=True)

    salesorder_id = StringField(max_length=255, null=True)
    salesorder_number = StringField(max_length=255, null=True)
    salesorders = ListField(DynamicField(), default=list, null=True)
    contact_persons_details = ListField(DynamicField(), default=list, null=True)
    created_time = DateTimeField(null=True)
    last_modified_time = DateTimeField(null=True)
    created_date = DateTimeField(null=True)
    created_by_name = StringField(max_length=255, null=True)
    estimate_id = StringField(max_length=255, null=True)
    
    customer_default_billing_address = DictField(default=dict, null=True)

    notes = StringField(null=True)
    terms = StringField(null=True)

    billing_address = DictField(default=dict, null=True)
    shipping_address = DictField(default=dict, null=True)
    contact = DictField(default=dict)

    inserted_in_qb = BooleanField(default=False)
    items_unmatched = ListField(DynamicField(), default=list, null=True)
    customer_unmatched = ListField(DynamicField(), default=list, null=True)
    force_to_sync = BooleanField(default=False)
    
    last_sync_date = DateTimeField(default=timezone.now)

    number_of_times_synced = IntField(default=0, null=True)
    all_items_matched = BooleanField(default=False)
    all_customer_matched = BooleanField(default=False)
    qb_customer_list_id = StringField(max_length=255, null=True)

    meta = {
        'collection': 'zoho_full_invoice', 
        'indexes': [
            'invoice_id',
            'invoice_number',
            'customer_id',
            'customer_name',
        ]
    }

    def __str__(self):
        return f"{self.invoice_number} - {self.customer_name}"
    
    
class SyncMetadata(Document):
    key = StringField(required=True, unique=True)
    value = StringField(required=True)
    
    @staticmethod
    def get_last_sync_date(key):
        record = SyncMetadata.objects(key=key).first()
        if not record:
            date_str = timezone.now().strftime("%Y-%m-%d")
            SyncMetadata(key=key, value=date_str).save()
            record = SyncMetadata.objects(key=key).first()
        return record.value

    @staticmethod
    def update_last_sync_date(key, date_str):
        SyncMetadata.objects(key=key).update_one(
            set__value=date_str, upsert=True
        )
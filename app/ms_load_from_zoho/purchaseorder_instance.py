# manage_instances.py (o donde definiste create_inventory_itemgroup_instance)
from datetime import datetime as dt, timezone

from ms_load_from_zoho.models import ZohoPurchaseOrder
from ms_load_from_zoho.itemgroup_instance import _parse_ts_any

def create_purchaseorder_instance(logger, raw, zoho_org_id):
    try:
        created_time = _parse_ts_any(raw.get("created_time"))
        last_modified_time = _parse_ts_any(raw.get("last_modified_time"))
        date = _parse_ts_any(raw.get("date"))
        expected_delivery_date = _parse_ts_any(raw.get("expected_delivery_date"))
        delivery_date = _parse_ts_any(raw.get("delivery_date"))

        return ZohoPurchaseOrder(
            purchaseorder_id=str(raw.get("purchaseorder_id")).strip(),
            purchaseorder_number=raw.get("purchaseorder_number"),
            reference_number=raw.get("reference_number"),
            status=raw.get("status"),
            vendor_id=str(raw.get("vendor_id")).strip() if raw.get("vendor_id") else None,
            vendor_name=raw.get("vendor_name"),
            date=date,
            expected_delivery_date=expected_delivery_date,
            delivery_date=delivery_date,
            created_time=created_time,
            last_modified_time=last_modified_time,
            currency_id=str(raw.get("currency_id")).strip() if raw.get("currency_id") else None,
            currency_code=str(raw.get("currency_code")).strip() if raw.get("currency_code") else None,
            currency_symbol=str(raw.get("currency_symbol")).strip() if raw.get("currency_symbol") else None,
            exchange_rate=str(raw.get("exchange_rate")).strip() if raw.get("exchange_rate") else None,
            is_drop_shipment=str(raw.get("is_drop_shipment")).strip() if raw.get("is_drop_shipment") else None,
            is_backorder=str(raw.get("is_backorder")).strip() if raw.get("is_backorder") else None,
            can_send_in_mail=str(raw.get("can_send_in_mail")).strip() if raw.get("can_send_in_mail") else None,
            is_pre_gst=str(raw.get("is_pre_gst")).strip() if raw.get("is_pre_gst") else None,
            is_reverse_charge_applied=str(raw.get("is_reverse_charge_applied")).strip() if raw.get("is_reverse_charge_applied") else None,
            sub_total=raw.get("sub_total"),
            tax_total=raw.get("tax_total"),
            total=raw.get("total"),
            price_precision=raw.get("price_precision"),
            salesorder_id=str(raw.get("salesorder_id")).strip() if raw.get("salesorder_id") else None,
            pricebook_id=str(raw.get("pricebook_id")).strip() if raw.get("pricebook_id") else None,
            ship_via=str(raw.get("ship_via")).strip() if raw.get("ship_via") else None,
            ship_via_id=str(raw.get("ship_via_id")).strip() if raw.get("ship_via_id") else None,
            gst_treatment=raw.get("gst_treatment"),
            gst_no=raw.get("gst_no"),
            source_of_supply=raw.get("source_of_supply"),
            destination_of_supply=raw.get("destination_of_supply"),
            notes=raw.get("notes"),
            terms=raw.get("terms"),
            attention=raw.get("attention"),
            attachment_name=raw.get("attachment_name"),
            template_id=str(raw.get("template_id")).strip() if raw.get("template_id") else None,
            template_name=raw.get("template_name"),
            template_type=raw.get("template_type"),
            location_id=str(raw.get("location_id")).strip() if raw.get("location_id") else None,
            location_name=raw.get("location_name"),
            contact_persons_associated=raw.get("contact_persons_associated", []),
            custom_fields=raw.get("custom_fields", []),
            line_items=raw.get("line_items", []),
            taxes=raw.get("taxes", []),
            billing_address=raw.get("billing_address", []),
            delivery_address=raw.get("delivery_address", []),
            purchasereceives=raw.get("purchasereceives", []),
            bills=raw.get("bills", []),
            raw_payload=raw,
            zoho_org_id=zoho_org_id,
        )
    except Exception as e:
        logger.error(f"Error creating ZohoPurchaseOrder instance: {e}")
        return None

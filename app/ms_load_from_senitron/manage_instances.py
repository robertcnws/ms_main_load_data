from django.utils import timezone
from datetime import datetime
from .models import (
                        SenitronItemAsset, 
                        SenitronItem, 
                        SenitronStatus,
                        SenitronItemAssetLogs,
                    )

def create_senitron_item_asset_instance(logger, data, status_cache, item_cache):
    def parse_datetime(value, format, logger):
        """Parses a datetime string and returns an aware datetime object or None."""
        format2 = "%m/%d/%y %I:%M %p" if format == "%m/%d/%Y %I:%M %p" else "%m/%d/%Y %I:%M %p"
        if value and value.strip():
            try:
                dt = datetime.strptime(value, format)
                return timezone.make_aware(dt, timezone.get_current_timezone())
            except ValueError as e:
                try:
                    dt = datetime.strptime(value, format2)
                    return timezone.make_aware(dt, timezone.get_current_timezone())
                except ValueError as e:
                    logger.error(f"Error parsing datetime: {value}, error: {e}, in formats {format} and {format2}")
                    return None
        return None

    format = "%m/%d/%y %I:%M %p"
    aware_first_seen = parse_datetime(data.get('first_seen'), format, logger)
    aware_last_seen = parse_datetime(data.get('last_seen'), format, logger)
    aware_handheld_last_seen = parse_datetime(data.get('handheld_last_seen'), format, logger)
    aware_static_zone_last_update = parse_datetime(data.get('static_zone_last_update'), format, logger)
    aware_receiving_date = parse_datetime(data.get('receiving_date'), format, logger)
    aware_created_at = parse_datetime(data.get('created_at'), format, logger)
    aware_updated_at = parse_datetime(data.get('updated_at'), format, logger)
    
    item_number = data.get('item_number')
    serial_number = data.get('serial_number')
    alt_serial = data.get('alt_serial')
    last_seen_antenna = data.get('last_seen_antenna')
    last_zone = data.get('last_zone')
    handheld_reader = data.get('handheld_reader')
    static_zone = data.get('static_zone')
    current_units = data.get('current_units')
    storage_unit = data.get('storage_unit')
    adjust_qty = data.get('adjust_qty')
    attr1 = data.get('attr1')
    attr2 = data.get('attr2')
    attr3 = data.get('attr3')
    attr4 = data.get('attr4')
    attr5 = data.get('attr5')
    attr6 = data.get('attr6')
    attr7 = data.get('attr7')
    attr8 = data.get('attr8')
    attr9 = data.get('attr9')
    attr10 = data.get('attr10')
    epc = data.get('epc')
    text3 = data.get('text3')
    
    status_json = data.get('status')
    
    try:
        status_key = (status_json.get('name'), status_json.get('id'))
        if status_key in status_cache:
            status = status_cache[status_key]
        else:
            status = SenitronStatus.objects(name=status_json.get('name'), senitron_id=status_json.get('id')).modify(
                upsert=True,
                new=True,
                set__name=status_json.get('name'),
                set__senitron_id=status_json.get('id')
            )
            status_cache[status_key] = status
        
        if item_cache is not None:
            senitron_item = item_cache.get(item_number)
            if senitron_item is None:
                senitron_item = SenitronItem.objects(item_number=item_number).first()
                item_cache[item_number] = senitron_item
        else:
            senitron_item = SenitronItem.objects(item_number=item_number).first()

        asset = SenitronItemAsset(
            item_number=item_number,
            serial_number=serial_number,
            alt_serial=alt_serial,
            first_seen=aware_first_seen,
            last_seen=aware_last_seen,
            last_seen_antenna=last_seen_antenna,
            last_zone=last_zone,
            handheld_reader=handheld_reader,
            handheld_last_seen=aware_handheld_last_seen,
            static_zone=static_zone,
            static_zone_last_update=aware_static_zone_last_update,
            receiving_date=aware_receiving_date,
            current_units=current_units,
            storage_unit=storage_unit,
            adjust_qty=adjust_qty,
            attr1=attr1,
            attr2=attr2,
            attr3=attr3,
            attr4=attr4,
            attr5=attr5,
            attr6=attr6,
            attr7=attr7,
            attr8=attr8,
            attr9=attr9,
            attr10=attr10,
            created_at=aware_created_at,
            updated_at=aware_updated_at,
            epc=epc,
            text3=text3,
            status=status,
            senitron_item=senitron_item,
        )
        return asset
    except Exception as e:
        logger.error(f"Unexpected error for item_number={item_number}: {e}")
        return None

    
def create_senitron_item_asset_logs_instance(logger, data):
    def parse_datetime(value, format, logger):
        """Parses a datetime string and returns an aware datetime object or None."""
        format2 = "%m/%d/%y %I:%M %p" if format == "%m/%d/%Y %I:%M %p" else "%m/%d/%Y %I:%M %p"
        if value and value.strip():
            try:
                dt = datetime.strptime(value, format)
                return timezone.make_aware(dt, timezone.get_current_timezone())
            except ValueError as e:
                try:
                    dt = datetime.strptime(value, format2)
                    return timezone.make_aware(dt, timezone.get_current_timezone())
                except ValueError as e:
                    logger.error(f"Error parsing datetime: {value}, error: {e}, in formats {format} and {format2}")
                    return None
        return None

    format = "%m/%d/%y %I:%M %p"
    aware_last_seen = parse_datetime(data.get('last_seen'), format, logger)
    aware_created_at = parse_datetime(data.get('created_at'), format, logger)
    aware_updated_at = parse_datetime(data.get('updated_at'), format, logger)
    aware_created_time = parse_datetime(data.get('created_time'), format, logger)
    
    
    id = data.get('id')
    item_number = data.get('item_number')
    serial_number = data.get('serial_number')
    alt_serial = data.get('alt_serial')
    last_zone = data.get('last_zone')
    epc = data.get('epc')
    last_status_id = data.get('last_status').get('id')
    last_status_name = data.get('last_status').get('name')
    current_status_id = data.get('current_status').get('id')
    current_status_name = data.get('current_status').get('name')
    user = data.get('user')
    reason = data.get('reason')
    
    existing_asset = SenitronItemAssetLogs.objects(senitron_id=id).first()
    
    if existing_asset is None:
        return SenitronItemAssetLogs(
            senitron_id=id,
            item_number=item_number,
            serial_number=serial_number,
            alt_serial=alt_serial,
            last_seen=aware_last_seen,
            last_zone=last_zone,
            epc=epc,
            last_status_id=last_status_id,
            last_status_name=last_status_name,
            current_status_id=current_status_id,
            current_status_name=current_status_name,
            user=user,
            reason=reason,
            created_at=aware_created_at,
            updated_at=aware_updated_at,
            created_time=aware_created_time
        ) 
    else:
        return None
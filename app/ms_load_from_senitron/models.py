from django.utils import timezone
from mongoengine import (
                        Document,
                        StringField,
                        IntField,
                        BooleanField,
                        DateTimeField,
                        FloatField,
                        ReferenceField,
                    )


class SenitronItem(Document):
    item_number = StringField(max_length=255, unique=True)
    tags_count = IntField(default=0)
    qty = IntField(default=0)
    
    meta = {
        'collection': 'senitron_item',
        'indexes': [
            'item_number',
            'tags_count',
            'qty'
        ]
    }

    def __str__(self):
        return self.item_number


class SenitronStatus(Document):
    senitron_id = IntField(unique=True)
    name = StringField(max_length=100, unique=True)
    
    meta = {
        'collection': 'senitron_status',
        'indexes': [
            'senitron_id',
            'name'
        ]
    }

    def __str__(self):
        return self.name
    
    
class SenitronItemAsset(Document):
    serial_number = StringField(max_length=255, null=True)
    item_number = StringField(max_length=255, null=True)
    alt_serial = StringField(max_length=255, null=True)
    first_seen = DateTimeField(null=True)
    last_seen = DateTimeField(null=True)
    last_seen_antenna = StringField(max_length=255, null=True)
    last_zone = StringField(max_length=255, null=True)
    handheld_reader = StringField(max_length=255, null=True)
    handheld_last_seen = DateTimeField(null=True)
    static_zone = StringField(max_length=255, null=True)
    static_zone_last_update = DateTimeField(null=True)
    receiving_date = DateTimeField(null=True)
    current_units = FloatField(default=0.0)
    storage_unit = FloatField(default=0.0)
    adjust_qty = IntField(default=0)
    attr1 = StringField(max_length=255, null=True)
    attr2 = StringField(max_length=255, null=True)
    attr3 = StringField(max_length=255, null=True)
    attr4 = StringField(max_length=255, null=True)
    attr5 = StringField(max_length=255, null=True)
    attr6 = StringField(max_length=255, null=True)
    attr7 = StringField(max_length=255, null=True)
    attr8 = StringField(max_length=255, null=True)
    attr9 = StringField(max_length=255, null=True)
    attr10 = StringField(max_length=255, null=True)
    created_at = DateTimeField(null=True)
    updated_at = DateTimeField(null=True)
    epc = StringField(max_length=255, null=True)
    text3 = StringField(max_length=255, null=True)
    status = ReferenceField(SenitronStatus)
    senitron_item = ReferenceField(SenitronItem)
    
    meta = {
        'collection': 'senitron_item_asset', 
        'indexes': [
            'item_number', 
            'serial_number', 
            'status', 
            'last_seen', 
            'created_at', 
            'updated_at'
        ]
    }

    def __str__(self):
        s = self.status.name if self.status else 'Unknown'
        return f"Item {self.item_number} - Serial: {self.serial_number} - EPC: {self.epc} - Status: {s} - Last Seen: {self.last_seen}"
    
    
class SenitronItemAssetLogs(Document):
    senitron_id = IntField(unique=True, null=True)
    serial_number = StringField(max_length=255, null=True)
    item_number = StringField(max_length=255, null=True)
    alt_serial = StringField(max_length=255, null=True)
    last_seen = DateTimeField(null=True)
    last_zone = StringField(max_length=255, null=True)
    epc = StringField(max_length=255, null=True)
    last_status_id = IntField(null=True)
    last_status_name = StringField(max_length=255, null=True)
    current_status_id = IntField(null=True)
    current_status_name = StringField(max_length=255, null=True)
    user = StringField(max_length=255, null=True)
    reason = StringField(max_length=255, null=True)
    created_at = DateTimeField(null=True)
    updated_at = DateTimeField(null=True)
    created_time = DateTimeField(default=timezone.now)

    meta = {
        'collection': 'senitron_item_asset_logs',
        'indexes': [
            'senitron_id',
            'item_number',
            'serial_number',
            'current_status_id',
            'current_status_name',
            'last_status_id',
            'last_status_name',
            'last_seen',                                                                                                                                                 
            'created_at',
            'updated_at'
        ]
    }

    def __str__(self):
        return f"Item {self.item_number} - Serial: {self.serial_number} - EPC: {self.epc} - Status: {self.current_status_name} - Serial: {self.serial_number} - Last Seen: {self.last_seen}"



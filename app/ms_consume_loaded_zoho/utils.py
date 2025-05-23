from bson.objectid import ObjectId
import json

def transform_data_to_mongo(data, exclude_fields=None, include_fields=None):
    if isinstance(data, dict):
        for key, value in data.items():
            data[key] = transform_data_to_mongo(value)
        if not 'id' in data and '_id' in data:
            data['id'] = data.get('_id', None)
    else:
        data = data.to_mongo().to_dict()
        if '_id' in data and isinstance(data['_id'], ObjectId):
            data['_id'] = str(data['_id'])
            data['id'] = data['_id']
    if exclude_fields:
        for field in exclude_fields:
            if field in data:
                del data[field]
    if include_fields:
        for field in list(data.keys()):
            if field not in include_fields:
                del data[field]
    return data


def merge_list(sales_orders, id_field="salesorder_id"):
    merged = {}
    for order in sales_orders:
        if isinstance(order, bytes):
            try:
                order = json.loads(order.decode('utf-8'))
            except Exception as e:
                continue

        salesorder_id = order.get(id_field)
        if not salesorder_id:
            continue  
        if salesorder_id not in merged:
            merged[salesorder_id] = order.copy()
        else:
            existing = merged[salesorder_id]
            for key, value in order.items():
                if key in existing:
                    if isinstance(existing[key], list) and isinstance(value, list):
                        combined = existing[key] + value
                        unique = []
                        for item in combined:
                            if item not in unique:
                                unique.append(item)
                        existing[key] = unique
                    else:
                        existing[key] = value
                else:
                    existing[key] = value
    return list(merged.values())
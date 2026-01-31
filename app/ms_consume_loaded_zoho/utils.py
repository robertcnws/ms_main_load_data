from bson import ObjectId
from datetime import datetime, date
import json

def transform_data_to_mongo(data, exclude_fields=None, include_fields=None):
    # 1) dict
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            out[k] = transform_data_to_mongo(v)
        if "id" not in out and "_id" in out:
            out["id"] = out.get("_id")
        data = out

    # 2) list/tuple
    elif isinstance(data, (list, tuple)):
        data = [transform_data_to_mongo(x) for x in data]

    # 3) MongoEngine Document (o algo con to_mongo)
    elif hasattr(data, "to_mongo"):
        data = data.to_mongo().to_dict()
        if "_id" in data and isinstance(data["_id"], ObjectId):
            data["_id"] = str(data["_id"])
            data["id"] = data["_id"]

    # 4) ObjectId directo
    elif isinstance(data, ObjectId):
        data = str(data)

    # 5) fechas (opcional: a string)
    elif isinstance(data, (datetime, date)):
        data = data.isoformat()

    # 6) primitivos (str/int/float/bool/None) -> se devuelven tal cual
    else:
        return data

    # Solo aplicar exclude/include si el resultado final es dict
    if isinstance(data, dict):
        if exclude_fields:
            for field in exclude_fields:
                data.pop(field, None)

        if include_fields:
            for field in list(data.keys()):
                if field not in include_fields:
                    data.pop(field, None)

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
from bson.objectid import ObjectId

def _normalize_only_fields(only_fields_str, DocCls):
    if not only_fields_str:
        return None, None, {}

    requested = [f.strip() for f in only_fields_str.split(',') if f.strip()]
    model_fields = set(DocCls._fields.keys())  # incluye 'id'
    db_field_map = {name: field.db_field for name, field in DocCls._fields.items()}
    
    valid_for_only = [f for f in requested if f in model_fields and f not in ('id', '_id')]

    return requested, valid_for_only, db_field_map

def filtered_queryset_from_only_fields(queryset, only_fields_list):
    if only_fields_list:
        return queryset.only(*only_fields_list)
    return queryset

def filtered_list_from_only_fields(docs, requested_fields, valid_fields, db_field_map):
    items = []
    want_only = bool(requested_fields)
    
    valid_out = [f for f in (requested_fields or []) if f in db_field_map and f not in ('id','_id')]

    for doc in docs:
        raw = doc.to_mongo().to_dict()
        _id = raw.get('_id')
        if isinstance(_id, ObjectId):
            _id = str(_id)

        if want_only:
            out = {'_id': _id}
            for fname in valid_out:
                db_key = db_field_map.get(fname, fname)
                if db_key in raw:
                    val = raw[db_key]
                    out[fname] = val
            items.append(out)
        else:
            raw['_id'] = _id
            items.append(raw)
    return items
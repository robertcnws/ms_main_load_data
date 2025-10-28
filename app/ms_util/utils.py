from bson.objectid import ObjectId

def filtered_queryset_from_only_fields(queryset, only_fields_list):
    if only_fields_list:
        return queryset.only(*only_fields_list)
    return queryset

def filtered_list_from_only_fields(docs, only_fields_list):
    items_list = []
    want_only = bool(only_fields_list)
    req = []
    if want_only:
        req = [f.strip() for f in only_fields_list if f and f.strip()]
        req = [f for f in req if f not in ('id', '_id')]

    for doc in docs:
        raw = doc.to_mongo().to_dict()
        
        _id = raw.get('_id')
        if isinstance(_id, ObjectId):
            _id = str(_id)

        if want_only:
            out = {'_id': _id}
            for field in req:
                if field in raw:
                    val = raw[field]
                    if val is not None:
                        out[field] = val
        else:
            out = raw
            out['_id'] = _id

        items_list.append(out)

    return items_list
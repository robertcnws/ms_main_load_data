from bson.objectid import ObjectId

def filtered_queryset_from_only_fields(queryset, only_fields_list):
    if only_fields_list:
        return queryset.only(*only_fields_list)
    return queryset

def filtered_list_from_only_fields(docs, only_fields_list):
    items_list = []
    for doc in docs:
        if only_fields_list:
            out = {"_id": str(doc.id)}
            for field in only_fields_list:
                if field in ('id', '_id'):
                    continue
                value = getattr(doc, field, None)
                out[field] = value
        else:
            out = doc.to_mongo().to_dict()
            if '_id' in out and isinstance(out['_id'], ObjectId):
                out['_id'] = str(out['_id'])
        items_list.append(out)
    return items_list
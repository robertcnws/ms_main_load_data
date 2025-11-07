from bson.objectid import ObjectId
from __future__ import annotations
from datetime import datetime, date, time
from zoneinfo import ZoneInfo

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


def to_tz_iso8601(
    dt_or_str: str | datetime | date,
    target_tz: str = "America/New_York",
    source_tz: str = "UTC",
) -> str:
    """
    Convierte una fecha/hora a la zona `target_tz` y la devuelve como string
    con formato 'YYYY-MM-DDTHH:MM:SS±HHMM'.

    - Admite ISO 8601 con offset (p.ej. '2025-11-07T14:06:03.000+00:00' o '...Z')
      y descarta milisegundos.
    - Si recibe un datetime naive, asume `source_tz`.
    - Si recibe un date, usa las 00:00:00 en `source_tz`.
    """
    # Normaliza la entrada a datetime
    if isinstance(dt_or_str, datetime):
        dt = dt_or_str
    elif isinstance(dt_or_str, date):
        dt = datetime.combine(dt_or_str, time(0, 0, 0))
    elif isinstance(dt_or_str, str):
        s = dt_or_str.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    else:
        raise TypeError("dt_or_str debe ser str, datetime o date")

    # Si es naive, asigna tz de origen
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(source_tz))

    # Convierte a tz de destino
    dt_local = dt.astimezone(ZoneInfo(target_tz))

    # Devuelve sin milisegundos, con offset sin dos puntos (±HHMM)
    return dt_local.strftime("%Y-%m-%dT%H:%M:%S%z")
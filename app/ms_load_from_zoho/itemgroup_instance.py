# manage_instances.py (o donde definiste create_inventory_itemgroup_instance)
from datetime import datetime as dt, timezone

from ms_load_from_zoho.models import ZohoItemGroup

def _parse_ts_any(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        ts = float(v)
        if ts > 1e12:  # ms
            ts /= 1000.0
        return dt.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        if s.isdigit():
            ts = float(s)
            if ts > 1e12:
                ts /= 1000.0
            return dt.fromtimestamp(ts, tz=timezone.utc)
        for fmt in ("%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S.%f%z",
                    "%Y-%m-%d"):
            try:
                d = dt.strptime(s, fmt)
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                else:
                    d = d.astimezone(timezone.utc)
                return d
            except Exception:
                pass
    return None

def create_itemgroup_instance(raw, zoho_org_id):
    created_time = _parse_ts_any(raw.get("created_time"))
    last_modified_time = _parse_ts_any(raw.get("last_modified_time"))

    return ZohoItemGroup(
        group_id=str(raw.get("group_id") or "").strip(),
        group_name=str(raw.get("group_name") or "").strip(),
        product_type=raw.get("product_type"),
        brand=raw.get("brand"),
        manufacturer=raw.get("manufacturer"),
        unit=raw.get("unit"),
        description=raw.get("description"),
        is_taxable=bool(raw.get("is_taxable", False)),
        tax_id=raw.get("tax_id"),
        tax_name=raw.get("tax_name"),
        tax_percentage=raw.get("tax_percentage"),
        tax_type=raw.get("tax_type"),
        tax_exemption_id=raw.get("tax_exemption_id"),
        attribute_id1=raw.get("attribute_id1"),
        attribute_name1=raw.get("attribute_name1"),
        status=raw.get("status"),
        source=raw.get("source"),
        image_id=raw.get("image_id"),
        image_name=raw.get("image_name"),
        image_type=raw.get("image_type"),
        created_time=created_time,
        last_modified_time=last_modified_time,
        zoho_org_id=zoho_org_id,
    )

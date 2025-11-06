# services/items_service.py
import os
import time
import json
import logging
from datetime import datetime as dt, timezone
from email.utils import format_datetime

import requests
from django.conf import settings
from mongoengine.queryset.visitor import Q

from ms_load_from_zoho.metrics import now_iso, set_metrics
from ms_load_from_zoho import helpers
from .models import AppConfig, ZohoInventoryItem, TimelineItem, SyncMetadata, ZohoItemGroup
from .manage_instances import create_inventory_itemgroup_instance

logger = logging.getLogger(__name__)
LOG_PREFIX = "[ITEMGROUPS]"

# Heurísticas de corte (tuneables por ENV)
CUTOFF_STALE_RATIO = float(os.getenv("ZOHO_ITEMGROUPS_CUTOFF_STALE_RATIO", "0.9"))
CUTOFF_STALE_STREAK = int(os.getenv("ZOHO_ITEMGROUPS_CUTOFF_STALE_STREAK", "2"))
LIST_PAGE_DELAY_SEC = float(os.getenv("ZOHO_LIST_PAGE_DELAY_SEC", "1"))

def _parse_zoho_ts(value: str | None):
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return dt.strptime(value, fmt).astimezone(timezone.utc)
        except Exception:
            pass
    return None

def _lm_or_created(item: dict):
    return _parse_zoho_ts(item.get("last_modified_time")) or _parse_zoho_ts(item.get("created_time"))

def load_itemgroups_service(*, zoho_org_id: str, start_date: str | None = None, item_number: str | None = None, use_if_modified_since: bool = True):
    t0 = time.time()
    list_calls = created = updated = 0
    status = "ok"
    
    if start_date:
        try:
            cutoff_dt = dt.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError("Invalid start_date format. Use YYYY-MM-DD")
    else:
        last_sync = SyncMetadata.get_last_sync_date("last_sync_date_itemgroups")
        if last_sync:
            # last_sync viene en ISO; si no es aware, lo forzamos a UTC
            try:
                cutoff_dt = dt.fromisoformat(last_sync)
                if cutoff_dt.tzinfo is None:
                    cutoff_dt = cutoff_dt.replace(tzinfo=timezone.utc)
                else:
                    cutoff_dt = cutoff_dt.astimezone(timezone.utc)
            except Exception:
                cutoff_dt = dt.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            existing_groups = ZohoItemGroup.objects().count()
            if existing_groups > 0:
                cutoff_dt = dt.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                cutoff_dt = dt(2000, 1, 1, tzinfo=timezone.utc)

    logger.info(f"{LOG_PREFIX} START zoho_org_id={zoho_org_id} cutoff={cutoff_dt.isoformat()} group_id={item_number}")

    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    if not app_config:
        raise ValueError(f"No AppConfig for zoho_org_id={zoho_org_id}")

    try:
        headers = helpers.config_headers(zoho_org_id)
    except Exception as e:
        logger.error(f"{LOG_PREFIX} Error connecting to Zoho API: {e}")
        status = "error"
        set_metrics(
            "itemgroups",
            zoho_org_id=zoho_org_id,
            last_run=now_iso(),
            last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_itemgroups") or "",
            list_calls=list_calls,
            detail_calls=0,
            package_calls=0,
            created=created,
            updated=updated,
            duration_sec=round(time.time() - t0, 3),
            status=status,
        )
        raise

    session = helpers._retry_session()
    ims_headers = headers.copy()
    if use_if_modified_since:
        ims_headers["If-Modified-Since"] = format_datetime(cutoff_dt)

    def _get(url, hdrs, params):
        nonlocal list_calls
        resp = session.get(url, headers=hdrs, params=params)
        list_calls += 1
        if resp.status_code == 401:
            logger.warning(f"{LOG_PREFIX} 401 -> refresh token")
            new_token = helpers.refresh_zoho_access_token(zoho_org_id)
            hdrs["Authorization"] = f"Zoho-oauthtoken {new_token}"
            resp = session.get(url, headers=hdrs, params=params)
            list_calls += 1
        resp.raise_for_status()
        return resp

    itemgroups_to_process = []

    if item_number:
        # SINGLE
        url = f"{settings.ZOHO_INVENTORY_ITEMGROUPS_URL}/{item_number}"
        try:
            r = _get(url, ims_headers if use_if_modified_since else headers, {"organization_id": app_config.zoho_org_id})
            if r.status_code != 304:
                it = r.json().get("item", {})
                if it:
                    lm = _lm_or_created(it)
                    if not lm or lm >= cutoff_dt:
                        itemgroups_to_process.append(it)
        except requests.RequestException as e:
            logger.error(f"{LOG_PREFIX} Error fetching single itemgroup={item_number}: {e}")
    else:
        # LIST PAGINADO
        base_url = settings.ZOHO_INVENTORY_ITEMGROUPS_URL
        start_date = dt.strptime(start_date, '%Y-%m-%d')
        last_modified_time = start_date.strftime('%Y-%m-%d') + 'T00:00:00+0000'
        params = {
            "organization_id": app_config.zoho_org_id,
            "per_page": 200,
            "page": 1,
            "last_modified_time": last_modified_time,
        }
        page = 1
        has_more = True
        stale_streak = 0
        hdrs_for_list = ims_headers if use_if_modified_since else headers

        while has_more:
            cur = params | {"page": page}
            try:
                logger.debug(f"{LOG_PREFIX} LIST page={page}")
                r = _get(base_url, hdrs_for_list, cur)
                if use_if_modified_since and r.status_code == 304 and page == 1:
                    has_more = False
                    break
                data = r.json()
                page_items = data.get("itemgroups", []) or []
                has_more = data.get("page_context", {}).get("has_more_page", False)
                
                stale_count = 0
                recent = []
                for it in page_items:
                    lm = _lm_or_created(it)
                    if lm and lm >= cutoff_dt:
                        recent.append(it)
                    else:
                        stale_count += 1

                itemgroups_to_process.extend(recent)
                
                total = len(page_items) or 1
                if (stale_count / total) >= CUTOFF_STALE_RATIO:
                    stale_streak += 1
                else:
                    stale_streak = 0
                if stale_streak >= CUTOFF_STALE_STREAK:
                    has_more = False

                page += 1
                time.sleep(LIST_PAGE_DELAY_SEC)
            except requests.RequestException as e:
                logger.error(f"{LOG_PREFIX} Error fetching itemgroups page={page}: {e}")
                status = "error"
                break

    logger.info(f"{LOG_PREFIX} LIST after_cutoff count={len(itemgroups_to_process)} list_calls={list_calls}")

    # UPSERT
    ids = [it.get("group_id") for it in itemgroups_to_process if it.get("group_id")]
    existing = ZohoItemGroup.objects(Q(group_id__in=ids))
    existing_map = {doc.group_id: doc for doc in existing}

    new_docs, to_update, timelines = [], [], []
    for raw in itemgroups_to_process:
        inst = create_inventory_itemgroup_instance(logger, raw, zoho_org_id)
        if not inst:
            continue
        prev = existing_map.get(inst.group_id)
        if prev:
            to_update.append(inst)
        else:
            new_docs.append(inst)

    if new_docs:
        ZohoItemGroup.objects.insert(new_docs)
        created = len(new_docs)

    if to_update:
        for inst in to_update:
            db = ZohoItemGroup.objects(group_id=inst.group_id).first()
            if not db:
                continue
            # Update fields as necessary
            # ------------
            db.save()
        updated = len(to_update)

    if timelines:
        TimelineItem.objects.insert(timelines)
        
    if status == "ok":
        SyncMetadata.update_last_sync_date(
            "last_sync_date_itemgroups",
            dt.now(timezone.utc).strftime("%Y-%m-%d")
        )

    duration = round(time.time() - t0, 3)
    set_metrics(
            "itemgroups",
            zoho_org_id=zoho_org_id,
            last_run=now_iso(),
            last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_itemgroups") or "",
            list_calls=list_calls,
            detail_calls=0,
            package_calls=0,
            created=created,
            updated=updated,
            duration_sec=duration,
            status=status,
        )

    logger.info(f"{LOG_PREFIX} END created={created} updated={updated} list_calls={list_calls} duration_sec={duration} status={status}")

    return {
        "created": created,
        "updated": updated,
        "list_calls": list_calls,
        "duration_sec": duration,
        "status": status,
        "count_after_cutoff": len(itemgroups_to_process),
        "cutoff_iso": cutoff_dt.isoformat(),
    }

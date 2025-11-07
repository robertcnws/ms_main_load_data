# services/items_service.py
import os
import time
import logging
from datetime import datetime as dt, timezone
from email.utils import format_datetime

import requests
from django.conf import settings
from ms_util.utils import to_tz_iso8601
from mongoengine.queryset.visitor import Q

from ms_load_from_zoho.metrics import now_iso, set_metrics
from ms_load_from_zoho import helpers
from .models import AppConfig, ZohoInventoryItem, TimelineItem, SyncMetadata
from .manage_instances import create_inventory_item_instance

logger = logging.getLogger(__name__)
LOG_PREFIX = "[ITEMS]"

# Heurísticas de corte (tuneables por ENV)
CUTOFF_STALE_RATIO = float(os.getenv("ZOHO_ITEMS_CUTOFF_STALE_RATIO", "0.9"))
CUTOFF_STALE_STREAK = int(os.getenv("ZOHO_ITEMS_CUTOFF_STALE_STREAK", "2"))
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

def load_items_service(*, zoho_org_id: str, start_date: str | None = None, item_number: str | None = None, use_if_modified_since: bool = True):
    t0 = time.time()
    list_calls = created = updated = 0
    status = "ok"
    
    if not start_date:
        last_sync = SyncMetadata.get_last_sync_date("last_sync_date_items")
        base = dt.now(timezone.utc)
        if last_sync:
            try:
                base = dt.strptime(last_sync, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except Exception:
                pass
        start_date = to_tz_iso8601(base)
        
    cutoff_dt = _parse_zoho_ts(last_modified_time)

    logger.info(f"{LOG_PREFIX} START zoho_org_id={zoho_org_id} cutoff={cutoff_dt.isoformat()} item_number={item_number}")

    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    if not app_config:
        raise ValueError(f"No AppConfig for zoho_org_id={zoho_org_id}")

    try:
        headers = helpers.config_headers(zoho_org_id)
    except Exception as e:
        logger.error(f"{LOG_PREFIX} Error connecting to Zoho API: {e}")
        status = "error"
        set_metrics(
            "items",
            zoho_org_id=zoho_org_id,
            last_run=now_iso(),
            last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_items") or "",
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

    items_to_process = []

    if item_number:
        # SINGLE
        url = f"{settings.ZOHO_INVENTORY_ITEMS_URL}/{item_number}"
        try:
            r = _get(url, ims_headers if use_if_modified_since else headers, {"organization_id": app_config.zoho_org_id})
            if r.status_code != 304:
                it = r.json().get("item", {})
                if it:
                    lm = _lm_or_created(it)
                    if not lm or lm >= cutoff_dt:
                        items_to_process.append(it)
        except requests.RequestException as e:
            logger.error(f"{LOG_PREFIX} Error fetching single item={item_number}: {e}")
    else:
        # LIST PAGINADO
        base_url = settings.ZOHO_INVENTORY_ITEMS_URL
        # start_date = dt.strptime(start_date, '%Y-%m-%d')
        # last_modified_time = start_date.strftime('%Y-%m-%d') + 'T00:00:00+0000'
        last_modified_time = start_date
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
                page_items = data.get("items", []) or []
                has_more = data.get("page_context", {}).get("has_more_page", False)
                
                stale_count = 0
                recent = []
                for it in page_items:
                    lm = _lm_or_created(it)
                    if lm and lm >= cutoff_dt:
                        recent.append(it)
                    else:
                        stale_count += 1

                items_to_process.extend(recent)
                
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
                logger.error(f"{LOG_PREFIX} Error fetching items page={page}: {e}")
                status = "error"
                break

    logger.info(f"{LOG_PREFIX} LIST after_cutoff count={len(items_to_process)} list_calls={list_calls}")

    # UPSERT
    ids = [it.get("item_id") for it in items_to_process if it.get("item_id")]
    existing = ZohoInventoryItem.objects(Q(item_id__in=ids))
    existing_map = {doc.item_id: doc for doc in existing}

    new_docs, to_update, timelines = [], [], []
    for raw in items_to_process:
        inst = create_inventory_item_instance(logger, raw, zoho_org_id)
        if not inst:
            continue
        prev = existing_map.get(inst.item_id)
        if prev:
            # cambios relevantes
            if prev.status != inst.status:
                timelines.append(TimelineItem(
                    item_number=inst.item_id,
                    previous_status_zoho=prev.status,
                    date_previous_status_zoho=prev.last_modified_time or prev.created_time,
                    actual_status_zoho=inst.status,
                    date_actual_status_zoho=inst.last_modified_time or inst.created_time,
                    text=f"{inst.sku or '-'} status changed -> From {prev.status} to {inst.status}"
                ))
            if int(prev.stock_on_hand) != int(inst.stock_on_hand):
                change = "added" if inst.stock_on_hand > prev.stock_on_hand else "removed"
                diff = abs(inst.stock_on_hand - prev.stock_on_hand)
                timelines.append(TimelineItem(
                    item_number=inst.item_id,
                    previous_stock_on_hand=prev.stock_on_hand,
                    date_previous_stock_on_hand=prev.last_modified_time or prev.created_time,
                    actual_stock_on_hand=inst.stock_on_hand,
                    date_actual_stock_on_hand=inst.last_modified_time or inst.created_time,
                    text=f"{inst.sku or '-'} : {int(diff)} unit(s) {change} -> New stock on hand: {int(inst.stock_on_hand)}"
                ))
            to_update.append(inst)
        else:
            new_docs.append(inst)
            timelines.append(TimelineItem(
                item_number=inst.item_id,
                actual_stock_on_hand=inst.stock_on_hand,
                date_actual_stock_on_hand=inst.last_modified_time or inst.created_time,
                actual_status_zoho=inst.status,
                date_actual_status_zoho=inst.last_modified_time or inst.created_time,
                text=f"{inst.sku or '-'} created -> On hand: {int(inst.stock_on_hand)}, Status: {inst.status}"
            ))

    if new_docs:
        ZohoInventoryItem.objects.insert(new_docs)
        created = len(new_docs)

    if to_update:
        for inst in to_update:
            db = ZohoInventoryItem.objects(item_id=inst.item_id).first()
            if not db:
                continue
            db.status = inst.status
            db.stock_on_hand = inst.stock_on_hand
            db.last_modified_time = inst.last_modified_time
            db.save()
        updated = len(to_update)

    if timelines:
        TimelineItem.objects.insert(timelines)
        
    if status == "ok":
        SyncMetadata.update_last_sync_date(
            "last_sync_date_items",
            dt.now(timezone.utc).strftime("%Y-%m-%d")
        )

    duration = round(time.time() - t0, 3)
    set_metrics(
            "items",
            zoho_org_id=zoho_org_id,
            last_run=now_iso(),
            last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_items") or "",
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
        "count_after_cutoff": len(items_to_process),
        "cutoff_iso": cutoff_dt.isoformat(),
    }

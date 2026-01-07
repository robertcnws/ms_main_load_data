# services/items_service.py
import os
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Optional, Tuple, List

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

def load_items_service(*, start_date: str | None = None, zoho_org_id: str, item_number: str | None = None, use_if_modified_since: bool = True):
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
        
    cutoff_dt = _parse_zoho_ts(start_date)

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
        params = {"organization_id": app_config.zoho_org_id}
        try:
            r = _get(url, ims_headers if use_if_modified_since else headers, params)
            if r.status_code != 304:
                it = r.json().get("item", {})
                if it:
                    lm = _lm_or_created(it)
                    if not lm or lm >= cutoff_dt:
                        items_to_process.append(it)
        except requests.RequestException as e:
            logger.error(f"{LOG_PREFIX} Error fetching single item={item_number} for org_id={zoho_org_id}: {e}")
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
                logger.error(f"{LOG_PREFIX} Error fetching items page={page} for org_id={zoho_org_id}: {e}")
                status = "error"
                break

    logger.info(f"{LOG_PREFIX} LIST after_cutoff count={len(items_to_process)} list_calls={list_calls} org_id={zoho_org_id}")

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

    logger.info(f"{LOG_PREFIX} END org_id={zoho_org_id} created={created} updated={updated} list_calls={list_calls} duration_sec={duration} status={status}")

    return {
        "created": created,
        "updated": updated,
        "list_calls": list_calls,
        "duration_sec": duration,
        "status": status,
        "count_after_cutoff": len(items_to_process),
        "cutoff_iso": cutoff_dt.isoformat(),
    }
    
    
DETAIL_RPS = 4.0
MAX_WORKERS = 6
MAX_RETRIES_429 = 3
MAX_RETRIES_NET = 2
CONNECT_TO = 10
READ_TO = 60


class RateLimiter:
    def __init__(self, rps: float):
        self.min_interval = 1.0 / max(rps, 0.1)
        self._lock = threading.Lock()
        self._next_ts = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            if now < self._next_ts:
                time.sleep(self._next_ts - now)
            self._next_ts = max(self._next_ts, time.monotonic()) + self.min_interval


def load_items_field_values_backfill_stock(
    *,
    zoho_org_id: str,
    use_if_modified_since: bool = True,
    detail_fields: Optional[List[str]] = None,
    max_workers: int = MAX_WORKERS,
    detail_rps: float = DETAIL_RPS,
    limit_initial: Optional[int] = None,
) -> Dict[str, Any]:

    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    if not app_config:
        raise ValueError(f"No AppConfig for zoho_org_id={zoho_org_id}")

    LOG_PREFIX = "[items.backfill]"
    status = "ok"

    # Default fields
    if detail_fields is None:
        detail_fields = ["actual_available_for_sale_stock"]

    base_headers = helpers.config_headers(zoho_org_id)
    headers_lock = threading.Lock()
    refresh_lock = threading.Lock()

    list_session = helpers._retry_session()

    def _get_with_refresh(session: requests.Session, url: str, hdrs: Dict[str, str], params: Dict[str, Any]) -> requests.Response:
        resp = session.get(url, headers=hdrs, params=params, timeout=(CONNECT_TO, READ_TO))
        if resp.status_code == 401:
            with refresh_lock:
                # Re-check por si otro thread ya refrescó
                resp2 = session.get(url, headers=hdrs, params=params, timeout=(CONNECT_TO, READ_TO))
                if resp2.status_code != 401:
                    return resp2

                logger.warning(f"{LOG_PREFIX} 401 -> refresh token (org_id={zoho_org_id})")
                new_token = helpers.refresh_zoho_access_token(zoho_org_id)

                with headers_lock:
                    base_headers["Authorization"] = f"Zoho-oauthtoken {new_token}"

                resp = session.get(url, headers=base_headers, params=params, timeout=(CONNECT_TO, READ_TO))
        return resp

    # ========= LIST PAGINADO =========
    items_to_process: List[Dict[str, Any]] = []
    base_url = settings.ZOHO_INVENTORY_ITEMS_URL

    params = {
        "organization_id": app_config.zoho_org_id,
        "per_page": 200,
        "page": 1,
        "fields": "item_id",
    }

    page = 1
    has_more = True
    hdrs_for_list = base_headers  # (usa ims_headers aquí si tienes If-Modified-Since real)

    while has_more:
        cur = params | {"page": page}
        try:
            logger.debug(f"{LOG_PREFIX} LIST page={page}")
            r = _get_with_refresh(list_session, base_url, hdrs_for_list, cur)

            if use_if_modified_since and r.status_code == 304 and page == 1:
                has_more = False
                break

            r.raise_for_status()
            data = r.json()
            page_items = data.get("items", []) or []
            has_more = data.get("page_context", {}).get("has_more_page", False)

            items_to_process.extend(page_items)
            page += 1
            time.sleep(LIST_PAGE_DELAY_SEC)

        except requests.RequestException as e:
            logger.exception(f"{LOG_PREFIX} LIST error: {e}")
            status = "error"
            break

    ids = [it.get("item_id") for it in items_to_process if it.get("item_id")]
    if not ids:
        return {"status": status, "count_after_cutoff": 0, "updated_missing": 0, "skipped": 0, "errors": 0}

    # ========= EXISTING con campo missing/null =========
    missing_q = Q(actual_available_for_sale_stock__exists=False) | Q(actual_available_for_sale_stock=None)

    qs = ZohoInventoryItem.objects(Q(item_id__in=ids) & missing_q).only("id", "item_id")
    if limit_initial:
        qs = qs.limit(limit_initial)

    docs = list(qs)
    if not docs:
        return {"status": status, "count_after_cutoff": len(items_to_process), "updated_missing": 0, "skipped": 0, "errors": 0}

    limiter = RateLimiter(detail_rps)

    # Construye fields solo si hay lista no vacía
    fields_str = ",".join([f for f in detail_fields if f]) if detail_fields else ""

    def fetch_and_update_one(doc) -> Tuple[str, str]:
        item_id = doc.item_id
        detail_url = f"{settings.ZOHO_INVENTORY_ITEMS_URL}/{item_id}"

        detail_params = {"organization_id": app_config.zoho_org_id}
        if fields_str:
            detail_params["fields"] = fields_str

        session = helpers._retry_session()

        for attempt in range(1, MAX_RETRIES_429 + 1):
            try:
                limiter.wait()

                with headers_lock:
                    hdrs = base_headers.copy()

                resp = _get_with_refresh(session, detail_url, hdrs, detail_params)

                if resp.status_code == 429:
                    ra = resp.headers.get("Retry-After")
                    sleep_s = float(ra) if ra else min(2.0, 0.5 * attempt)
                    logger.warning(f"{LOG_PREFIX} 429 item_id={item_id} retry_after={sleep_s}s attempt={attempt}")
                    time.sleep(sleep_s)
                    continue

                resp.raise_for_status()

                payload = resp.json() or {}
                item = payload.get("item") or {}
                value = item.get("actual_available_for_sale_stock")

                if value is None:
                    return ("skipped", item_id)

                ZohoInventoryItem.objects(id=doc.id).update_one(set__actual_available_for_sale_stock=value)
                return ("updated", item_id)

            except requests.RequestException as e:
                if attempt <= MAX_RETRIES_NET:
                    time.sleep(0.3 * attempt)
                    continue
                logger.warning(f"{LOG_PREFIX} DETAIL error item_id={item_id}: {e}")
                return ("error", item_id)
            except Exception as e:
                logger.warning(f"{LOG_PREFIX} Unexpected error item_id={item_id}: {e}")
                return ("error", item_id)

        return ("error", item_id)

    updated = 0
    skipped = 0
    errors = 0

    logger.info(
        f"{LOG_PREFIX} Backfill start org_id={zoho_org_id} missing={len(docs)} "
        f"workers={max_workers} rps={detail_rps} fields={fields_str or '(none)'}"
    )

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(fetch_and_update_one, d) for d in docs]
        for fut in as_completed(futures):
            outcome, _ = fut.result()
            if outcome == "updated":
                updated += 1
            elif outcome == "skipped":
                skipped += 1
            else:
                errors += 1

    logger.info(f"{LOG_PREFIX} Backfill done updated={updated} skipped={skipped} errors={errors}")

    return {
        "status": status,
        "count_after_cutoff": len(items_to_process),
        "missing_initial": len(docs),
        "updated_missing": updated,
        "skipped": skipped,
        "errors": errors,
        "workers": max_workers,
        "detail_rps": detail_rps,
        "detail_fields": detail_fields,
    }
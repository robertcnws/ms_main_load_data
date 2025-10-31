from __future__ import annotations

import os
import time
import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from concurrent.futures import TimeoutError as FuturesTimeout  # por compatibilidad en bloques pkg

from django.conf import settings
from mongoengine.queryset.visitor import Q
from tenacity import retry, retry_if_exception_type, wait_exponential, stop_after_attempt

from ms_load_from_zoho.models import (
    AppConfig,
    ZohoShipmentOrder,
    ZohoPackage,
    SyncMetadata,
)
from ms_load_from_zoho import helpers
from ms_load_from_zoho.manage_instances import (
    create_inventory_package_instance,
    create_inventory_shipment_instance,
)

logger = logging.getLogger("ms_load_from_zoho.shipments")

# ---- Métricas (no-op fallback)
try:
    from ms_load_from_zoho.metrics import set_metrics as _set_metrics, now_iso as _now_iso
except Exception:
    def _set_metrics(*args, **kwargs): ...
    def _now_iso():
        return datetime.now(timezone.utc).isoformat()

# ==== Config por ENV ====
LIST_PER_PAGE                 = int(os.getenv("ZOHO_LIST_PER_PAGE", "50"))
LIST_TIMEOUT_SEC              = float(os.getenv("ZOHO_LIST_TIMEOUT_SEC", "60"))
DETAIL_TIMEOUT_SEC            = float(os.getenv("ZOHO_DETAIL_TIMEOUT_SEC", "10"))

ZOHO_MAX_PAGES                = int(os.getenv("ZOHO_MAX_PAGES", "50"))
ZOHO_LIST_PAGE_DELAY_SEC      = float(os.getenv("ZOHO_LIST_PAGE_DELAY_SEC", "0.5"))

# Concurrencia y throttling (dejamos workers=1 por diseño anti-429)
ZOHO_WORKERS_SHIP             = 1
ZOHO_WORKERS_PKG              = 1
ZOHO_DETAIL_THROTTLE_SEC      = float(os.getenv("ZOHO_DETAIL_THROTTLE_SEC", "0.05"))

# Timeouts reales (connect/read) para requests
CONNECT_TO                    = float(os.getenv("ZOHO_CONNECT_TIMEOUT_SEC", "8"))
READ_TO                       = float(os.getenv("ZOHO_READ_TIMEOUT_SEC", "12"))

# Control de 429
ZOHO_MAX_RETRY_AFTER_SEC      = float(os.getenv("ZOHO_MAX_RETRY_AFTER_SEC", "0"))  # 0 => skip siempre

# Límites duros para no colgar
ZOHO_MAX_DETAILS_PER_RUN_SHIP = int(os.getenv("ZOHO_MAX_DETAILS_PER_RUN_SHIP", "20"))
ZOHO_MAX_DETAILS_PER_RUN_PKG  = int(os.getenv("ZOHO_MAX_DETAILS_PER_RUN_PKG",  "40"))
ZOHO_MAX_RUN_SECONDS          = int(os.getenv("ZOHO_MAX_RUN_SECONDS", "120"))     # 2 min cap

# Orden del listado
ZOHO_SORT_COLUMN              = os.getenv("ZOHO_SORT_COLUMN", "last_modified_time")
ZOHO_SORT_ORDER               = os.getenv("ZOHO_SORT_ORDER", "D")  # D=desc, A=asc

# ==== Utils ====
def _parse_zoho_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S"):
        try:
            dt_ = datetime.strptime(value, fmt)
            if dt_.tzinfo is None:
                dt_ = dt_.replace(tzinfo=timezone.utc)
            return dt_
        except Exception:
            continue
    return None

def _parse_zoho_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None

def _lm_any(it: Dict[str, Any]) -> Optional[datetime]:
    return (
        _parse_zoho_ts(it.get("last_modified_time"))
        or _parse_zoho_ts(it.get("updated_time"))
        or _parse_zoho_ts(it.get("created_time"))
        or _parse_zoho_date(it.get("date"))
    )

def _iso_zoho_midnight_utc(d: datetime) -> str:
    d_utc = d.astimezone(timezone.utc)
    at_midnight = datetime(d_utc.year, d_utc.month, d_utc.day, tzinfo=timezone.utc)
    return at_midnight.strftime("%Y-%m-%dT00:00:00+0000")

def _new_session() -> requests.Session:
    return helpers._retry_session()

# ==== GET “ligero” para details (NO duerme con 429) ====
class ZohoTooManyRequests(RuntimeError):
    def __init__(self, url: str, retry_after: Optional[float]):
        super().__init__(f"429 on {url} (Retry-After={retry_after})")
        self.url = url
        self.retry_after = retry_after

def _extract_retry_after(resp: requests.Response) -> Optional[float]:
    ra = resp.headers.get("Retry-After")
    if not ra:
        return None
    try:
        return float(ra)
    except Exception:
        return None

def _zoho_get_light(session: requests.Session, url: str, headers: Dict[str, str],
                    params: Dict[str, Any], zoho_org_id: str) -> requests.Response:
    resp = session.get(url, headers=headers, params=params, timeout=(CONNECT_TO, READ_TO))
    if resp.status_code == 401:
        logger.warning("401 -> refreshing token")
        new_token = helpers.refresh_zoho_access_token(zoho_org_id)
        headers["Authorization"] = f"Zoho-oauthtoken {new_token}"
        resp = session.get(url, headers=headers, params=params, timeout=(CONNECT_TO, READ_TO))

    if resp.status_code == 429:
        ra = _extract_retry_after(resp)
        if ra is None or ra <= ZOHO_MAX_RETRY_AFTER_SEC:
            # RA pequeño/ausente: dejamos que tenacity reintente con backoff corto
            raise ZohoTooManyRequests(url, ra)
        # RA alto: devolvemos para SKIP inmediato
        return resp

    return resp

# ==== Fetchers (DETALLE) ====
@retry(
    retry=retry_if_exception_type((ZohoTooManyRequests, requests.exceptions.RequestException)),
    wait=wait_exponential(multiplier=0.3, min=0.3, max=1.0),
    stop=stop_after_attempt(2),
    reraise=True,
)
def fetch_shipment_details(list_item: Dict[str, Any], headers: Dict[str, str], zoho_org_id: str) -> Optional[Dict[str, Any]]:
    sid = list_item.get("shipment_id")
    if not sid:
        return None
    url = f"{settings.ZOHO_INVENTORY_SHIPMENTS_URL}/{sid}"
    with _new_session() as s:
        resp = _zoho_get_light(s, url, headers, {}, zoho_org_id)
    if resp.status_code == 429:
        ra = _extract_retry_after(resp)
        logger.warning("429 %s (Retry-After=%ss) -> SKIP shipment detail", url, ra)
        return None
    resp.raise_for_status()
    if ZOHO_DETAIL_THROTTLE_SEC > 0:
        time.sleep(ZOHO_DETAIL_THROTTLE_SEC)
    return resp.json().get("shipmentorder")

@retry(
    retry=retry_if_exception_type((ZohoTooManyRequests, requests.exceptions.RequestException)),
    wait=wait_exponential(multiplier=0.3, min=0.3, max=1.0),
    stop=stop_after_attempt(2),
    reraise=True,
)
def fetch_package(package_id: str, headers: Dict[str, str], zoho_org_id: str) -> Optional[Dict[str, Any]]:
    if not package_id:
        return None
    url = f"{settings.ZOHO_INVENTORY_PACKAGES_URL}/{package_id}"
    with _new_session() as s:
        resp = _zoho_get_light(s, url, headers, {}, zoho_org_id)
    if resp.status_code == 429:
        ra = _extract_retry_after(resp)
        logger.warning("429 %s (Retry-After=%ss) -> SKIP package detail", url, ra)
        return None
    resp.raise_for_status()
    if ZOHO_DETAIL_THROTTLE_SEC > 0:
        time.sleep(ZOHO_DETAIL_THROTTLE_SEC)
    return resp.json().get("package")

# ==== Servicio principal ====
def load_shipments_service(*, start_date: Optional[str], zoho_org_id: str) -> Dict[str, Any]:
    t0 = time.time()
    list_calls = shipment_detail_calls = package_calls = 0
    created = updated = 0
    status = "ok"
    hit_max_pages = False

    logger.info("ZOHO: shipments START")
    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    if not app_config:
        raise RuntimeError(f"AppConfig not found for zoho_org_id={zoho_org_id}")

    # start_date por defecto = last_sync o hoy
    if not start_date:
        last_sync = SyncMetadata.get_last_sync_date("last_sync_date_shipments")
        base = datetime.now(timezone.utc)
        try:
            if last_sync:
                base = datetime.strptime(last_sync, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            pass
        start_date = base.strftime("%Y-%m-%d")

    start_anchor = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    last_modified_time = _iso_zoho_midnight_utc(start_anchor)  # Zoho espera '...T00:00:00+0000'
    cutoff_dt = _parse_zoho_ts(last_modified_time)

    logger.info(
        "ZOHO: shipments org=%s start=%s last_modified_time=%s (cutoff=%s)",
        zoho_org_id, start_date, last_modified_time, cutoff_dt.isoformat() if cutoff_dt else None,
    )

    # Headers para Zoho
    try:
        headers = helpers.config_headers(zoho_org_id)
    except Exception as e:
        logger.error(f"Error connecting to Zoho API (headers): {e}")
        status = "error"
        _set_metrics(
            "shipments", last_run=_now_iso(),
            last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_shipments") or "",
            list_calls=list_calls, detail_calls=shipment_detail_calls, package_calls=package_calls,
            created=created, updated=updated, duration_sec=round(time.time()-t0, 3), status=status,
        )
        return {"status": "error", "message": str(e)}

    # -------- Listado --------
    url = settings.ZOHO_INVENTORY_SHIPMENTS_URL
    params = {
        "organization_id": app_config.zoho_org_id,
        "per_page": LIST_PER_PAGE,
        "page": 1,
        "last_modified_time": last_modified_time,
        "sort_column": ZOHO_SORT_COLUMN,
        "sort_order": ZOHO_SORT_ORDER,
    }

    items_list: List[Dict[str, Any]] = []
    page = 1

    with _new_session() as session:
        while True:
            try:
                params["page"] = page
                resp = helpers.zoho_get(session, url, headers, params, zoho_org_id, logger, timeout=LIST_TIMEOUT_SEC)
                list_calls += 1
                resp.raise_for_status()
                payload = resp.json() if resp.content else {}
                batch = payload.get("shipmentorders", []) or []
                items_list.extend(batch)

                if batch:
                    ts_vals = [ts for ts in (_lm_any(x) for x in batch) if ts]
                    first_lm = max(ts_vals) if ts_vals else None
                    last_lm  = min(ts_vals) if ts_vals else None
                    logger.info(
                        "Shipments page=%s got=%s lm_first=%s lm_last=%s cutoff=%s",
                        page, len(batch),
                        first_lm.isoformat() if first_lm else None,
                        last_lm.isoformat()  if last_lm  else None,
                        cutoff_dt.isoformat() if cutoff_dt else None
                    )
                    # EARLY STOP por cutoff (un día)
                    if last_lm and cutoff_dt and last_lm < cutoff_dt:
                        logger.info("Stopping paging: last_lm < cutoff (page=%s)", page)
                        break

                page_ctx = payload.get("page_context", {}) or {}
                has_more = bool(page_ctx.get("has_more_page"))
                logger.info("Shipments list page=%s got=%s has_more=%s", page, len(batch), has_more)

                if not has_more or page >= ZOHO_MAX_PAGES:
                    hit_max_pages = page >= ZOHO_MAX_PAGES and has_more
                    break

                page += 1
                time.sleep(ZOHO_LIST_PAGE_DELAY_SEC)

            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching shipments list (page={page}): {e}")
                status = "error"
                _set_metrics(
                    "shipments", last_run=_now_iso(),
                    last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_shipments") or "",
                    list_calls=list_calls, detail_calls=shipment_detail_calls, package_calls=package_calls,
                    created=created, updated=updated, duration_sec=round(time.time()-t0, 3), status=status,
                )
                return {"status": "error", "message": "Failed to fetch shipments"}

    # Orden local por LM desc (por seguridad)
    def _lm_dt(s: Dict[str, Any]) -> datetime:
        return _lm_any(s) or datetime.min.replace(tzinfo=timezone.utc)
    items_list.sort(key=_lm_dt, reverse=True)

    # -------- Decide quién necesita detalle --------
    shipment_ids_list = [it.get("shipment_id") for it in items_list if it.get("shipment_id")]
    existing_shipments = ZohoShipmentOrder.objects(Q(shipment_id__in=shipment_ids_list))
    existing_map = {s.shipment_id: _parse_zoho_ts(s.last_modified_time) for s in existing_shipments}

    def _needs_detail(list_item: Dict[str, Any]) -> bool:
        sid = list_item.get("shipment_id")
        if not sid:
            return False
        listed_lm = _lm_any(list_item)
        if cutoff_dt and listed_lm and listed_lm < cutoff_dt:
            return False
        prev_lm = existing_map.get(sid)
        if prev_lm is None:
            return True
        if listed_lm and prev_lm and listed_lm > prev_lm:
            return True
        return False

    detail_candidates_all = [it for it in items_list if _needs_detail(it)]
    detail_candidates = detail_candidates_all[:ZOHO_MAX_DETAILS_PER_RUN_SHIP]
    omitted = max(0, len(detail_candidates_all) - len(detail_candidates))
    logger.info(
        "ZOHO: shipments DETAILS candidates=%s (from listed=%s) cutoff=%s",
        len(detail_candidates), len(items_list), cutoff_dt.isoformat() if cutoff_dt else None
    )
    if omitted:
        logger.warning("Detail candidates capped: %s omitted (limit=%s)", omitted, ZOHO_MAX_DETAILS_PER_RUN_SHIP)

    # -------- Details SHIPMENTS (SECUENCIAL) --------
    full_items: List[Dict[str, Any]] = []
    start_run = time.time()

    def _time_left_ok() -> bool:
        return (time.time() - start_run) < ZOHO_MAX_RUN_SECONDS

    processed = 0
    for it in detail_candidates:
        if not _time_left_ok():
            logger.warning("Budget time exhausted for shipment details -> breaking")
            break
        try:
            r = fetch_shipment_details(it, headers, zoho_org_id)
        except Exception as e:
            logger.warning("Shipment detail error sid=%s: %s", it.get("shipment_id"), e)
            r = None
        if r:
            full_items.append(r)
        processed += 1
        # log SIEMPRE por ítem (para que veas avance continuo)
        logger.info("Shipment details progress %s/%s (sid=%s)", processed, len(detail_candidates), it.get("shipment_id"))
        if ZOHO_DETAIL_THROTTLE_SEC > 0:
            time.sleep(ZOHO_DETAIL_THROTTLE_SEC)

    shipment_detail_calls = processed
    logger.info("ZOHO: shipments DETAILS fetched=%s (candidates_tried=%s)", len(full_items), shipment_detail_calls)

    # -------- Packages (SECUENCIAL) --------
    all_package_ids: List[str] = []
    for sh in full_items:
        for pkg in (sh.get("packages") or []):
            pid = pkg.get("package_id") if isinstance(pkg, dict) else pkg
            if pid:
                all_package_ids.append(pid)
    all_package_ids = sorted(set(all_package_ids))
    if len(all_package_ids) > ZOHO_MAX_DETAILS_PER_RUN_PKG:
        logger.warning("Package detail ids capped: %s -> %s (limit)", len(all_package_ids), ZOHO_MAX_DETAILS_PER_RUN_PKG)
        all_package_ids = all_package_ids[:ZOHO_MAX_DETAILS_PER_RUN_PKG]

    logger.info("ZOHO: shipments PACKAGES ids=%s (unique) for %s shipments with detail",
                len(all_package_ids), len(full_items))

    all_packages_data: List[Dict[str, Any]] = []
    done_pkg = 0
    for pid in all_package_ids:
        if not _time_left_ok():
            logger.warning("Max run seconds reached during package details -> stopping")
            break
        try:
            pkg = fetch_package(pid, headers, zoho_org_id)
        except Exception as e:
            logger.warning("Package detail error pid=%s: %s", pid, e)
            pkg = None
        if pkg:
            all_packages_data.append(pkg)
        done_pkg += 1
        if done_pkg % 10 == 0:
            logger.info("Package details progress %s/%s (last=%s)", done_pkg, len(all_package_ids), pid)
        if ZOHO_DETAIL_THROTTLE_SEC > 0:
            time.sleep(ZOHO_DETAIL_THROTTLE_SEC)

    package_calls = done_pkg

    # -------- Persistencia packages --------
    exist_pkg_ids = set()
    if all_package_ids:
        existing_packages = ZohoPackage.objects(package_id__in=all_package_ids)
        exist_pkg_ids = set(existing_packages.distinct("package_id"))

    new_pkgs, upd_pkgs = [], []
    for pkg_data in all_packages_data:
        new_pkg = create_inventory_package_instance(logger, pkg_data, zoho_org_id=zoho_org_id)
        if not new_pkg:
            continue
        if new_pkg.package_id in exist_pkg_ids:
            upd_pkgs.append(new_pkg)
        else:
            new_pkgs.append(new_pkg)

    if new_pkgs:
        ZohoPackage.objects.insert(new_pkgs, load_bulk=False)
    for pkg in upd_pkgs:
        obj = ZohoPackage.objects(package_id=pkg.package_id).first()
        if obj:
            for f in pkg._fields:
                if f in ("id",):
                    continue
                setattr(obj, f, getattr(pkg, f))
            obj.save()

    # -------- Persistencia shipments --------
    exist_ship_ids = set()
    shipments_ids = [it.get("shipment_id") for it in full_items if it.get("shipment_id")]
    if shipments_ids:
        existing_shipments2 = ZohoShipmentOrder.objects(Q(shipment_id__in=shipments_ids))
        exist_ship_ids = set(existing_shipments2.distinct("shipment_id"))

    new_ships, upd_ships = [], []
    for data_item in full_items:
        new_item = create_inventory_shipment_instance(logger, data_item, zoho_org_id)
        if not new_item:
            continue
        if new_item.shipment_id in exist_ship_ids:
            upd_ships.append(new_item)
        else:
            new_ships.append(new_item)

    if new_ships:
        ZohoShipmentOrder.objects.insert(new_ships, load_bulk=False)
        created = len(new_ships)

    if upd_ships:
        for sh in upd_ships:
            obj = ZohoShipmentOrder.objects(shipment_id=sh.shipment_id).first()
            if obj:
                for f in sh._fields:
                    if f in ("id",):
                        continue
                    setattr(obj, f, getattr(sh, f))
                obj.save()
        updated = len(upd_ships)

    # Actualiza last_sync_date solo si no fue parcial por límites/tiempo
    partial_by_limits = (omitted > 0) or (not _time_left_ok())
    if not (hit_max_pages or partial_by_limits) and status == "ok":
        SyncMetadata.update_last_sync_date(
            "last_sync_date_shipments",
            datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )

    duration = round(time.time() - t0, 3)
    final_status = "partial" if (hit_max_pages or partial_by_limits) else status
    _set_metrics(
        "shipments",
        last_run=_now_iso(),
        last_sync_date=SyncMetadata.get_last_sync_date("last_sync_date_shipments") or "",
        list_calls=list_calls, detail_calls=shipment_detail_calls, package_calls=package_calls,
        created=created, updated=updated, duration_sec=duration, status=final_status,
    )

    logger.info("Shipments processed: %s created, %s updated (status=%s, hit_max_pages=%s, partial_by_limits=%s)",
                created, updated, final_status, hit_max_pages, partial_by_limits)
    logger.info(
        "ZOHO: shipments DONE status=%s created=%s updated=%s list_calls=%s detail_calls=%s package_calls=%s duration=%.2fs",
        final_status, created, updated, list_calls, shipment_detail_calls, package_calls, duration
    )
    return {
        "status": final_status,
        "created": created, "updated": updated,
        "list_calls": list_calls, "detail_calls": shipment_detail_calls, "package_calls": package_calls,
        "duration_sec": duration,
        "start_date": start_date, "zoho_org_id": zoho_org_id,
        "hit_max_pages": hit_max_pages, "cutoff": last_modified_time,
        "limits": {
            "omitted_ship_details": omitted,
            "max_details_ship": ZOHO_MAX_DETAILS_PER_RUN_SHIP,
            "max_details_pkg": ZOHO_MAX_DETAILS_PER_RUN_PKG,
            "max_run_seconds": ZOHO_MAX_RUN_SECONDS,
        },
        "sort": {"column": ZOHO_SORT_COLUMN, "order": ZOHO_SORT_ORDER},
    }

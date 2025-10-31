# ms_load_from_zoho/metrics.py
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, Optional, List

try:
    from django.core.cache import cache
except Exception:
    cache = None  # fallback a memoria

_LOCK = threading.RLock()
_CACHE_KEY = "zoho_loader_metrics_v1"     # snapshot actual
_CACHE_HISTORY_KEY = "zoho_loader_metrics_history_v1"  # histórico circular
_HISTORY_MAX = 200  # entradas máx. por tipo

# Estructura por tipo (e.g. "shipments"):
# {
#   'last_run': ISO,
#   'last_sync_date': 'YYYY-MM-DD'| '',
#   'list_calls': int,
#   'detail_calls': int,
#   'package_calls': int,
#   'created': int,
#   'updated': int,
#   'duration_sec': float,
#   'status': 'ok'|'error',
# }

from datetime import datetime, timezone

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def _get_store() -> Dict[str, Dict[str, Any]]:
    """Lee snapshot desde cache o memoria."""
    if cache is None:
        # fallback en memoria
        if not hasattr(_get_store, "_MEM"):
            _get_store._MEM = {}
        return _get_store._MEM  # type: ignore[attr-defined]
    data = cache.get(_CACHE_KEY)
    return data or {}

def _set_store(data: Dict[str, Dict[str, Any]]) -> None:
    if cache is None:
        _get_store._MEM = data  # type: ignore[attr-defined]
        return
    cache.set(_CACHE_KEY, data, timeout=None)

def _get_history() -> Dict[str, List[Dict[str, Any]]]:
    if cache is None:
        if not hasattr(_get_history, "_MEM_H"):
            _get_history._MEM_H = {}
        return _get_history._MEM_H  # type: ignore[attr-defined]
    data = cache.get(_CACHE_HISTORY_KEY)
    return data or {}

def _set_history(hist: Dict[str, List[Dict[str, Any]]]) -> None:
    if cache is None:
        _get_history._MEM_H = hist  # type: ignore[attr-defined]
        return
    cache.set(_CACHE_HISTORY_KEY, hist, timeout=None)

def set_metrics(
    kind: str,
    *,
    last_run: str,
    last_sync_date: str = "",
    list_calls: int = 0,
    detail_calls: int = 0,
    package_calls: int = 0,
    created: int = 0,
    updated: int = 0,
    duration_sec: float = 0.0,
    status: str = "ok",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Guarda un snapshot para `kind` (p.ej. 'shipments') y
    agrega una entrada al histórico (recorta a _HISTORY_MAX).
    """
    entry: Dict[str, Any] = {
        "last_run": last_run,
        "last_sync_date": last_sync_date or "",
        "list_calls": int(list_calls),
        "detail_calls": int(detail_calls),
        "package_calls": int(package_calls),
        "created": int(created),
        "updated": int(updated),
        "duration_sec": float(duration_sec),
        "status": status,
    }
    if extra:
        entry.update(extra)

    with _LOCK:
        store = _get_store()
        store[kind] = entry
        _set_store(store)

        hist = _get_history()
        arr = hist.get(kind, [])
        arr.append(entry)
        if len(arr) > _HISTORY_MAX:
            arr = arr[-_HISTORY_MAX:]
        hist[kind] = arr
        _set_history(hist)

def get_metrics_snapshot() -> Dict[str, Dict[str, Any]]:
    """Devuelve el snapshot actual de todos los tipos."""
    with _LOCK:
        return dict(_get_store())

def get_metrics_history(kind: Optional[str] = None, limit: int = 50) -> Dict[str, List[Dict[str, Any]]]:
    """Devuelve histórico (global o por tipo)."""
    with _LOCK:
        hist = _get_history()
        if kind:
            return {kind: hist.get(kind, [])[-limit:]}
        # limitar cada arreglo para no inundar respuestas
        return {k: v[-limit:] for k, v in hist.items()}

def clear_metrics(kind: Optional[str] = None) -> None:
    """Borra snapshot/histórico (global o por tipo)."""
    with _LOCK:
        if kind is None:
            _set_store({})
            _set_history({})
            return
        store = _get_store()
        store.pop(kind, None)
        _set_store(store)

        hist = _get_history()
        hist.pop(kind, None)
        _set_history(hist)

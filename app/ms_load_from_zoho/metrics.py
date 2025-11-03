from __future__ import annotations
from datetime import datetime, timezone, date
from typing import Optional, Dict, Any, Union, List

from .models import IntegrationMetrics

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _coerce_date(d: Optional[str | date]) -> Optional[date]:
    if not d:
        return None
    if isinstance(d, date):
        return d
    try:
        # 'YYYY-MM-DD'
        return datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:
        return None

def set_metrics(
    module: str,
    *,
    zoho_org_id: str,
    last_run: Optional[str] = None,
    last_sync_date: Optional[str | date] = None,
    list_calls: int = 0,
    detail_calls: int = 0,
    package_calls: int = 0,
    created: int = 0,
    updated: int = 0,
    duration_sec: float = 0.0,
    status: str = "ok",
) -> Dict[str, Any]:
    """
    Upsert por (module, zoho_org_id) guardando la última corrida.
    """
    lr_dt = datetime.now(timezone.utc) if not last_run else datetime.strptime(
        last_run, "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=timezone.utc)

    lsd = _coerce_date(last_sync_date)

    doc = IntegrationMetrics.objects(module=module, zoho_org_id=zoho_org_id).order_by("-last_run_dt").first()
    if not doc:
        doc = IntegrationMetrics(module=module, zoho_org_id=zoho_org_id, last_run_dt=lr_dt)

    # set/update
    doc.last_run_dt = lr_dt
    if lsd is not None:
        doc.last_sync_date = lsd

    doc.list_calls = int(list_calls or 0)
    doc.detail_calls = int(detail_calls or 0)
    doc.package_calls = int(package_calls or 0)
    doc.created = int(created or 0)
    doc.updated = int(updated or 0)
    doc.duration_sec = float(duration_sec or 0.0)
    doc.status = status or "ok"
    doc.updated_at = datetime.now(timezone.utc)
    doc.save()

    return {
        "module": module,
        "zoho_org_id": zoho_org_id,
        "last_run": lr_dt.isoformat(),
        "last_sync_date": doc.last_sync_date.isoformat() if doc.last_sync_date else "",
        "list_calls": doc.list_calls,
        "detail_calls": doc.detail_calls,
        "package_calls": doc.package_calls,
        "created": doc.created,
        "updated": doc.updated,
        "duration_sec": doc.duration_sec,
        "status": doc.status,
    }

def get_latest_metrics(
    module: str,
    *,
    zoho_org_id: Optional[str] = None
) -> Union[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """
    - Si se pasa `zoho_org_id`: retorna el último doc de ese módulo para esa org (mismo contrato que ya tenías).
    - Si NO se pasa `zoho_org_id`: retorna un dict {org_id: metrics_dict} con el último doc por cada org.
    """

    def _to_payload(doc: IntegrationMetrics) -> Dict[str, Any]:
        return {
            "zoho_org_id": doc.zoho_org_id,
            "last_run": doc.last_run_dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if doc.last_run_dt else "",
            "last_sync_date": doc.last_sync_date.isoformat() if getattr(doc, "last_sync_date", None) else "",
            "list_calls": doc.list_calls or 0,
            "detail_calls": doc.detail_calls or 0,
            "package_calls": doc.package_calls or 0,
            "created": doc.created or 0,
            "updated": doc.updated or 0,
            "duration_sec": float(doc.duration_sec or 0.0),
            "status": doc.status or "",
        }

    # Modo 1: con filtro de org -> mismo comportamiento anterior
    if zoho_org_id:
        q = IntegrationMetrics.objects(module=module, zoho_org_id=zoho_org_id).order_by("-last_run_dt").first()
        if not q:
            return {
                "zoho_org_id": zoho_org_id,
                "last_run": "",
                "last_sync_date": "",
                "list_calls": 0, "detail_calls": 0, "package_calls": 0,
                "created": 0, "updated": 0,
                "duration_sec": 0.0, "status": "",
            }
        return _to_payload(q)

    # Modo 2: sin filtro -> último por CADA org del módulo
    # Intento 2.1: pipeline de agregación (eficiente)
    try:
        coll = IntegrationMetrics._get_collection()
        cursor = coll.aggregate([
            {"$match": {"module": module}},
            {"$sort": {"zoho_org_id": 1, "last_run_dt": -1}},           # ordena por org asc y last_run desc
            {"$group": {                                              # te quedas con el PRIMERO por org
                "_id": "$zoho_org_id",
                "doc": {"$first": "$$ROOT"}
            }},
        ])
        per_org: Dict[str, Dict[str, Any]] = {}
        for row in cursor:
            d = row.get("doc") or {}
            payload = {
                "zoho_org_id": d.get("zoho_org_id", ""),
                "last_run": (d.get("last_run_dt") or "").strftime("%Y-%m-%dT%H:%M:%SZ") if d.get("last_run_dt") else "",
                "last_sync_date": d.get("last_sync_date").isoformat() if d.get("last_sync_date") else "",
                "list_calls": int(d.get("list_calls", 0)),
                "detail_calls": int(d.get("detail_calls", 0)),
                "package_calls": int(d.get("package_calls", 0)),
                "created": int(d.get("created", 0)),
                "updated": int(d.get("updated", 0)),
                "duration_sec": float(d.get("duration_sec", 0.0)),
                "status": d.get("status", ""),
            }
            per_org[payload["zoho_org_id"]] = payload
        
        if not per_org:
            return {}
        return per_org

    except Exception:
        docs: List[IntegrationMetrics] = list(
            IntegrationMetrics.objects(module=module).order_by("-last_run_dt", "zoho_org_id")
        )
        per_org: Dict[str, Dict[str, Any]] = {}
        seen: set[str] = set()
        for d in docs:
            if d.zoho_org_id in seen:
                continue
            per_org[d.zoho_org_id] = _to_payload(d)
            seen.add(d.zoho_org_id)
        return per_org
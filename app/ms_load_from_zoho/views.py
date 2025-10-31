from django.conf import settings
from ms_load_from_zoho.metrics import get_latest_metrics
from ms_load_from_zoho import extra_views
from ms_load_from_zoho.service_customers import load_customers_service
from ms_load_from_zoho.service_invoices import load_invoices_service
from ms_load_from_zoho.service_items import load_items_service
from ms_load_from_zoho.service_sales_orders import load_sales_orders_service
from datetime import datetime as dt, timezone as tz
from typing import Optional
from django.http import JsonResponse
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.contrib.auth.decorators import login_required
from ms_load_from_zoho.models import (
                      SyncMetadata,
                    )

from typing import Dict, Optional
from ms_load_from_zoho.service_shipments import load_shipments_service
import json
import logging
import ms_load_from_zoho.helpers as helpers


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# =========================
# MÉTRICAS EN MEMORIA
# =========================
METRICS = {
    # Ejemplo de estructura por módulo:
    # 'salesorders': {
    #   'last_run': '2025-10-29T12:34:56Z',
    #   'last_sync_date': '2025-10-29',
    #   'list_calls': 0, 'detail_calls': 0, 'package_calls': 0,
    #   'created': 0, 'updated': 0,
    #   'duration_sec': 0.0, 'status': 'ok'|'error'
    # }
}

def _now_iso():
    return dt.now(tz.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def _parse_zoho_ts(s: str):
    if not s:
        return None
    try:
        return dt.strptime(s, '%Y-%m-%dT%H:%M:%S%z')
    except Exception:
        return None

def _set_metrics(mod, **kwargs):
    entry = METRICS.get(mod, {})
    entry.update(kwargs)
    METRICS[mod] = entry

# =========================
# AUTH / SETTINGS (igual)
# =========================

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def generate_auth_url(request, zoho_org_id):
    return helpers.generate_auth_url(zoho_org_id)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def get_refresh_token(request, zoho_org_id):
    return helpers.get_refresh_token(request, zoho_org_id)

@csrf_exempt
@api_view(['GET'])
@permission_classes([AllowAny])
def zoho_api_settings(request, zoho_org_id):
    return helpers.zoho_api_settings(zoho_org_id)

@login_required(login_url='login')
def zoho_api_connect(request, zoho_org_id):
    return helpers.zoho_api_connect(request, zoho_org_id)


# ----------------------------------------------------------
# MAIN LOAD
# ----------------------------------------------------------

# =========================
# INVENTORY ITEMS
# =========================

@api_view(['POST'])
@permission_classes([AllowAny])
def load_inventory_items(request, zoho_org_id):
    try:
        if request.body:
            data = json.loads(request.body)
        else:
            data = {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    start_date: Optional[str] = data.get("start_date")
    item_number: Optional[str] = data.get("item_number")
    result = load_items_service(zoho_org_id=zoho_org_id, start_date=start_date, item_number=item_number)

    status = 200 if result.get("status") == "ok" else 500
    return JsonResponse(result, status=status)


# ----------------------------------------------------------

# =========================
# SALES ORDERS (optimizado)
# =========================

@api_view(['POST'])
@permission_classes([AllowAny])
def load_inventory_sales_orders(request, zoho_org_id):
    try:
        if request.body:
            data = json.loads(request.body)
        else:
            data = {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    start_date: Optional[str] = data.get("start_date")
    result = load_sales_orders_service(start_date=start_date, zoho_org_id=zoho_org_id)

    status = 200 if result.get("status") == "ok" else 500
    return JsonResponse(result, status=status)

# =========================
# SHIPMENTS + PACKAGES (optimizado)
# =========================

@api_view(["POST"])
@permission_classes([AllowAny])
def load_inventory_shipments(request, zoho_org_id: str):
    
    try:
        if request.body:
            data = json.loads(request.body)
        else:
            data = {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    start_date: Optional[str] = data.get("start_date")
    result = load_shipments_service(start_date=start_date, zoho_org_id=zoho_org_id)

    status = 200 if result.get("status") == "ok" else 500
    return JsonResponse(result, status=status)


# =========================
# BOOKS CUSTOMERS (métrica básica)
# =========================

@api_view(['POST'])
@permission_classes([AllowAny])
def load_books_customers(request, zoho_org_id):
    
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    start_date = data.get("start_date")  # opcional
    result = load_customers_service(start_date=start_date, zoho_org_id=zoho_org_id)

    if result.get("status") in ("ok", "partial"):
        return JsonResponse({"message": "Customers loaded", "result": result}, status=200)

    return JsonResponse({"error": result.get("message", "Unknown error"), "result": result}, status=500)


# =========================
# INVOICES (métrica de list + details)
# =========================

@api_view(['POST'])
@permission_classes([AllowAny])
def load_books_invoices(request, zoho_org_id):
    try:
        if request.body:
            data = json.loads(request.body)
        else:
            data = {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    start_date: Optional[str] = data.get("start_date")
    result = load_invoices_service(zoho_org_id=zoho_org_id, start_date=start_date)

    status = 200 if result.get("status") == "ok" else 500
    return JsonResponse(result, status=status)

            
# =========================
# MÉTRICAS PANEL (JSON/HTML)
# =========================

@api_view(['GET'])
@permission_classes([AllowAny])
def metrics_panel(request):
    fmt = request.GET.get('format')
    
    if not fmt:
        fmt = request.GET.get('?format')
    
    if not fmt and request.path.rstrip('/').endswith('.html'):
        fmt = 'html'
    
    if not fmt:
        accept = request.META.get('HTTP_ACCEPT', '')
        if 'text/html' in accept:
            fmt = 'html'

    fmt = (fmt or 'json').lower()
    
    def _lsd(key):
        return SyncMetadata.get_last_sync_date(key) or ''

    defaults = {
        'items':        {'last_sync_date': _lsd('last_sync_date_items')},
        'salesorders':  {'last_sync_date': _lsd('last_sync_date_salesorders')},
        'shipments':    {'last_sync_date': _lsd('last_sync_date_shipments')},
        'invoices':     {'last_sync_date': _lsd('last_sync_date_invoices')},
        'customers':    {'last_sync_date': _lsd('last_sync_date_customers')},
    }
    
    data = {}
    for mod in ['items','salesorders','shipments','invoices','customers']:
        base = {
            'last_run': '',
            'last_sync_date': defaults.get(mod,{}).get('last_sync_date',''),
            'list_calls': 0, 'detail_calls': 0, 'package_calls': 0,
            'created': 0, 'updated': 0,
            'duration_sec': 0.0, 'status': ''
        }
        base.update(METRICS.get(mod, {}))
        data[mod] = base

    if fmt == 'html':
        rows = []
        header = """
        <tr>
          <th>Module</th>
          <th>Company</th>
          <th>Last Run</th>
          <th>Last Sync</th>
          <th>List Calls</th>
          <th>Detail Calls</th>
          <th>Package Calls</th>
          <th>Created</th>
          <th>Updated</th><th>Duration (s)</th><th>Status</th>
          <th>Duration (s)</th>
          <th>Status</th>
        </tr>"""
        for mod, m in data.items():
            company = 'NWS' if m.get('zoho_org_id', '') == settings.ZOHO_ORG_ID else 'NWSHOME'
            rows.append(f"""
            <tr>
              <td>{mod}</td>
              <td>{company}</td>
              <td>{m['last_run']}</td>
              <td>{m['last_sync_date']}</td>
              <td>{m['list_calls']}</td>
              <td>{m['detail_calls']}</td>
              <td>{m['package_calls']}</td>
              <td>{m['created']}</td>
              <td>{m['updated']}</td>
              <td>{m['duration_sec']}</td>
              <td>{m['status']}</td>
            </tr>""")
        html = f"""
        <html><head><title>Metrics Main Load NWS</title>
        <style>
          body{{font-family:Arial,Helvetica,sans-serif;padding:16px}}
          table{{border-collapse:collapse;width:100%}}
          th,td{{border:1px solid #ddd;padding:8px;text-align:center}}
          th{{background:#f5f5f5}}
        </style></head>
        <body>
          <h2>Metrics of Integrations in Main Load Data Service(last run)</h2>
          <table>{header}{''.join(rows)}</table>
          <p style="margin-top:12px;color:#666">Refresh this page to see the metrics of the latest run.</p>
        </body></html>"""
        return HttpResponse(html)

    return JsonResponse(data, status=200)

MODULES = ['items', 'salesorders', 'shipments', 'invoices', 'customers']

@api_view(['GET'])
@permission_classes([AllowAny])
def metrics_panel(request):
    # ---- detección de formato (igual que antes) ----
    fmt = request.GET.get('format') or request.GET.get('?format')
    if not fmt and request.path.rstrip('/').endswith('.html'):
        fmt = 'html'
    if not fmt:
        accept = request.META.get('HTTP_ACCEPT', '')
        if 'text/html' in accept:
            fmt = 'html'
    fmt = (fmt or 'json').lower()

    # ---- armar data por módulo -> { org_id: metrics } ----
    data: Dict[str, Dict[str, dict]] = {}
    for mod in MODULES:
        # sin zoho_org_id => devuelve el último por cada org de ese módulo
        per_org = get_latest_metrics(mod)  # dict {"774691355": {...}, "881031522": {...}}
        # si tu get_latest_metrics devuelve {}, mantenemos {} para el módulo
        data[mod] = per_org or {}

    # ---- salida HTML ----
    if fmt == 'html':
        header = """
        <tr>
          <th>Module</th><th>Org</th><th>Last Run</th><th>Last Sync</th>
          <th>List Calls</th><th>Detail Calls</th><th>Package Calls</th>
          <th>Created</th><th>Updated</th><th>Duration (s)</th><th>Status</th>
        </tr>"""
        rows = []
        for mod, per_org in data.items():
            if not per_org:
                rows.append(f"""
                <tr>
                  <td>{mod}</td>
                  <td colspan="10" style="color:#999;text-align:center">No data</td>
                </tr>""")
                continue
            for org_id, m in sorted(per_org.items(), key=lambda kv: kv[0]):
                rows.append(f"""
                <tr>
                  <td>{mod}</td>
                  <td>{org_id}</td>
                  <td>{m.get('last_run','')}</td>
                  <td>{m.get('last_sync_date','')}</td>
                  <td>{m.get('list_calls',0)}</td>
                  <td>{m.get('detail_calls',0)}</td>
                  <td>{m.get('package_calls',0)}</td>
                  <td>{m.get('created',0)}</td>
                  <td>{m.get('updated',0)}</td>
                  <td>{m.get('duration_sec',0.0)}</td>
                  <td>{m.get('status','')}</td>
                </tr>""")

        html = f"""
        <html>
          <head>
            <title>Metrics Main Load NWS</title>
            <style>
              body{{font-family:Arial,Helvetica,sans-serif;padding:16px}}
              table{{border-collapse:collapse;width:100%}}
              th,td{{border:1px solid #ddd;padding:8px;text-align:center}}
              th{{background:#f5f5f5}}
              .hint{{margin-top:12px;color:#666}}
            </style>
          </head>
          <body>
            <h2>Metrics of Integrations (last run per org)</h2>
            <table>{header}{''.join(rows)}</table>
            <p class="hint">Refresh this page to see the latest metrics. JSON: add <code>?format=json</code></p>
          </body>
        </html>"""
        return HttpResponse(html)

    # ---- salida JSON ----
    # Estructura: { "items": { "<org>": {...}, ... }, "salesorders": {...}, ... }
    return JsonResponse(data, status=200, safe=True)


# --------------
# OTHERS VIEWS
# --------------

@api_view(['POST'])
@permission_classes([AllowAny])
def load_inventory_sales_orders_by_customer_name(request, zoho_org_id):
    return extra_views.load_inventory_sales_orders_by_customer_name(request, zoho_org_id)


@api_view(['POST'])
@permission_classes([AllowAny])
def load_inventory_sales_orders_to_qbwc(request, zoho_org_id):
    return extra_views.load_inventory_sales_orders_to_qbwc(request, zoho_org_id)

@api_view(['POST'])
@permission_classes([AllowAny])
def load_books_invoices_by_customer_name(request, zoho_org_id):
    return extra_views.load_books_invoices_by_customer_name(request, zoho_org_id)
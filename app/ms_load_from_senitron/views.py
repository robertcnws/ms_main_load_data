from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from dateutil.parser import parse
from datetime import datetime as dt
from django.http import JsonResponse
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from .models import (
                        SenitronItemAsset, 
                        SenitronItem, 
                        SenitronStatus, 
                        SenitronItemAssetLogs,
                    )
from .manage_instances import (
                                create_senitron_item_asset_instance,
                                create_senitron_item_asset_logs_instance
                              )
import requests
import json
import logging


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


MAX_WORKERS = 10
BATCH_SIZE = 500
REQUEST_TIMEOUT = 10

def create_session():
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


#############################################
# LOAD SENITRON INVENTORY ITEM ASSETS
#############################################

@api_view(['POST'])
@permission_classes([AllowAny])
def load_senitron_item_assets(request):
    data = json.loads(request.body) if request.body else {}
    username = data.get('username')
    
    params = {
        'api_key': settings.API_KEY_SENITRON,
        'per_page': 250
    }
    if 'item_number' in data:
        params['item_number'] = data['item_number']
    
    filter_kwargs = {}
    if 'item_number' in data:
        filter_kwargs['item_number'] = data['item_number']
        deleted_count = SenitronItemAsset.objects(**filter_kwargs).delete()
    else:
        deleted_count = SenitronItemAsset.objects().delete()
    logger.info(f"Deleted {deleted_count} SenitronItemAsset records before loading new data")

    existing_statuses = SenitronStatus.objects()
    status_cache = {(s.name, s.senitron_id): s for s in existing_statuses}

    item_numbers = set()
    for item in data.get('assets', []):
        if 'item_number' in item:
            item_numbers.add(item['item_number'])

    existing_items = SenitronItem.objects(item_number__in=list(item_numbers))
    item_cache = {itm.item_number: itm for itm in existing_items}

    url = settings.API_SENITRON_ASSETS_URL
    session = create_session()

    def fetch_and_save_page(page):
        page_params = params.copy()
        page_params['page'] = page
        try:
            response = session.get(url, params=page_params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            items = response.json().get('assets', [])
            
            if 'item_number' in page_params and page_params['item_number'] in item_numbers:
                items = [it for it in items if it.get('item_number') == page_params['item_number']]

            assets = []
            for item_data in items:
                asset = create_senitron_item_asset_instance(
                    logger, 
                    item_data, 
                    status_cache, 
                    item_cache
                )
                if asset:
                    assets.append(asset)

            if assets:
                SenitronItemAsset.objects.insert(assets)

            return len(items) > 0

        except requests.RequestException as e:
            logger.error(f"Error fetching page {page}: {e}")
            return False

    page = 1
    has_more = True

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while has_more:
            futures = {executor.submit(fetch_and_save_page, p): p for p in range(page, page + MAX_WORKERS)}
            has_more = False
            for future in as_completed(futures):
                if future.result():
                    has_more = True
            page += MAX_WORKERS

    logger.info("Senitron Item Assets loaded successfully")
    return JsonResponse({'message': 'Senitron Items Assets loaded successfully'}, status=200)


@api_view(['POST'])
@permission_classes([AllowAny])
def load_senitron_item_assets_logs(request):
    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    username = data.get('username', None)
    now = timezone.now()
    
    last_time_inserted = SenitronItemAssetLogs.objects.order_by('-created_time').first()
    
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if last_time_inserted:
        if timezone.is_naive(last_time_inserted.created_time):
            last_time_inserted_time = timezone.make_aware(last_time_inserted.created_time, dt.now().astimezone().tzinfo)
        else:
            last_time_inserted_time = last_time_inserted.created_time

        diff = now - last_time_inserted_time
    else:
        diff = now - start_of_day

    diff_hours = max(int(diff.total_seconds() // 3600), 1)

    params = {
        'api_key': settings.API_KEY_SENITRON,
        'per_page': 250,
        'filter_hours': diff_hours
    }

    if 'item_number' in data:
        params['item_number'] = data['item_number']

    url = settings.API_SENITRON_ASSETS_LOGS_URL
    session = create_session()
    
    assets_qty = 0

    def fetch_and_save_page(page, assets_qty):
        page_params = params.copy()
        page_params['page'] = page
        try:
            response = session.get(url, params=page_params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            items = response.json().get('assets', [])

            items_map = {}

            for item_data in items:
                serial_number = item_data.get('serial_number')
                current_status = item_data.get('current_status', {})
                current_status_id = current_status.get('id')
                current_status_name = current_status.get('name')
                last_status = item_data.get('last_status', {})
                last_status_id = last_status.get('id')
                last_status_name = last_status.get('name')
                last_seen_str = item_data.get('last_seen')

                if last_seen_str:
                    last_seen_dt = parse(last_seen_str)
                else:
                    continue

                key = (serial_number, current_status_id, current_status_name, last_status_id, last_status_name)

                if key not in items_map or last_seen_dt > items_map[key]['last_seen_dt']:
                    items_map[key] = {
                        'item_data': item_data,
                        'last_seen_dt': last_seen_dt
                    }

            selected_items = [
                v['item_data'] for v in items_map.values()
                if v['item_data']['current_status']['id'] != v['item_data']['last_status']['id']
            ]
            
            assets_qty += len(selected_items)

            assets = []
            for item_data in selected_items:
                asset = create_senitron_item_asset_logs_instance(logger, item_data)
                if asset:
                    assets.append(asset)

            if assets:
                SenitronItemAssetLogs.objects.insert(assets, load_bulk=False)
            
            return len(items) > 0
        except requests.RequestException as e:
            logger.error(f"Error fetching page {page}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error on page {page}: {e}")
            return False

    page = 1
    has_more = True

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while has_more:
            futures = {executor.submit(fetch_and_save_page, p, assets_qty): p for p in range(page, page + MAX_WORKERS)}
            has_more = False

            for future in as_completed(futures):
                page_result = future.result()
                if page_result:
                    has_more = True
            page += MAX_WORKERS
            
    logger.info(f"Senitron Item Assets Logs loaded successfully. Total assets: {assets_qty}")

    return JsonResponse({'message': 'Senitron Items Assets Logs loaded successfully'}, status=200)

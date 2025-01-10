from celery import shared_task
from datetime import datetime
from django.http import HttpRequest
from django.utils import timezone
from .views import (
                    load_senitron_item_assets,
                    load_senitron_item_assets_logs,
                   )
import json
    
@shared_task
def task_load_senitron_items_assets():
    request = HttpRequest()
    request.method = 'POST'
    request.content_type = 'application/json'
    request._body = json.dumps({}).encode('utf-8')
    load_senitron_item_assets(request)
    

@shared_task
def task_load_senitron_items_assets_logs():
    request = HttpRequest()
    request.method = 'POST'
    request.content_type = 'application/json'
    request._body = json.dumps({}).encode('utf-8')
    load_senitron_item_assets_logs(request)
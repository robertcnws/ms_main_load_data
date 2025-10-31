import os, logging
from celery import Celery
# from celery.signals import worker_process_init
# from django.conf import settings
# from .mongo_setup import connect_mongo

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ms_main_load_data.settings')

app = Celery('ms_main_load_data')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.conf.beat_scheduler = 'celery.beat.PersistentScheduler' 

app.autodiscover_tasks()

from django.conf import settings
import logging
logging.getLogger(__name__).info(
    "CELERY BOOT broker=%s backend=%s default_queue=%s",
    getattr(settings, "CELERY_BROKER_URL", None),
    getattr(settings, "CELERY_RESULT_BACKEND", None),
    getattr(settings, "CELERY_TASK_DEFAULT_QUEUE", None),
)

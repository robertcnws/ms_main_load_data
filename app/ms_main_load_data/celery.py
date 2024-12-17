import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ms_main_load_data.settings')

app = Celery('ms_main_load_data')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.conf.beat_scheduler = 'celery.beat.PersistentScheduler' 

app.autodiscover_tasks()

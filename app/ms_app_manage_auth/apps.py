from django.apps import AppConfig
from django.conf import settings
# from ms_main_load_data.mongo_setup import connect_mongo

class MsAppManageAuthConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ms_app_manage_auth'

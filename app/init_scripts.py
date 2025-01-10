# ./django/init_scripts.py
import os
import django
from datetime import datetime
from ms_app_manage_auth.models import LoginUser
from ms_load_from_zoho.models import AppConfig
# from ms_main_load_data.mongo_setup import connect_mongo

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ms_main_load_data.settings')
django.setup()

# connect_mongo()

def create_superuser():
    username = os.getenv('DJANGO_SUPERUSER_USERNAME')
    email = os.getenv('DJANGO_SUPERUSER_EMAIL')
    password = os.getenv('DJANGO_SUPERUSER_PASSWORD')

    if not LoginUser.objects(username=username).first():
        print("Creating superuser...")
        superuser = LoginUser(
            username=username,
            email=email,
            is_staff=True,
            is_active=True,
            date_joined=datetime.now(),
        )
        superuser.set_password(password)
        superuser.save()
        print("Superuser created!")

def create_loginuser():
    username = os.getenv('LOGINUSER_USERNAME')
    email = os.getenv('LOGINUSER_EMAIL')
    password = os.getenv('LOGINUSER_PASSWORD')

    if not LoginUser.objects(username=username).first():
        print("Creating LoginUser...")
        loginuser = LoginUser(
            username=username,
            email=email,
            is_staff=True,
            is_active=True,
            date_joined=datetime.now(),
        )
        loginuser.set_password(password)
        loginuser.save()
        print("LoginUser created!")
        
def create_app_config():
    zoho_org_id = os.getenv('ZOHO_ORG_ID')
    if not AppConfig.objects(zoho_org_id=zoho_org_id).first():
        print("Creating AppConfig...")
        zoho_client_id = os.getenv('ZOHO_CLIENT_ID')
        zoho_client_secret = os.getenv('ZOHO_CLIENT_SECRET')
        zoho_refresh_token = os.getenv('ZOHO_REFRESH_TOKEN')
        zoho_redirect_uri = os.getenv('ZOHO_REDIRECT_URI')
        app_config = AppConfig(
            zoho_org_id=zoho_org_id,
            zoho_client_id=zoho_client_id,
            zoho_client_secret=zoho_client_secret,
            zoho_refresh_token=zoho_refresh_token,
            zoho_redirect_uri=zoho_redirect_uri,
        )
        app_config.save()
        print("AppConfig created!")

if __name__ == "__main__":
    create_superuser()
    create_loginuser()
    create_app_config()

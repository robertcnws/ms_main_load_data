# mongo_setup.py
from django.conf import settings
import mongoengine

def connect_mongo_dev():
    mongoengine.connect(
        db=settings.MONGO_DB,
        host=settings.MONGO_HOST,
        port=settings.MONGO_PORT,
        username=settings.MONGO_USER,
        password=settings.MONGO_PASSWORD,
        authentication_source='admin',
        alias='default'  
    )
    
def connect_mongo_prod():
    mongoengine.connect(
        alias='default',
        host=settings.MONGO_URI
    )

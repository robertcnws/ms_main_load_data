# mongo_setup.py
from django.conf import settings
import mongoengine

def connect_mongo():
    mongoengine.connect(
        db=settings.MONGO_DB,
        host=settings.MONGO_HOST,
        port=settings.MONGO_PORT,
        username=settings.MONGO_USER,
        password=settings.MONGO_PASSWORD,
        authentication_source='admin',
        alias='default'  # Asegura que usas el alias por defecto
    )

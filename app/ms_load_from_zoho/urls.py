# ./django/ms_main_load_data/urls.py

from django.contrib import admin
from django.urls import path, include
from rest_framework_mongoengine import routers   
from . import views

urlpatterns = [
    path("connect/", views.zoho_api_connect, name="zoho_api_connect"),
    path("zoho_api_settings/", views.zoho_api_settings, name="zoho_api_settings"),
    path("generate_auth_url/", views.generate_auth_url, name="generate_auth_url"),
    path("get_refresh_token/", views.get_refresh_token, name="get_refresh_token"),
]

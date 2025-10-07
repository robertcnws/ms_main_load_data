# ./django/ms_main_load_data/urls.py

from django.contrib import admin
from django.urls import path, include
from rest_framework_mongoengine import routers   
from . import views

app_name = 'ms_load_from_zoho'

urlpatterns = [
    path("connect/<str:zoho_org_id>/", views.zoho_api_connect, name="zoho_api_connect"),
    path("zoho_api_settings/<str:zoho_org_id>/", views.zoho_api_settings, name="zoho_api_settings"),
    path("generate_auth_url/<str:zoho_org_id>/", views.generate_auth_url, name="generate_auth_url"),
    path("get_refresh_token/<str:zoho_org_id>/", views.get_refresh_token, name="get_refresh_token"),
    path("load_invoices/customer/<str:zoho_org_id>/", views.load_books_invoices_by_customer_name, name="load_books_invoices_by_customer_name"),
    path("load_sales_orders/customer/<str:zoho_org_id>/", views.load_inventory_sales_orders_by_customer_name, name="load_inventory_sales_orders_by_customer_name"),
    path("load_sales_orders/<str:zoho_org_id>/", views.load_inventory_sales_orders, name="load_inventory_sales_orders"),
    path("load_sales_orders_to_qbwc/<str:zoho_org_id>/", views.load_inventory_sales_orders_to_qbwc, name="load_inventory_sales_orders_to_qbwc"),
]

from django.urls import path
from . import views

urlpatterns = [
    path("item_assets/", views.item_assets, name="item_assets"),
    path("item_assets_logs/", views.item_assets_logs, name="item_assets_logs"),
]
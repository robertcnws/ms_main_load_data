from django.urls import path
from . import views

urlpatterns = [
    path("secure-endpoint/", views.secure_endpoint, name="secure_endpoint"),
    path("items/", views.items, name="items"),
    path("customers/", views.customers, name="customers"),
    path("shipment_orders/", views.shipment_orders, name="shipment_orders"),
    path("sales_orders/", views.sales_orders, name="sales_orders"),
    path("full_sales_orders/", views.full_sales_orders, name="full_sales_orders"),
    path("packages/", views.packages, name="packages"),
    path("invoices/", views.invoices, name="invoices"),
]
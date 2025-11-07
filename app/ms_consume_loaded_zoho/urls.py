from django.urls import path
from . import views

urlpatterns = [
    path("secure-endpoint/", views.secure_endpoint, name="secure_endpoint"),
    path("items/", views.items, name="items"),
    path("itemgroups/", views.itemgroups, name="itemgroups"),
    path("customers/", views.customers, name="customers"),
    path("shipment_orders/", views.shipment_orders, name="shipment_orders"),
    path("sales_orders/", views.sales_orders, name="sales_orders"),
    path("full_sales_orders/", views.full_sales_orders, name="full_sales_orders"),
    path("sales_orders_to_service/", views.sales_orders_to_service, name="sales_orders_to_service"),
    path("invoices_to_rewards_points/", views.invoices_to_rewards_points, name="invoices_to_rewards_points"),
    path("refetch_salesorder/<str:zoho_org_id>/<str:salesorder_number>/", views.refetch_salesorder, name="refetch_salesorder"),
    path("packages/", views.packages, name="packages"),
    path("invoices/", views.invoices, name="invoices"),
    path("delete/sales_orders/", views.delete_sales_orders, name="delete_sales_orders"),
]
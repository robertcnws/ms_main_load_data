from django.urls import path
from . import views

urlpatterns = [
    path("secure-endpoint/", views.secure_endpoint, name="secure_endpoint"),
    path("items/", views.items, name="items"),
]
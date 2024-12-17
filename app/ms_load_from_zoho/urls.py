# ./django/ms_main_load_data/urls.py

from django.contrib import admin
from django.urls import path, include
from rest_framework_mongoengine import routers   
from .views import LoginUserViewSet  

router = routers.DefaultRouter()
router.register(r'login-users', LoginUserViewSet)

urlpatterns = [
    path('/', include(router.urls)),
]

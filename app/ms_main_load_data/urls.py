"""
URL configuration for ms_main_load_data project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.urls import path
from django.urls import include
import ms_app_manage_auth.views as ms_app_manage_auth

urlpatterns = [
    path('api/zoho/', include('ms_load_from_zoho.urls')),
    path('api/manage/', include('ms_app_manage_auth.urls')),
    path('api/consume/zoho/', include('ms_consume_loaded_zoho.urls')),
    path('api/consume/senitron/', include('ms_consume_loaded_senitron.urls')),
    path('api/', ms_app_manage_auth.MainManageAuthView.as_view(), name='main_manage_auth'),
    path('health-check/', ms_app_manage_auth.health_check, name='health_check'),
    path('', ms_app_manage_auth.MainManageAuthView.as_view(), name='main_manage_auth'),
]

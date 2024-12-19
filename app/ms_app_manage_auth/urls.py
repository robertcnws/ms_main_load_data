# tu_app/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # URLs para System
    path('auth/systems/', views.SystemListView.as_view(), name='system_list'),
    path('auth/systems/create/', views.SystemCreateView.as_view(), name='system_create'),
    path('auth/systems/edit/<str:pk>/', views.SystemUpdateView.as_view(), name='system_update'),
    path('auth/systems/delete/<str:pk>/', views.SystemDeleteView.as_view(), name='system_delete'),
    
    # URLs para ModuleSystem
    path('auth/modules/', views.ModuleSystemListView.as_view(), name='module_system_list'),
    path('auth/modules/create/', views.ModuleSystemCreateView.as_view(), name='module_system_create'),
    path('auth/modules/edit/<str:pk>/', views.ModuleSystemUpdateView.as_view(), name='module_system_update'),
    path('auth/modules/delete/<str:pk>/', views.ModuleSystemDeleteView.as_view(), name='module_system_delete'),
    
    # URLs para PermissionModuleSystem
    path('auth/permissions/', views.PermissionModuleSystemListView.as_view(), name='permission_module_system_list'),
    path('auth/permissions/create/', views.PermissionModuleSystemCreateView.as_view(), name='permission_module_system_create'),
    path('auth/permissions/edit/<str:pk>/', views.PermissionModuleSystemUpdateView.as_view(), name='permission_module_system_update'),
    path('auth/permissions/delete/<str:pk>/', views.PermissionModuleSystemDeleteView.as_view(), name='permission_module_system_delete'),
    
    # URL para Asign Permissions a Usuarios
    path('auth/asign-permissions/', views.AsignPermissionsView.as_view(), name='asign_permissions'),
    path('auth/ajax/load-modules/', views.LoadModulesView.as_view(), name='ajax_load_modules'),
    path('auth/ajax/load-permissions/', views.LoadPermissionsView.as_view(), name='ajax_load_permissions'),
    path('auth/ajax/load-user-permissions/', views.LoadUserPermissionsView.as_view(), name='ajax_load_user_permissions'),
    path('auth/ajax/assign-permissions/', views.AssignPermissionsAjaxView.as_view(), name='ajax_assign_permissions'),
    
    # URL para LoginUser
    
    path('auth/users/', views.LoginUserListView.as_view(), name='loginuser_list'),
    path('auth/users/create/', views.LoginUserCreateView.as_view(), name='loginuser_create'),
    path('auth/users/update/<str:user_id>/', views.LoginUserUpdateView.as_view(), name='loginuser_update'),
    path('auth/users/delete/<str:user_id>/', views.LoginUserDeleteView.as_view(), name='loginuser_delete'),
    
    # URL para LoginUser Login
    
    path('auth/login/', views.UserLoginView.as_view(), name='login'),
    path('auth/logout/', views.UserLogoutView.as_view(), name='logout'),
    
    # MAIN URL
    path('auth/', views.MainManageAuthView.as_view(), name='main_manage_auth'),
]

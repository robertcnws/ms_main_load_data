# tu_app/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404
from django.views import View
from .models import (
                        System,
                        ModuleSystem,
                        PermissionModuleSystem,
                        LoginUser
                    )
from .forms import (
                        SystemForm,
                        ModuleSystemForm,
                        PermissionModuleSystemForm,
                        AsignPermissionsForm
                    )

# MAIN VIEW

class MainManageAuthView(View):
    def get(self, request):
        return render(request, 'main_manage_auth.html')

# SYSTEMS VIEWS

class SystemListView(View):
    def get(self, request):
        systems = System.objects.all()
        return render(request, 'system_list.html', {'systems': systems})

class SystemCreateView(View):
    def get(self, request):
        form = SystemForm()
        return render(request, 'system_form.html', {'form': form})
    
    def post(self, request):
        form = SystemForm(request.POST)
        if form.is_valid():
            System(**form.cleaned_data).save()
            return redirect('system_list')
        return render(request, 'system_form.html', {'form': form})

class SystemUpdateView(View):
    def get(self, request, pk):
        system = System.objects(id=pk).first()
        if not system:
            raise Http404("System not found.")
        form = SystemForm(initial={
            'name': system.name,
            'description': system.description,
        })
        return render(request, 'system_form.html', {'form': form, 'system': system})
    
    def post(self, request, pk):
        system = System.objects(id=pk).first()
        if not system:
            raise Http404("System not found.")
        form = SystemForm(request.POST)
        if form.is_valid():
            system.name = form.cleaned_data['name']
            system.description = form.cleaned_data['description']
            system.save()
            return redirect('system_list')
        return render(request, 'system_form.html', {'form': form, 'system': system})

class SystemDeleteView(View):
    def get(self, request, pk):
        system = System.objects(id=pk).first()
        if not system:
            raise Http404("System not found.")
        return render(request, 'system_confirm_delete.html', {'system': system})
    
    def post(self, request, pk):
        system = System.objects(id=pk).first()
        if not system:
            raise Http404("System not found.")
        system.delete()
        return redirect('system_list')


# MODULES VIEWS

class ModuleSystemListView(View):
    def get(self, request):
        modules = ModuleSystem.objects.all()
        return render(request, 'module_system_list.html', {'modules': modules})

class ModuleSystemCreateView(View):
    def get(self, request):
        form = ModuleSystemForm()
        return render(request, 'module_system_form.html', {'form': form})
    
    def post(self, request):
        form = ModuleSystemForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            description = form.cleaned_data['description']
            system_id = form.cleaned_data['system']
            
            system = System.objects(id=system_id).first()
            if not system:
                form.add_error('system', 'Selected system does not exist.')
                return render(request, 'module_system_form.html', {'form': form})
            
            module_system = ModuleSystem(
                name=name,
                description=description,
                system=system
            )
            module_system.save()
            return redirect('module_system_list') 
        return render(request, 'module_system_form.html', {'form': form})

class ModuleSystemUpdateView(View):
    def get(self, request, pk):
        module = ModuleSystem.objects(id=pk).first()
        if not module:
            raise Http404("Module not found.")
        form = ModuleSystemForm(initial={
            'name': module.name,
            'description': module.description,
            'system': module.system,
        })
        return render(request, 'module_system_form.html', {'form': form, 'module': module})
    
    def post(self, request, pk):
        module = ModuleSystem.objects(id=pk).first()
        if not module:
            raise Http404("Module not found.")
        form = ModuleSystemForm(request.POST)
        if form.is_valid():
            module.name = form.cleaned_data['name']
            module.description = form.cleaned_data['description']
            system_id = form.cleaned_data['system']
            system = System.objects(id=system_id).first()
            if not system:
                form.add_error('system', 'System not found.')
                return render(request, 'module_system_form.html', {'form': form})
            module.system = system
            module.save()
            return redirect('module_system_list')
        return render(request, 'module_system_form.html', {'form': form, 'module': module})

class ModuleSystemDeleteView(View):
    def get(self, request, pk):
        module = ModuleSystem.objects(id=pk).first()
        if not module:
            raise Http404("Module not found.")
        return render(request, 'module_system_confirm_delete.html', {'module': module})
    
    def post(self, request, pk):
        module = ModuleSystem.objects(id=pk).first()
        if not module:
            raise Http404("Module not found.")
        module.delete()
        return redirect('module_system_list')
    
    
# PERMISSIONS VIEWS

class PermissionModuleSystemListView(View):
    def get(self, request):
        permissions = PermissionModuleSystem.objects.all()
        return render(request, 'permission_module_system_list.html', {'permissions': permissions})

class PermissionModuleSystemCreateView(View):
    def get(self, request):
        form = PermissionModuleSystemForm()
        return render(request, 'permission_module_system_form.html', {'form': form})
    
    def post(self, request):
        form = PermissionModuleSystemForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            description = form.cleaned_data['description']
            module_system_id = form.cleaned_data['module_system']
            module_system = ModuleSystem.objects(id=module_system_id).first()
            if not module_system:
                form.add_error('module_system', 'Module System not found.')
                return render(request, 'permission_module_system_form.html', {'form': form})
            permission = PermissionModuleSystem(
                name=name,
                description=description,
                module_system=module_system
            )
            permission.save()
            return redirect('permission_module_system_list')
        return render(request, 'permission_module_system_form.html', {'form': form})

class PermissionModuleSystemUpdateView(View):
    def get(self, request, pk):
        permission = PermissionModuleSystem.objects(id=pk).first()
        if not permission:
            raise Http404("Permission not found.")
        form = PermissionModuleSystemForm(initial={
            'name': permission.name,
            'description': permission.description,
            'module_system': str(permission.module_system.id),
        })
        return render(request, 'permission_module_system_form.html', {'form': form, 'permission': permission})
    
    def post(self, request, pk):
        permission = PermissionModuleSystem.objects(id=pk).first()
        if not permission:
            raise Http404("Permission not found.")
        form = PermissionModuleSystemForm(request.POST)
        if form.is_valid():
            permission.name = form.cleaned_data['name']
            permission.description = form.cleaned_data['description']
            module_system_id = form.cleaned_data['module_system']
            module_system = ModuleSystem.objects(id=module_system_id).first()
            if not module_system:
                form.add_error('module_system', 'Module System not found.')
                return render(request, 'permission_module_system_form.html', {'form': form, 'permission': permission})
            permission.module_system = module_system
            permission.save()
            return redirect('permission_module_system_list')
        return render(request, 'permission_module_system_form.html', {'form': form, 'permission': permission})

class PermissionModuleSystemDeleteView(View):
    def get(self, request, pk):
        permission = PermissionModuleSystem.objects(id=pk).first()
        if not permission:
            raise Http404("Permission not found.")
        return render(request, 'permission_module_system_confirm_delete.html', {'permission': permission})
    
    def post(self, request, pk):
        permission = PermissionModuleSystem.objects(id=pk).first()
        if not permission:
            raise Http404("Permission not found.")
        permission.delete()
        return redirect('permission_module_system_list')


# ASIGN PERMISSIONS VIEWS

class AsignPermissionsView(View):
    def get(self, request):
        form = AsignPermissionsForm()
        return render(request, 'asign_permissions.html', {'form': form})
    
    def post(self, request):
        form = AsignPermissionsForm(request.POST)
        if form.is_valid():
            user_id = form.cleaned_data['user']
            permission_ids = form.cleaned_data['permissions']
            
            user = LoginUser.objects(id=user_id).first()
            if not user:
                form.add_error('user', 'Usuario seleccionado no existe.')
                return render(request, 'asign_permissions.html', {'form': form})
            
            permissions = PermissionModuleSystem.objects(id__in=permission_ids)
            
            user.permissions = list(permissions)  
            user.save()

            return redirect('main_manage_auth') 
        return render(request, 'asign_permissions.html', {'form': form})


# tu_app/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate, BACKEND_SESSION_KEY
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
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
                        AsignPermissionsForm,
                        LoginUserForm,
                        LoginForm
                    )
from datetime import datetime
import uuid

# HEALTH CHECK VIEW

@csrf_exempt
def health_check(request):
    return JsonResponse({'status': 'ok'})

# MAIN VIEW

class MainManageAuthView(LoginRequiredMixin, View):
    login_url = 'login' 
    
    def get(self, request):
        return render(request, 'main_manage_auth.html')
    
# USER LOGIN VIEWS

class UserLoginView(View):
    form_class = LoginForm
    template_name = 'login.html'

    def get(self, request):
        form = self.form_class()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = self.form_class(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                # login(request, user)
                # request.session[SESSION_KEY] = str(user.pk)  
                print("USER ID:", user.id)          # Debe imprimir un ObjectId
                print("USER ID STR:", str(user.id))
                request.session['user_id'] = str(user.id)
                request.session[BACKEND_SESSION_KEY] = 'ms_app_manage_auth.backends.MongoDBBackend'
                request.session.set_expiry(0)
                request.session.modified = True
                messages.success(request, "Logged in successfully.")
                return redirect('main_manage_auth') 
            else:
                messages.error(request, "Invalid username or password.")
        return render(request, self.template_name, {'form': form})

@method_decorator(login_required(login_url='login'), name='dispatch')
class UserLogoutView(View):
    def get(self, request):
        logout(request)
        messages.success(request, "Logged out successfully.")
        return redirect('login')

# SYSTEMS VIEWS

@method_decorator(login_required(login_url='login'), name='dispatch')
class SystemListView(View):
    def get(self, request):
        systems = System.objects.all()
        sorted_systems = sorted(
                    systems,
                    key=lambda sys: (
                        sys.name.lower()
                    )
                )
        return render(request, 'system_list.html', {'systems': sorted_systems})

@method_decorator(login_required(login_url='login'), name='dispatch')
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

@method_decorator(login_required(login_url='login'), name='dispatch')
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

@method_decorator(login_required(login_url='login'), name='dispatch')
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
@method_decorator(login_required(login_url='login'), name='dispatch')
class ModuleSystemListView(View):
    def get(self, request):
        modules = ModuleSystem.objects.all()
        sorted_modules = sorted(
                    modules,
                    key=lambda mod: (
                        mod.system.name.lower(),
                        mod.name.lower()
                    )
                )
        return render(request, 'module_system_list.html', {'modules': sorted_modules})

@method_decorator(login_required(login_url='login'), name='dispatch')
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

@method_decorator(login_required(login_url='login'), name='dispatch')
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

@method_decorator(login_required(login_url='login'), name='dispatch')
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

@method_decorator(login_required(login_url='login'), name='dispatch')
class PermissionModuleSystemListView(View):
    def get(self, request):
        permissions = PermissionModuleSystem.objects.all()
        sorted_permissions = sorted(
                    permissions,
                    key=lambda perm: (
                        perm.module_system.system.name.lower(),
                        perm.module_system.name.lower(),
                        perm.name.lower()
                    )
                )
        return render(request, 'permission_module_system_list.html', {'permissions': sorted_permissions})

@method_decorator(login_required(login_url='login'), name='dispatch')
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

@method_decorator(login_required(login_url='login'), name='dispatch')
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

@method_decorator(login_required(login_url='login'), name='dispatch')
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

@method_decorator(login_required(login_url='login'), name='dispatch')
class AsignPermissionsView(View):
    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied
        form = AsignPermissionsForm()
        return render(request, 'asign_permissions.html', {'form': form})

@method_decorator(login_required(login_url='login'), name='dispatch')
class AssignPermissionsAjaxView(View):
    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied
        user_id = request.POST.get('user_id')
        permission_ids = request.POST.getlist('permissions')
        if not user_id or not permission_ids:
            return JsonResponse({'status': 'error'}, status=400)
        
        user = LoginUser.objects(id=user_id).first()
        if not user:
            return JsonResponse({'status': 'error'}, status=404)
        
        permissions = PermissionModuleSystem.objects(id__in=permission_ids)
        added = False
        for perm in permissions:
            if perm not in user.permissions:
                user.permissions.append(perm)
                added = True
        if added:
            user.save()
            return JsonResponse({'status': 'success'})
        return JsonResponse({'status': 'no_changes'})

@method_decorator(login_required(login_url='login'), name='dispatch')
class LoadModulesView(View):
    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied
        system_id = request.GET.get('system_id')
        if system_id:
            modules = ModuleSystem.objects(system=system_id)
            module_list = [{'id': str(module.id), 'name': module.name} for module in modules]
            return JsonResponse({'modules': module_list})
        return JsonResponse({'modules': []})

@method_decorator(login_required(login_url='login'), name='dispatch')
class LoadPermissionsView(View):
    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied
        module_id = request.GET.get('module_id')
        if module_id:
            permissions = PermissionModuleSystem.objects(module_system=module_id)
            permission_list = [{'id': str(perm.id), 'name': perm.name} for perm in permissions]
            return JsonResponse({'permissions': permission_list})
        return JsonResponse({'permissions': []})

@method_decorator(login_required(login_url='login'), name='dispatch')
class LoadUserPermissionsView(View):
    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied
        user_id = request.GET.get('user_id')
        if user_id:
            user = LoginUser.objects(id=user_id).first()
            if user:
                sorted_permissions = sorted(
                    user.permissions,
                    key=lambda perm: (
                        perm.module_system.system.name.lower(),
                        perm.module_system.name.lower(),
                        perm.name.lower()
                    )
                )
                permissions = [{
                    'name': perm.name,
                    'module': perm.module_system.name,
                    'system': perm.module_system.system.name,
                    'edit_url': f"/api/manage/auth/permissions/edit/{perm.id}/",
                    'delete_url': f"/api/manage/auth/permissions/delete/{perm.id}/"
                } for perm in sorted_permissions]
                return JsonResponse({'permissions': permissions})
        return JsonResponse({'permissions': []})
    

@method_decorator(login_required(login_url='login'), name='dispatch')    
class LoginUserListView(View):
    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied
        users = LoginUser.objects.all().order_by('username')
        return render(request, 'loginuser_list.html', {'users': users})

@method_decorator(login_required(login_url='login'), name='dispatch')
class LoginUserCreateView(View):
    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied
        form = LoginUserForm()
        return render(request, 'loginuser_form.html', {'form': form, 'is_create': True})

    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied
        form = LoginUserForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            user = LoginUser(
                username=data['username'],
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
                email=data.get('email', ''),
                is_staff=data.get('is_staff', False),
                is_active=data.get('is_active', True),
                phone_number=data.get('phone_number', ''),
                country=data.get('country', ''),
                state=data.get('state', ''),
                city=data.get('city', ''),
                address=data.get('address', ''),
                zip_code=data.get('zip_code', ''),
                gender=data.get('gender', ''),
                date_joined=datetime.now(),
                date_updated=datetime.now(),
                token=generate_token(),
            )
            user.set_password(data['password'])
            user.save()
            messages.success(request, "User created successfully.")
            return redirect('loginuser_list')
        return render(request, 'loginuser_form.html', {'form': form, 'is_create': True})

@method_decorator(login_required(login_url='login'), name='dispatch')
class LoginUserUpdateView(View):
    def get(self, request, user_id):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied
        user = LoginUser.objects(id=user_id).first()
        if not user:
            raise Http404("User not found.")
        initial_data = {
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'is_staff': user.is_staff,
            'is_active': user.is_active,
            'phone_number': user.phone_number,
            'country': user.country,
            'state': user.state,
            'city': user.city,
            'address': user.address,
            'zip_code': user.zip_code,
            'gender': user.gender,
            # 'password': user.password,  
        }
        form = LoginUserForm(initial=initial_data)
        return render(request, 'loginuser_form.html', {'form': form, 'is_create': False, 'user_id': user_id})

    def post(self, request, user_id):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied
        user = LoginUser.objects(id=user_id).first()
        if not user:
            raise Http404("User not found.")
        form = LoginUserForm(request.POST, initial={
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'is_staff': user.is_staff,
            'is_active': user.is_active,
            'phone_number': user.phone_number,
            'country': user.country,
            'state': user.state,
            'city': user.city,
            'address': user.address,
            'zip_code': user.zip_code,
            'gender': user.gender,
        })
        if form.is_valid():
            data = form.cleaned_data
            user.username = data['username']
            user.first_name = data.get('first_name', '')
            user.last_name = data.get('last_name', '')
            user.email = data.get('email', '')
            user.is_staff = data.get('is_staff', False)
            user.is_active = data.get('is_active', True)
            user.phone_number = data.get('phone_number', '')
            user.country = data.get('country', '')
            user.state = data.get('state', '')
            user.city = data.get('city', '')
            user.address = data.get('address', '')
            user.zip_code = data.get('zip_code', '')
            user.gender = data.get('gender', '')
            user.date_updated = datetime.now()
            if data['password']:
                user.set_password(data['password'])
            if not user.token:
                user.token = generate_token()
            user.save()
            messages.success(request, "User updated successfully.")
            return redirect('loginuser_list')
        return render(request, 'loginuser_form.html', {'form': form, 'is_create': False, 'user_id': user_id})

@method_decorator(login_required(login_url='login'), name='dispatch')
class LoginUserDeleteView(View):
    def get(self, request, user_id):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied
        user = LoginUser.objects(id=user_id).first()
        if not user:
            raise Http404("User not found.")
        return render(request, 'loginuser_confirm_delete.html', {'user': user})

    def post(self, request, user_id):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied
        user = LoginUser.objects(id=user_id).first()
        if not user:
            raise Http404("User not found.")
        user.delete()
        messages.success(request, "User deleted successfully.")
        return redirect('loginuser_list')
    

def generate_token():
        return str(uuid.uuid4())
# tu_app/forms.py

from django import forms
from .models import (
                        System, 
                        ModuleSystem, 
                        PermissionModuleSystem, 
                        LoginUser
                    )

class SystemForm(forms.Form):
    name = forms.CharField(max_length=150, required=True)
    description = forms.CharField(max_length=500, required=False, widget=forms.Textarea)

class ModuleSystemForm(forms.Form):
    name = forms.CharField(max_length=150, required=True)
    description = forms.CharField(max_length=500, required=False, widget=forms.Textarea)
    system = forms.ChoiceField(choices=[], required=True)

    def __init__(self, *args, **kwargs):
        super(ModuleSystemForm, self).__init__(*args, **kwargs)
        systems = System.objects.all()
        self.fields['system'].choices = [(str(system.id), system.name) for system in systems]

class PermissionModuleSystemForm(forms.Form):
    name = forms.CharField(max_length=150, required=True)
    description = forms.CharField(max_length=500, required=False, widget=forms.Textarea)
    module_system = forms.ChoiceField(choices=[], required=True)

    def __init__(self, *args, **kwargs):
        super(PermissionModuleSystemForm, self).__init__(*args, **kwargs)
        modules_systems = ModuleSystem.objects.all()
        self.fields['module_system'].choices = [
            (str(module.id), f'{module.name} (System: {module.system.name})') 
            for module in modules_systems
        ]

class AsignPermissionsForm(forms.Form):
    user = forms.ChoiceField(choices=[], required=True)
    permissions = forms.MultipleChoiceField(choices=[], required=True, widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        super(AsignPermissionsForm, self).__init__(*args, **kwargs)
        users = LoginUser.objects.all()
        self.fields['user'].choices = [(str(user.id), user.username) for user in users]
        permissions = PermissionModuleSystem.objects.all()
        self.fields['permissions'].choices = [(str(perm.id), f'{perm.name} (Module: {perm.module_system.name}, System: {perm.module_system.system.name})') for perm in permissions]

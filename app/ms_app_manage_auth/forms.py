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
    system = forms.ChoiceField(choices=[], required=True)
    module = forms.ChoiceField(choices=[], required=True)
    permissions = forms.MultipleChoiceField(choices=[], required=True, widget=forms.CheckboxSelectMultiple)
    select_all = forms.BooleanField(required=False, initial=False)

    def __init__(self, *args, **kwargs):
        super(AsignPermissionsForm, self).__init__(*args, **kwargs)
        users = LoginUser.objects.all()
        self.fields['user'].choices = [('', '-Select User-')] + [(str(user.id), user.username) for user in users]
        systems = System.objects.all()
        self.fields['system'].choices = [('', '-Select System-')] + [(str(system.id), system.name) for system in systems]
        self.fields['module'].choices = [('', '-Select Module-')]
        self.fields['permissions'].choices = []
        

class LoginUserForm(forms.Form):
    username = forms.CharField(max_length=150, required=True, label="Username")
    first_name = forms.CharField(max_length=30, required=False, label="First Name")
    last_name = forms.CharField(max_length=30, required=False, label="Last Name")
    email = forms.EmailField(max_length=254, required=False, label="Email")
    is_staff = forms.BooleanField(required=False, label="Is Staff")
    is_active = forms.BooleanField(required=False, initial=True, label="Is Active")
    date_joined = forms.DateTimeField(required=False, widget=forms.HiddenInput)
    phone_number = forms.CharField(max_length=50, required=False, label="Phone Number")
    country = forms.CharField(max_length=50, required=False, label="Country")
    state = forms.CharField(max_length=50, required=False, label="State")
    city = forms.CharField(max_length=50, required=False, label="City")
    address = forms.CharField(max_length=255, required=False, label="Address")
    zip_code = forms.CharField(max_length=50, required=False, label="Zip Code")
    gender = forms.ChoiceField(choices=[('', 'Select Gender'), ('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')], required=False, label="Gender")
    password = forms.CharField(widget=forms.PasswordInput, required=True, label="Password")

    def __init__(self, *args, **kwargs):
        super(LoginUserForm, self).__init__(*args, **kwargs)
        self.fields['password'].help_text = "Enter a secure password."

    def clean_username(self):
        username = self.cleaned_data['username']
        if self.initial.get('username') != username:
            if LoginUser.objects(username=username).first():
                raise forms.ValidationError("Username already exists.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and not forms.EmailField().clean(email):
            raise forms.ValidationError("Enter a valid email address.")
        return email
    
class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'})
    )
    password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'})
    )

# tu_app/models.py

import mongoengine
from mongoengine import (
                            Document, 
                            StringField, 
                            ReferenceField, 
                            ListField, 
                            BooleanField, 
                            DateTimeField, 
                            CASCADE
                        )
from django.contrib.auth.hashers import (
                                            make_password, 
                                            check_password
                                        )

class System(Document):
    name = StringField(max_length=150, unique=True, required=True)
    description = StringField(max_length=500, required=False)
    
    meta = {
        'collection': 'systems',
        'indexes': ['name'],
    }

    def __str__(self):
        return self.name
    

class ModuleSystem(Document):
    name = StringField(max_length=150, required=True)
    description = StringField(max_length=500, required=False)
    system = ReferenceField(System, reverse_delete_rule=CASCADE, required=True)
    
    meta = {
        'collection': 'modules_systems',
        'indexes': ['name', 'system'],
    }

    def __str__(self):
        return f"{self.system.name} - {self.name}"


class PermissionModuleSystem(Document):
    name = StringField(max_length=150, required=True)
    description = StringField(max_length=500, required=False)
    module_system = ReferenceField(ModuleSystem, reverse_delete_rule=CASCADE, required=True)
    
    meta = {
        'collection': 'permissions_modules_systems',
        'indexes': ['name', 'module_system'],
    }

    def __str__(self):
        return f"{self.module_system} - {self.name}"
    
    
class LoginUser(Document):
    # Campos existentes...
    username = StringField(max_length=150, unique=True, required=True)
    first_name = StringField(max_length=30, required=False)
    last_name = StringField(max_length=30, required=False)
    email = StringField(max_length=254, required=False)
    is_staff = BooleanField(default=False)
    is_active = BooleanField(default=True)
    date_joined = DateTimeField(default=mongoengine.fields.DateTimeField().default)
    phone_number = StringField(max_length=50, required=False)
    country = StringField(max_length=50, required=False)
    state = StringField(max_length=50, required=False)
    city = StringField(max_length=50, required=False)
    address = StringField(max_length=255, required=False)
    zip_code = StringField(max_length=50, required=False)
    gender = StringField(max_length=50, required=False)
    password = StringField(required=True)
    
    # Nueva relación para permisos
    permissions = ListField(ReferenceField(PermissionModuleSystem), default=[])
    
    meta = {
        'collection': 'login_users',
        'indexes': ['username', 'email'],
    }
    
    def set_password(self, raw_password):
        self.password = make_password(raw_password)
    
    def check_password(self, raw_password):
        return check_password(raw_password, self.password)
    
    def has_permission(self, perm):
        return perm in self.permissions

    def has_module_permissions(self, app_label):
        # Implementa la lógica según cómo defines tus módulos y permisos
        for perm in self.permissions:
            if perm.startswith(app_label + "."):
                return True
        return False
    
    def get_permissions(self):
        """
        Retorna una lista de nombres de permisos asignados al usuario.
        """
        return [perm.name for perm in self.permissions]



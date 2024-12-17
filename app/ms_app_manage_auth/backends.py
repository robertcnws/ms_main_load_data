# tu_app/backends.py

from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import AnonymousUser
from .models import LoginUser

class MongoEngineBackend(BaseBackend):
    """
    Autenticación personalizada usando MongoEngine.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = LoginUser.objects.get(username=username)
            if user.check_password(password):
                return user
        except LoginUser.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return LoginUser.objects.get(id=user_id)
        except LoginUser.DoesNotExist:
            return None

    def has_permission(self, user_obj, perm, obj=None):
        return user_obj.has_permission(perm)

    def has_module_permissions(self, user_obj, app_label):
        return user_obj.has_module_permissions(app_label)

    @property
    def is_authenticated(self):
        return True

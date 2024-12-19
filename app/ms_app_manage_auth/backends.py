# backends.py
from django.contrib.auth.backends import BaseBackend
from .models import LoginUser

class MongoDBBackend(BaseBackend):
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        try:
            user = LoginUser.objects(username=username).first()
        except LoginUser.DoesNotExist:
            return None

        if user and user.check_password(password):
            return user
        return None

    def get_user(self, user_id):
        try:
            user = LoginUser.objects(id=user_id).first()
            return user
        except:
            return None

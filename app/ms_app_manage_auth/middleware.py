from django.contrib.auth.models import AnonymousUser
from django.utils.deprecation import MiddlewareMixin
from ms_main_load_data.mongo_setup import connect_mongo
from .models import LoginUser
import mongoengine

class MongoAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_id = request.session.get('user_id', None)
        if user_id:
            user = LoginUser.objects(id=user_id).first()
            if user:
                request.user = user
            else:
                request.user = AnonymousUser()
        else:
            request.user = AnonymousUser()

        return self.get_response(request)
    
    
# ms_app_manage_auth/middleware.py


class MongoConnectionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if not mongoengine.connection.get_connection():
            connect_mongo()

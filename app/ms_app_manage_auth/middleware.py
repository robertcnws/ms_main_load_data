from django.contrib.auth.models import AnonymousUser
from .models import LoginUser

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
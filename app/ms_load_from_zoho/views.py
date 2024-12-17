from rest_framework_mongoengine.viewsets import ModelViewSet
from ms_app_manage_auth.models import LoginUser
from ms_app_manage_auth.serializers import LoginUserSerializer

class LoginUserViewSet(ModelViewSet):
    queryset = LoginUser.objects.all()
    serializer_class = LoginUserSerializer

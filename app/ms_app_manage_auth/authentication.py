# authentication.py

from rest_framework.authentication import BaseAuthentication
from rest_framework import exceptions
from .models import LoginUser                          
from django.utils.translation import gettext_lazy as _

class MongoTokenAuthentication(BaseAuthentication):
    """
    Autenticación personalizada utilizando un token almacenado en el documento LoginUser de MongoDB.
    """
    keyword = 'Token'

    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return None 

        parts = auth_header.split()

        if len(parts) != 2 or parts[0] != self.keyword:
            raise exceptions.AuthenticationFailed(_('Formato de encabezado de autenticación inválido.'))

        token = parts[1]

        try:
            user = LoginUser.objects.get(token=token)
        except LoginUser.DoesNotExist:
            raise exceptions.AuthenticationFailed(_('Token de autenticación inválido.'))

        if not user.is_active:
            raise exceptions.AuthenticationFailed(_('Usuario inactivo.'))
        
        return (user, token)

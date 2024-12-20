import json
from bson import json_util
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ms_app_manage_auth.authentication import MongoTokenAuthentication
from ms_load_from_zoho.models import ZohoInventoryItem


@api_view(['GET'])
@authentication_classes([MongoTokenAuthentication])
@permission_classes([IsAuthenticated])
def secure_endpoint(request):
    """
    Endpoint seguro que solo puede ser accedido por usuarios autenticados vía token.
    """
    data = {
        'message': 'Este es un endpoint seguro accesible solo para clientes autenticados.'
    }
    return Response(data, status=status.HTTP_200_OK)


@api_view(['GET'])
@authentication_classes([MongoTokenAuthentication])
@permission_classes([IsAuthenticated])
def items(request):
    items = ZohoInventoryItem.objects.all()
    items_json = json_util.dumps(items) 
    items_data = json.loads(items_json)  
    return Response(items_data, status=status.HTTP_200_OK)

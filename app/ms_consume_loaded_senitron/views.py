from bson import json_util
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from bson.objectid import ObjectId
from datetime import datetime as dt
from ms_app_manage_auth.authentication import MongoTokenAuthentication
from ms_load_from_senitron.models import (
                                        SenitronItemAsset,
                                        SenitronItemAssetLogs,
                                        SenitronStatus
                                     )
import logging


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class CustomPagination(PageNumberPagination):
    page_size_query_param = 'page_size'
    max_page_size = 1000

@api_view(['GET'])
@authentication_classes([MongoTokenAuthentication])
@permission_classes([IsAuthenticated])
def item_assets(request):
    
    data = request.query_params.dict()
    
    item_numbers = data.get('item_numbers', None)
    
    if item_numbers:
        item_numbers = item_numbers.split(',')
        queryset = SenitronItemAsset.objects(item_number__in=item_numbers)
    else:
        queryset = SenitronItemAsset.objects.all()
    
    paginator = CustomPagination()
    paginated_queryset = paginator.paginate_queryset(queryset, request)

    list = []
    for doc in paginated_queryset:
        doc_dict = doc.to_mongo().to_dict()
        if '_id' in doc_dict and isinstance(doc_dict['_id'], ObjectId):
            doc_dict['_id'] = str(doc_dict['_id'])
        if 'status' in doc_dict:
            if isinstance(doc_dict['status'], ObjectId):
                status_senitron = SenitronStatus.objects.get(id=doc_dict['status'])
                doc_dict['status'] = {
                    'name':status_senitron.name,
                    'senitron_id': status_senitron.senitron_id
                }
        list.append(doc_dict)
        
    logger.info(
        f'Senitron Item Assets read: {len(list)}, '
        f'paginated: {len(paginated_queryset)}, '
        f'Count: {paginator.page.paginator.count}, '
        f'Number: {paginator.page.number}, '
        f'Number of pages: {paginator.page.paginator.num_pages}'
    )
    
    return Response({
            'count': paginator.page.paginator.count if paginator.page else len(list),
            'next': paginator.get_next_link(),
            'previous': paginator.get_previous_link(),
            'results': list,
    }, status=status.HTTP_200_OK)
    
    
@api_view(['GET'])
@authentication_classes([MongoTokenAuthentication])
@permission_classes([IsAuthenticated])
def item_assets_logs(request):
    
    data = request.query_params.dict()
    
    item_numbers = data.get('item_numbers', None)
    
    if item_numbers:
        item_numbers = item_numbers.split(',')
        queryset = SenitronItemAssetLogs.objects(item_number__in=item_numbers)
    else:
        queryset = SenitronItemAssetLogs.objects.all()
    
    paginator = CustomPagination()
    paginated_queryset = paginator.paginate_queryset(queryset, request)

    list = []
    for doc in paginated_queryset:
        doc_dict = doc.to_mongo().to_dict()
        if '_id' in doc_dict and isinstance(doc_dict['_id'], ObjectId):
            doc_dict['_id'] = str(doc_dict['_id'])
        list.append(doc_dict)
        
    logger.info(
        f'Senitron Item Assets Logs read: {len(list)}, '
        f'paginated: {len(paginated_queryset)}, '
        f'Count: {paginator.page.paginator.count}, '
        f'Number: {paginator.page.number}, '
        f'Number of pages: {paginator.page.paginator.num_pages}'
    )
    
    return Response({
            'count': paginator.page.paginator.count if paginator.page else len(list),
            'next': paginator.get_next_link(),
            'previous': paginator.get_previous_link(),
            'results': list,
    }, status=status.HTTP_200_OK)

from bson import json_util
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from bson.objectid import ObjectId
from datetime import datetime as dt
from ms_app_manage_auth.authentication import MongoTokenAuthentication
from ms_load_from_zoho.models import (
                                        ZohoInventoryItem, 
                                        ZohoShipmentOrder,
                                        ZohoPackage,
                                        ZohoCustomer,
                                        ZohoFullInvoice,
                                        ZohoInventoryShipmentSalesOrder,
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
    queryset = ZohoInventoryItem.objects.all() or []
    paginator = CustomPagination()
    paginated_queryset = paginator.paginate_queryset(queryset, request)

    items_list = []
    for doc in paginated_queryset:
        doc_dict = doc.to_mongo().to_dict()
        if '_id' in doc_dict and isinstance(doc_dict['_id'], ObjectId):
            doc_dict['_id'] = str(doc_dict['_id'])
        items_list.append(doc_dict)
        
    logger.info(
        f'Items read: {len(items_list)}, '
        f'paginated: {len(paginated_queryset)}, '
        f'Count: {paginator.page.paginator.count}, '
        f'Number: {paginator.page.number}, '
        f'Number of pages: {paginator.page.paginator.num_pages}'
    )

    return Response({
        'count': paginator.page.paginator.count if paginator.page else len(items_list),
        'next': paginator.get_next_link(),
        'previous': paginator.get_previous_link(),
        'results': items_list,
    }, status=status.HTTP_200_OK)
    
    
@api_view(['GET'])
@authentication_classes([MongoTokenAuthentication])
@permission_classes([IsAuthenticated])
def customers(request):
    queryset = ZohoCustomer.objects.all() or []
    paginator = CustomPagination()
    paginated_queryset = paginator.paginate_queryset(queryset, request)

    list = []
    for doc in paginated_queryset:
        doc_dict = doc.to_mongo().to_dict()
        if '_id' in doc_dict and isinstance(doc_dict['_id'], ObjectId):
            doc_dict['_id'] = str(doc_dict['_id'])
        list.append(doc_dict)
        
    logger.info(
        f'Customers read: {len(list)}, '
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
def shipment_orders(request):
    
    data = request.query_params.dict()
    
    start_date = data.get('start_date', None)
    end_date = data.get('end_date', None)
    
    try:
        if start_date:
            start_date = dt.strptime(start_date, '%Y-%m-%d')
        if end_date:
            end_date = dt.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    except ValueError:
        logger.error('Invalid date format')
        return Response({'error': 'Invalid date format'}, status=status.HTTP_400_BAD_REQUEST)
    
    if start_date and end_date:
        if start_date > end_date:
            logger.error(f'Invalid date range: [{start_date} - {end_date}]')
            return Response({'error': 'Invalid date range'}, status=status.HTTP_400_BAD_REQUEST)
        queryset = ZohoShipmentOrder.objects(date__gte=start_date, date__lte=end_date)
    elif start_date and not end_date:
        queryset = ZohoShipmentOrder.objects(date__gte=start_date)
    elif end_date and not start_date:
        queryset = ZohoShipmentOrder.objects(date__lte=end_date)
    else:
        queryset = ZohoShipmentOrder.objects.all()
    
    paginator = CustomPagination()
    paginated_queryset = paginator.paginate_queryset(queryset, request)

    list = []
    for doc in paginated_queryset:
        doc_dict = doc.to_mongo().to_dict()
        if '_id' in doc_dict and isinstance(doc_dict['_id'], ObjectId):
            doc_dict['_id'] = str(doc_dict['_id'])
        list.append(doc_dict)
        
    logger.info(
        f'Shipment orders read: {len(list)}, '
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
def packages(request):
    
    data = request.query_params.dict()
    
    shipment_ids = data.get('shipment_ids', None)
    
    if shipment_ids:
        shipment_ids = shipment_ids.split(',')
        queryset = ZohoPackage.objects(shipment_id__in=shipment_ids)
    else:
        queryset = ZohoPackage.objects.all()
    
    paginator = CustomPagination()
    paginated_queryset = paginator.paginate_queryset(queryset, request)

    list = []
    for doc in paginated_queryset:
        doc_dict = doc.to_mongo().to_dict()
        if '_id' in doc_dict and isinstance(doc_dict['_id'], ObjectId):
            doc_dict['_id'] = str(doc_dict['_id'])
        list.append(doc_dict)
        
    logger.info(
        f'Packages read: {len(list)}, '
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
def invoices(request):
    
    data = request.query_params.dict()
    
    start_date = data.get('start_date', None)
    end_date = data.get('end_date', None)
    
    try:
        if start_date:
            start_date = dt.strptime(start_date, '%Y-%m-%d')
        if end_date:
            end_date = dt.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    except ValueError:
        logger.error('Invalid date format')
        return Response({'error': 'Invalid date format'}, status=status.HTTP_400_BAD_REQUEST)
    
    if start_date and end_date:
        if start_date > end_date:
            logger.error(f'Invalid date range: [{start_date} - {end_date}]')
            return Response({'error': 'Invalid date range'}, status=status.HTTP_400_BAD_REQUEST)
        queryset = ZohoFullInvoice.objects(date__gte=start_date, date__lte=end_date)
    elif start_date and not end_date:
        queryset = ZohoFullInvoice.objects(date__gte=start_date)
    elif end_date and not start_date:
        queryset = ZohoFullInvoice.objects(date__lte=end_date)
    else:
        queryset = ZohoFullInvoice.objects.all()
    
    paginator = CustomPagination()
    paginated_queryset = paginator.paginate_queryset(queryset, request)

    list = []
    for doc in paginated_queryset:
        doc_dict = doc.to_mongo().to_dict()
        if '_id' in doc_dict and isinstance(doc_dict['_id'], ObjectId):
            doc_dict['_id'] = str(doc_dict['_id'])
        list.append(doc_dict)
        
    logger.info(
        f'Invoices read: {len(list)}, '
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
def sales_orders(request):
    
    data = request.query_params.dict()
    
    start_date = data.get('start_date', None)
    end_date = data.get('end_date', None)
    installation_name = data.get('installation_name', None)
    
    try:
        if start_date:
            start_date = dt.strptime(start_date, '%Y-%m-%d')
        if end_date:
            end_date = dt.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    except ValueError:
        logger.error('Invalid date format')
        return Response({'error': 'Invalid date format'}, status=status.HTTP_400_BAD_REQUEST)
    
    if start_date and end_date:
        if start_date > end_date:
            logger.error(f'Invalid date range: [{start_date} - {end_date}]')
            return Response({'error': 'Invalid date range'}, status=status.HTTP_400_BAD_REQUEST)
        queryset = ZohoInventoryShipmentSalesOrder.objects(date__gte=start_date, date__lte=end_date)
    elif start_date and not end_date:
        queryset = ZohoInventoryShipmentSalesOrder.objects(date__gte=start_date)
    elif end_date and not start_date:
        queryset = ZohoInventoryShipmentSalesOrder.objects(date__lte=end_date)
    else:
        queryset = ZohoInventoryShipmentSalesOrder.objects.all()
    if installation_name:
        queryset = [doc for doc in queryset for item in doc.line_items if item.get('name') == installation_name]
    
    paginator = CustomPagination()
    paginated_queryset = paginator.paginate_queryset(queryset, request)

    list = []
    for doc in paginated_queryset:
        doc_dict = doc.to_mongo().to_dict()
        if '_id' in doc_dict and isinstance(doc_dict['_id'], ObjectId):
            doc_dict['_id'] = str(doc_dict['_id'])
        list.append(doc_dict)
        
    logger.info(
        f'Sales orders read: {len(list)}, '
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
def full_sales_orders(request):
    
    data = request.query_params.dict()
    
    start_date = data.get('start_date', None)
    end_date = data.get('end_date', None)
    installation_name = data.get('installation_name', None)
    
    try:
        if start_date:
            start_date = dt.strptime(start_date, '%Y-%m-%d')
        if end_date:
            end_date = dt.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    except ValueError:
        logger.error('Invalid date format')
        return Response({'error': 'Invalid date format'}, status=status.HTTP_400_BAD_REQUEST)
    
    if start_date and end_date:
        if start_date > end_date:
            logger.error(f'Invalid date range: [{start_date} - {end_date}]')
            return Response({'error': 'Invalid date range'}, status=status.HTTP_400_BAD_REQUEST)
        queryset = ZohoInventoryShipmentSalesOrder.objects(date__gte=start_date, date__lte=end_date)
    elif start_date and not end_date:
        queryset = ZohoInventoryShipmentSalesOrder.objects(date__gte=start_date)
    elif end_date and not start_date:
        queryset = ZohoInventoryShipmentSalesOrder.objects(date__lte=end_date)
    else:
        queryset = ZohoInventoryShipmentSalesOrder.objects.all()
    if installation_name:
        queryset = [doc for doc in queryset for item in doc.line_items if item.get('name') == installation_name]
    
    paginator = CustomPagination()
    paginated_queryset = paginator.paginate_queryset(queryset, request)

    list = []
    for doc in paginated_queryset:
        doc_dict = doc.to_mongo().to_dict()
        if '_id' in doc_dict and isinstance(doc_dict['_id'], ObjectId):
            doc_dict['_id'] = str(doc_dict['_id'])
        list.append(doc_dict)
        
    for doc in list:
        customer = ZohoCustomer.objects.get(contact_id=doc['customer_id'])
        customer_dict = customer.to_mongo().to_dict()
        if '_id' in customer_dict and isinstance(customer_dict['_id'], ObjectId):
            customer_dict['_id'] = str(customer_dict['_id'])
        doc['customer'] = customer_dict
        
    logger.info(
        f'Sales orders read: {len(list)}, '
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

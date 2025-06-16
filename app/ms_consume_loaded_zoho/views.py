from bson import json_util
from mongoengine import Q
from concurrent.futures import ThreadPoolExecutor, as_completed
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from bson.objectid import ObjectId
from datetime import datetime as dt
from ms_app_manage_auth.authentication import MongoTokenAuthentication
from django.conf import settings
from django.http import JsonResponse
from ms_load_from_zoho.models import AppConfig
from ms_load_from_zoho.models import (
                                        ZohoInventoryItem, 
                                        ZohoShipmentOrder,
                                        ZohoPackage,
                                        ZohoCustomer,
                                        ZohoFullInvoice,
                                        ZohoInventoryShipmentSalesOrder,
                                     )
from ms_load_from_zoho.views import (
                                        config_headers,
                                        refresh_zoho_access_token,
                                        fetch_sales_order_details
)

from .utils import (
                    transform_data_to_mongo,
                    merge_list
)

import logging
import requests

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
    params = request.query_params.dict()
    queryset = ZohoCustomer.objects.all() or []
    
    if params.get('first_name'):
        queryset = queryset.filter(first_name__icontains=params['first_name'])
    if params.get('last_name'):
        queryset = queryset.filter(last_name__icontains=params['last_name'])
    if params.get('phone') or params.get('mobile'):
        number = params['phone'] if params.get('phone') else params['mobile']
        queryset = queryset.filter(
            Q(phone__exists=True, phone__ne="", phone__icontains=number) |
            Q(mobile__exists=True, mobile__ne="", mobile__icontains=number)
        )
    if params.get('email'):
        queryset = queryset.filter(email__icontains=params['email'])
    if params.get('zoho_org_id'):
        queryset = queryset.filter(zoho_org_id=params['zoho_org_id'])
        
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
    
    sales_orders_ids = data.get('sales_orders_ids', None)
    not_sales_orders_ids = data.get('not_sales_orders_ids', None)
    
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
    if sales_orders_ids and not not_sales_orders_ids:
        sales_orders_ids = sales_orders_ids.split(',')
        queryset = [doc for doc in queryset if doc.salesorder_id in sales_orders_ids]
    if not_sales_orders_ids and not sales_orders_ids:
        not_sales_orders_ids = not_sales_orders_ids.split(',')
        queryset = [doc for doc in queryset if doc.salesorder_id not in not_sales_orders_ids]
    if installation_name:
        queryset = [doc for doc in queryset for item in doc.line_items if installation_name.lower() in item.get('name', '').lower()]
    
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
    sales_orders_ids = data.get('sales_orders_ids', None)
    not_sales_orders_ids = data.get('not_sales_orders_ids', None)
    
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
    if sales_orders_ids and not not_sales_orders_ids:
        sales_orders_ids = sales_orders_ids.split(',')
        queryset = [doc for doc in queryset if doc.salesorder_id in sales_orders_ids]
    if not_sales_orders_ids and not sales_orders_ids:
        not_sales_orders_ids = not_sales_orders_ids.split(',')
        queryset = [doc for doc in queryset if doc.salesorder_id not in not_sales_orders_ids]
    if installation_name:
        queryset = [doc for doc in queryset for item in doc.line_items if installation_name.lower() in item.get('name', '').lower()]
    
    paginator = CustomPagination()
    paginated_queryset = paginator.paginate_queryset(queryset, request)

    list = []
    for doc in paginated_queryset:
        doc_dict = doc.to_mongo().to_dict()
        if '_id' in doc_dict and isinstance(doc_dict['_id'], ObjectId):
            doc_dict['_id'] = str(doc_dict['_id'])
        list.append(doc_dict)
        
    for doc in list:
        customer = ZohoCustomer.objects(contact_id=doc['customer_id']).first()
        if customer:
            customer_dict = customer.to_mongo().to_dict()
            if '_id' in customer_dict and isinstance(customer_dict['_id'], ObjectId):
                customer_dict['_id'] = str(customer_dict['_id'])
            doc['customer'] = customer_dict
        else:
            doc['customer'] = {}
        
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
def delete_sales_orders(request):
    
    data = request.query_params.dict()
    
    sales_orders_ids = data.get('sales_orders_ids', None)
    
    if not sales_orders_ids:
        return Response({'error': 'Missing sales_orders_ids'}, status=status.HTTP_400_BAD_REQUEST)
    
    sales_orders_ids = sales_orders_ids.split(',')
    queryset = ZohoInventoryShipmentSalesOrder.objects(salesorder_id__in=sales_orders_ids)
    queryset.delete()
    
    return Response({'message': 'Sales orders deleted'}, status=status.HTTP_200_OK)


@api_view(['GET'])
@authentication_classes([MongoTokenAuthentication])
@permission_classes([IsAuthenticated])
def sales_orders_to_service(request):
    params = request.query_params.dict()
    is_recent = params.get('is_recent', 'false').lower() == 'true'
    salesorder_number = params.get('salesorder_number')

    sales_orders_in_zoho_nws = []
    sales_orders_in_zoho_nwshome = []
    
    if salesorder_number:
        sales_orders = list(ZohoInventoryShipmentSalesOrder.objects(salesorder_number=salesorder_number))
        sales_orders = [transform_data_to_mongo(so) for so in sales_orders]
        if not is_recent:
            sales_orders_in_zoho_nws = load_inventory_sales_orders_by(settings.ZOHO_ORG_ID, param=salesorder_number)
            sales_orders_in_zoho_nwshome = load_inventory_sales_orders_by(settings.ZOHO_ORG_ID_NWSHOME, param=salesorder_number)
    else:
        queryset = ZohoCustomer.objects.all() 
        if params.get('company_name'):
            value = params['company_name']
            queryset = queryset.filter(
                Q(first_name__exists=True, first_name__ne="", first_name__icontains=value) |
                Q(contact_name__exists=True, contact_name__ne="", contact_name__icontains=value) |
                Q(customer_name__exists=True, customer_name__ne="", customer_name__icontains=value) |
                Q(company_name__exists=True, company_name__ne="", company_name__icontains=value)
            )
        if params.get('first_name'):
            value = params['first_name']
            queryset = queryset.filter(
                Q(first_name__exists=True, first_name__ne="", first_name__icontains=value) |
                Q(contact_name__exists=True, contact_name__ne="", contact_name__icontains=value) |
                Q(customer_name__exists=True, customer_name__ne="", customer_name__icontains=value) |
                Q(company_name__exists=True, company_name__ne="", company_name__icontains=value)
            )
        if params.get('last_name'):
            value = params['last_name']
            queryset = queryset.filter(
                Q(last_name__exists=True, last_name__ne="", last_name__icontains=value) |
                Q(contact_name__exists=True, contact_name__ne="", contact_name__icontains=value) |
                Q(customer_name__exists=True, customer_name__ne="", customer_name__icontains=value) |
                Q(company_name__exists=True, company_name__ne="", company_name__icontains=value)
            )
        if params.get('phone'):
            value = params['phone']
            queryset = queryset.filter(
                Q(phone__exists=True, phone__ne="", phone__icontains=value) |
                Q(mobile__exists=True, mobile__ne="", mobile__icontains=value)
            )
        if params.get('email'):
            value = params['email']
            queryset = queryset.filter(email__exists=True, email__ne="", email__icontains=value)
            
        customers = list(queryset)
            
        def get_sales_orders_from_zoho(customer):
            if not customer:
                return
            local_sales_orders = ZohoInventoryShipmentSalesOrder.objects(customer_id=customer.contact_id)
            _ = [transform_data_to_mongo(so) for so in local_sales_orders]
            sales_orders_in_zoho_nws.extend(load_inventory_sales_orders_by(settings.ZOHO_ORG_ID, param=customer))
            sales_orders_in_zoho_nwshome.extend(load_inventory_sales_orders_by(settings.ZOHO_ORG_ID_NWSHOME, param=customer))
        
        if not is_recent:
            MAX_WORKERS = 10
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = [executor.submit(get_sales_orders_from_zoho, customer) for customer in customers]
                for future in as_completed(futures):
                    future.result() 
        
        sales_orders = []
        for customer in customers:
            local_orders = ZohoInventoryShipmentSalesOrder.objects(customer_id=customer.contact_id)
            sales_orders.extend([transform_data_to_mongo(so) for so in local_orders])
    
    if not is_recent:
        if sales_orders_in_zoho_nws:
            sales_orders.extend(sales_orders_in_zoho_nws)
        if sales_orders_in_zoho_nwshome:
            sales_orders.extend(sales_orders_in_zoho_nwshome)
        if sales_orders_in_zoho_nws or sales_orders_in_zoho_nwshome:
            sales_orders = merge_list(sales_orders)
    
    if salesorder_number:
        sales_orders = [so for so in sales_orders if so.get('salesorder_number') == salesorder_number]
    
    return Response({
        'count': len(sales_orders),
        'results': sales_orders,
    }, status=status.HTTP_200_OK)
    
    

@api_view(['GET'])
@authentication_classes([MongoTokenAuthentication])
@permission_classes([IsAuthenticated])
def refetch_salesorder(request, zoho_org_id, salesorder_number):
            
    sales_orders = load_inventory_sales_orders_by(zoho_org_id, param=salesorder_number)

    return Response({
        'count': len(sales_orders),
        'results': sales_orders,
    }, status=status.HTTP_200_OK)
    
    
@api_view(['GET'])
@authentication_classes([MongoTokenAuthentication])
@permission_classes([IsAuthenticated])
def invoices_to_rewards_points(request):
    params = request.query_params.dict()

    invoices_in_zoho_nws = []
        
    queryset = ZohoFullInvoice.objects.all() 
        
    if params.get('customer_name'):
        value = params['customer_name']
        queryset = queryset.filter(
            Q(customer_name__exists=True, customer_name__ne="", customer_name__icontains=value)
        )
        
    if params.get('first_name'):
        value = params['first_name']
        queryset = queryset.filter(
            Q(contact_persons_details__first_name__exists=True) &
            Q(contact_persons_details__first_name__ne="") &
            Q(contact_persons_details__first_name__icontains=value)
        )
        
    if params.get('last_name'):
        value = params['last_name']
        queryset = queryset.filter(
            Q(contact_persons_details__last_name__exists=True) &
            Q(contact_persons_details__last_name__ne="") &
            Q(contact_persons_details__last_name__icontains=value)
        )
    if params.get('phone'):
        value = params['phone']
        queryset = queryset.filter(
            Q(phone__exists=True, phone__ne="", phone__icontains=value) |
            Q(mobile__exists=True, mobile__ne="", mobile__icontains=value) | 
            Q(contact_persons_details__phone__exists=True, contact_persons_details__phone__ne="", contact_persons_details__phone__icontains=value) |
            Q(contact_persons_details__mobile__exists=True, contact_persons_details__mobile__ne="", contact_persons_details__mobile__icontains=value)
        )
        
    if params.get('email'):
        value = params['email']
        queryset = queryset.filter(
            Q(email__exists=True, phone__ne="", phone__icontains=value) |
            Q(contact_persons_details__email__exists=True, contact_persons_details__email__ne="", contact_persons_details__email__icontains=value)
        )
            
    invoices_in_zoho_nws = list(queryset)
    
    invoices_in_zoho_nws = [invoice for invoice in invoices_in_zoho_nws if invoice.zoho_org_id == settings.ZOHO_ORG_ID]
    
    return Response({
        'count': len(invoices_in_zoho_nws),
        'results': invoices_in_zoho_nws,
    }, status=status.HTTP_200_OK)
    

# EXTRAS

def load_inventory_sales_orders_by(zoho_org_id, param):
    MAX_WORKERS = 10
    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    try:
        headers = config_headers(zoho_org_id)
    except Exception as e:
        logger.error(f"Error connecting to Zoho API: {str(e)}")
        return JsonResponse({'error': f"Error connecting to Zoho API (Load Items): {str(e)}"}, status=500)
    
    params = {
        'organization_id': app_config.zoho_org_id,
        'per_page': 200,
        'page': 1,
    }
    
    if not isinstance(param, str):
        customer_id = param.contact_id
        params['customer_id'] = customer_id
    else:
        params['salesorder_number'] = param
    

    url = settings.ZOHO_INVENTORY_SALESORDERS_URL
    items_to_get = []
    session = requests.Session()

    while True:
        try:
            response = session.get(url, headers=headers, params=params)
            if response.status_code == 401:
                new_token = refresh_zoho_access_token(zoho_org_id)
                headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                response = session.get(url, headers=headers, params=params)
            response.raise_for_status()
            items = response.json()
            print('items', items)
            items_to_get.extend(items.get('salesorders', []))
            if not items.get('page_context', {}).get('has_more_page', False):
                break
            params['page'] += 1
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching sales orders: {e}")
            return JsonResponse({'error': 'Failed to fetch sales orders'}, status=500)
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_sales_order_details, item, session, headers, zoho_org_id) for item in items_to_get]
        full_items_to_get = [future.result() for future in as_completed(futures) if future.result()]
                
    
    return full_items_to_get
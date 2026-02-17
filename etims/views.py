from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone

from .models import (
    ETimsConfiguration,
    FiscalReceipt,
    FiscalReceiptItem,
    OfflineTransactionQueue,
    ETimsApiLog
)
from .serializers import (
    ETimsConfigurationSerializer,
    FiscalReceiptSerializer,
    FiscalReceiptCreateSerializer,
    OfflineTransactionQueueSerializer,
    ETimsApiLogSerializer
)
from .services.etims_service import (
    ETimsService,
    FiscalReceiptService,
    OfflineSyncService,
    ETimsApiError
)
from sales.models import Sale, Return


class ETimsConfigurationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing eTIMS Configuration
    """
    queryset = ETimsConfiguration.objects.all()
    serializer_class = ETimsConfigurationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return ETimsConfiguration.objects.all().order_by('-created_at')
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get the active eTIMS configuration"""
        config = ETimsConfiguration.objects.filter(is_active=True).first()
        if config:
            serializer = self.get_serializer(config)
            return Response(serializer.data)
        return Response(
            {'error': 'No active configuration found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    @action(detail=False, methods=['post'])
    def set_active(self, request):
        """Set a configuration as active"""
        config_id = request.data.get('id')
        try:
            # Deactivate all
            ETimsConfiguration.objects.update(is_active=False)
            # Activate selected
            config = ETimsConfiguration.objects.get(id=config_id)
            config.is_active = True
            config.save()
            return Response({'status': 'activated', 'config': config.name})
        except ETimsConfiguration.DoesNotExist:
            return Response(
                {'error': 'Configuration not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class FiscalReceiptViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing Fiscal Receipts
    """
    queryset = FiscalReceipt.objects.all()
    serializer_class = FiscalReceiptSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = FiscalReceipt.objects.select_related('sale', 'return_record').prefetch_related('items')
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # Filter by sale
        sale_id = self.request.query_params.get('sale_id')
        if sale_id:
            queryset = queryset.filter(sale_id=sale_id)
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        return queryset.order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def register(self, request, pk=None):
        """
        Register a fiscal receipt with KRA eTIMS
        """
        fiscal_receipt = self.get_object()
        
        try:
            etims_service = ETimsService()
            result = etims_service.register_fiscal_receipt(fiscal_receipt)
            
            return Response({
                'status': 'success',
                'message': 'Receipt registered successfully',
                'kra_serial': result.get('serial_number'),
                'data': FiscalReceiptSerializer(fiscal_receipt).data
            })
            
        except ETimsApiError as e:
            return Response(
                {
                    'status': 'error',
                    'message': str(e),
                    'error_details': e.response_data
                },
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'])
    def register_all_pending(self, request):
        """
        Register all pending fiscal receipts
        """
        results = FiscalReceiptService.register_pending_receipts()
        return Response(results)
    
    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        """
        Void a fiscal receipt
        """
        fiscal_receipt = self.get_object()
        void_reason = request.data.get('reason', 'Voided by operator')
        
        try:
            etims_service = ETimsService()
            result = etims_service.void_fiscal_receipt(fiscal_receipt, void_reason)
            
            return Response({
                'status': 'success',
                'message': 'Receipt voided successfully',
                'data': FiscalReceiptSerializer(fiscal_receipt).data
            })
            
        except ETimsApiError as e:
            return Response(
                {
                    'status': 'error',
                    'message': str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )


class OfflineTransactionQueueViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Offline Transaction Queue
    """
    queryset = OfflineTransactionQueue.objects.all()
    serializer_class = OfflineTransactionQueueSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = OfflineTransactionQueue.objects.all()
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        return queryset.order_by('created_at')
    
    @action(detail=False, methods=['post'])
    def sync(self, request):
        """
        Sync offline transactions
        """
        results = OfflineSyncService.process_offline_transactions()
        return Response(results)


class ETimsApiLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing eTIMS API Logs
    """
    queryset = ETimsApiLog.objects.all()
    serializer_class = ETimsApiLogSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = ETimsApiLog.objects.select_related('fiscal_receipt')
        
        # Filter by success/failure
        success_param = self.request.query_params.get('success')
        if success_param is not None:
            queryset = queryset.filter(success=success_param.lower() == 'true')
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        return queryset.order_by('-created_at')
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """
        Get recent API logs
        """
        limit = int(request.query_params.get('limit', 50))
        logs = ETimsApiLog.objects.select_related('fiscal_receipt').order_by('-created_at')[:limit]
        serializer = self.get_serializer(logs, many=True)
        return Response(serializer.data)


class ETimsStatusViewSet(viewsets.ViewSet):
    """
    ViewSet for checking eTIMS status
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def check(self, request):
        """
        Check eTIMS connection status
        """
        try:
            etims_service = ETimsService()
            status = etims_service.check_connection()
            return Response(status)
        except ValueError as e:
            return Response({
                'connected': False,
                'message': str(e)
            })
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get eTIMS summary statistics
        """
        # Get active config
        config = ETimsConfiguration.objects.filter(is_active=True).first()
        
        # Count receipts by status
        from django.db.models import Count
        status_counts = FiscalReceipt.objects.values('status').annotate(
            count=Count('id')
        )
        
        # Count pending offline transactions
        offline_pending = OfflineTransactionQueue.objects.filter(
            status='pending'
        ).count()
        
        return Response({
            'config_active': config is not None,
            'config_name': config.name if config else None,
            'environment': 'sandbox' if config and config.is_sandbox else 'production' if config else None,
            'receipts_by_status': {item['status']: item['count'] for item in status_counts},
            'offline_transactions_pending': offline_pending,
            'total_receipts': FiscalReceipt.objects.count()
        })

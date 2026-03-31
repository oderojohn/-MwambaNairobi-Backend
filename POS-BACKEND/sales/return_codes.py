"""
Return Code API Views
Handles generation and validation of return codes for refunds.
"""
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from django.db import transaction

from .models import ReturnCode, Return
from .serializers import ReturnCodeSerializer, ValidateReturnCodeSerializer


class ReturnCodeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing return codes.
    
    Endpoints:
    - POST /api/returns/return-codes/generate/ - Generate a return code for a return
    - POST /api/returns/return-codes/validate/ - Validate a return code
    - POST /api/returns/return-codes/use/ - Mark a return code as used
    - GET /api/returns/return-codes/ - List all return codes
    """
    queryset = ReturnCode.objects.all()
    serializer_class = ReturnCodeSerializer
    
    def get_queryset(self):
        """Filter return codes based on user role"""
        queryset = super().get_queryset()
        
        # Cashiers can only see codes from their returns
        if hasattr(self.request.user, 'userprofile'):
            user_profile = self.request.user.userprofile
            if user_profile.role == 'cashier':
                return queryset.filter(return_record__processed_by=user_profile)
        
        return queryset
    
    @action(detail=False, methods=['post'])
    def generate(self, request):
        """
        Generate a return code for a return record.
        
        Request body:
        {
            "return_record_id": 1,
            "refund_amount": 1500.00
        }
        
        Returns:
        {
            "code": "ABCD1234",
            "refund_amount": "1500.00",
            "original_receipt_number": "SALE-123",
            "status": "active"
        }
        """
        try:
            return_record_id = request.data.get('return_record_id')
            refund_amount = request.data.get('refund_amount')
            
            if not return_record_id:
                return Response(
                    {'error': 'Return record ID is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                return_record = Return.objects.get(id=return_record_id)
            except Return.DoesNotExist:
                return Response(
                    {'error': 'Return record not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            if not refund_amount:
                refund_amount = return_record.total_refund_amount
            
            # Generate the return code
            code = ReturnCode.generate_code(
                refund_amount=refund_amount,
                receipt_number=return_record.sale.receipt_number
            )
            
            # Create the return code record
            return_code = ReturnCode.objects.create(
                code=code,
                return_record=return_record,
                refund_amount=refund_amount,
                original_receipt_number=return_record.sale.receipt_number
            )
            
            return Response({
                'code': return_code.code,
                'refund_amount': str(return_code.refund_amount),
                'original_receipt_number': return_code.original_receipt_number,
                'status': return_code.status,
                'created_at': return_code.created_at.isoformat()
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'])
    def validate(self, request):
        """
        Validate a return code and return its details.
        
        Request body:
        {
            "code": "ABCD1234"
        }
        
        Returns:
        {
            "valid": true,
            "refund_amount": "1500.00",
            "original_receipt_number": "SALE-123",
            "status": "active"
        }
        """
        serializer = ValidateReturnCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        code = serializer.validated_data['code'].upper()
        expected_amount = serializer.validated_data.get('expected_amount')
        
        try:
            return_code = ReturnCode.objects.get(code=code)
        except ReturnCode.DoesNotExist:
            return Response({
                'valid': False,
                'error': 'Invalid return code'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if code is valid
        if return_code.status != 'active':
            return Response({
                'valid': False,
                'error': f'Return code has already been {return_code.status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate amount if provided
        if expected_amount is not None:
            tolerance = 0.01  # Allow small floating point differences
            if abs(float(return_code.refund_amount) - float(expected_amount)) > tolerance:
                return Response({
                    'valid': False,
                    'error': 'Return code amount does not match expected amount',
                    'code_amount': str(return_code.refund_amount),
                    'expected_amount': str(expected_amount)
                }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'valid': True,
            'code': return_code.code,
            'refund_amount': str(return_code.refund_amount),
            'original_receipt_number': return_code.original_receipt_number,
            'status': return_code.status,
            'return_receipt': return_code.return_record.receipt_number
        })
    
    @action(detail=False, methods=['post'])
    def use(self, request):
        """
        Mark a return code as used when applying it to a new sale.
        
        Request body:
        {
            "code": "ABCD1234",
            "sale_id": 123
        }
        
        Returns:
        {
            "success": true,
            "refund_amount": "1500.00"
        }
        """
        code = request.data.get('code', '').upper()
        sale_id = request.data.get('sale_id')
        
        if not code:
            return Response(
                {'error': 'Return code is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not sale_id:
            return Response(
                {'error': 'Sale ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            return_code = ReturnCode.objects.get(code=code)
        except ReturnCode.DoesNotExist:
            return Response(
                {'error': 'Invalid return code'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if return_code.status != 'active':
            return Response(
                {'error': f'Return code has already been {return_code.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from .models import Sale
            sale = Sale.objects.get(id=sale_id)
        except Sale.DoesNotExist:
            return Response(
                {'error': 'Sale not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Mark the code as used
        with transaction.atomic():
            return_code.status = 'used'
            return_code.used_at = timezone.now()
            return_code.used_in_sale = sale
            return_code.save()
        
        return Response({
            'success': True,
            'code': return_code.code,
            'refund_amount': str(return_code.refund_amount),
            'message': 'Return code applied successfully'
        })
    
    @action(detail=False, methods=['get'])
    def by_receipt(self, request):
        """
        Get all return codes for a specific receipt.
        
        Query params:
        - receipt_number: The original sale receipt number
        """
        receipt_number = request.query_params.get('receipt_number')
        
        if not receipt_number:
            return Response(
                {'error': 'Receipt number is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return_codes = ReturnCode.objects.filter(
            original_receipt_number__icontains=receipt_number
        )
        
        serializer = self.get_serializer(return_codes, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel an active return code.
        """
        return_code = self.get_object()
        
        if return_code.status != 'active':
            return Response(
                {'error': f'Cannot cancel return code with status: {return_code.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return_code.status = 'cancelled'
        return_code.save()
        
        serializer = self.get_serializer(return_code)
        return Response(serializer.data)

from rest_framework import serializers
from .models import Shift
from sales.serializers import SaleSerializer, ReturnSerializer
from django.db.models import Q

class ShiftSerializer(serializers.ModelSerializer):
    cashier_name = serializers.SerializerMethodField()
    cashier_role = serializers.SerializerMethodField()
    waiter_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    transaction_count = serializers.SerializerMethodField()
    expected_cash = serializers.SerializerMethodField()
    actual_cash = serializers.SerializerMethodField()
    total_returns = serializers.SerializerMethodField()
    return_count = serializers.SerializerMethodField()
    sales = SaleSerializer(source='sale_set', many=True, read_only=True)
    returns = serializers.SerializerMethodField()
    has_active_shift = serializers.SerializerMethodField()
    last_shift_info = serializers.SerializerMethodField()

    class Meta:
        model = Shift
        fields = [
            'id', 'cashier', 'start_time', 'end_time', 'opening_balance',
            'closing_balance', 'cash_sales', 'card_sales', 'mobile_sales',
            'total_sales', 'total_returns', 'return_count', 'net_sales',
            'status', 'discrepancy', 'approved_by',
            'cashier_name', 'cashier_role', 'waiter_name', 'approved_by_name', 'transaction_count', 'expected_cash', 'actual_cash', 'notes', 'sales', 'returns',
            'has_active_shift', 'last_shift_info'
        ]

    def get_has_active_shift(self, obj):
        """Check if this is an active shift"""
        return obj.status == 'open'

    def get_last_shift_info(self, obj):
        """Return last shift info when no active shift"""
        if obj.status != 'open':
            # This is the last closed shift - return its info
            discrepancy_value = float(obj.discrepancy) if obj.discrepancy is not None else 0
            return {
                'id': obj.id,
                'end_time': obj.end_time,
                'closing_balance': float(obj.closing_balance) if obj.closing_balance is not None else 0,
                'total_sales': float(obj.total_sales) if obj.total_sales is not None else 0,
                'discrepancy': discrepancy_value,
                'status': obj.status
            }
        return None

    def get_transaction_count(self, obj):
        try:
            return obj.sale_set.count()
        except:
            return 0

    def get_cashier_name(self, obj):
        try:
            return obj.cashier.user.username
        except:
            return None

    def get_cashier_role(self, obj):
        try:
            return obj.cashier.role
        except:
            return None

    def get_waiter_name(self, obj):
        try:
            return obj.cashier.user.username
        except:
            return None

    def get_approved_by_name(self, obj):
        try:
            return obj.approved_by.user.username if obj.approved_by else None
        except:
            return None

    def get_expected_cash(self, obj):
        return float(obj.opening_balance or 0) + float(obj.cash_sales or 0)

    def get_actual_cash(self, obj):
        return float(obj.closing_balance or 0)

    def get_discrepancy(self, obj):
        """Recalculate discrepancy to ensure accuracy
        Returns: actual - expected (opening + cash_sales - returns)
        Positive = overage, Negative = shortage
        """
        # Calculate returns from actual returns in this shift
        from sales.models import Return
        shift_returns = Return.objects.filter(
            shift=obj
        )
        total_returns = sum(float(r.total_refund_amount or 0) for r in shift_returns)
        
        expected = float(obj.opening_balance or 0) + float(obj.cash_sales or 0) - total_returns
        actual = float(obj.closing_balance or 0)
        return actual - expected

    def get_return_count(self, obj):
        """Get the count of returns processed in this shift"""
        from sales.models import Return
        # Filter by return's shift only (when return was processed, not when sale was made)
        return Return.objects.filter(
            shift=obj
        ).count()

    def get_total_returns(self, obj):
        """Get the total refund amount for returns processed in this shift"""
        from sales.models import Return
        from django.db.models import Sum
        # Filter by return's shift only (when return was processed, not when sale was made)
        result = Return.objects.filter(
            shift=obj
        ).aggregate(total=Sum('total_refund_amount'))
        return float(result['total'] or 0)

    def get_returns(self, obj):
        """Get all returns processed in this shift"""
        from sales.models import Return
        from django.db.models import Prefetch
        
        # Get returns that were processed in this shift only (not the sale's shift)
        returns = Return.objects.filter(
            shift=obj
        ).select_related(
            'sale', 'processed_by__user'
        ).prefetch_related('items__sale_item__product').order_by('-return_date')
        
        return ReturnSerializer(returns, many=True).data

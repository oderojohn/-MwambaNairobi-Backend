from rest_framework import serializers
from .models import ETimsConfiguration, FiscalReceipt, FiscalReceiptItem, OfflineTransactionQueue, ETimsApiLog


class ETimsConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ETimsConfiguration
        fields = [
            'id', 'name', 'tin', 'branch_id', 'device_serial',
            'api_key', 'api_secret', 'is_sandbox', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ('id', 'created_at', 'updated_at')


class FiscalReceiptItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalReceiptItem
        fields = [
            'id', 'product_code', 'product_name', 'hs_code',
            'quantity', 'unit_price', 'tax_rate', 'tax_amount',
            'discount_amount', 'line_total'
        ]


class FiscalReceiptSerializer(serializers.ModelSerializer):
    items = FiscalReceiptItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = FiscalReceipt
        fields = [
            'id', 'receipt_number', 'kra_serial', 'sale', 'return_record',
            'receipt_datetime', 'total_amount', 'tax_amount', 'discount_amount',
            'customer_tin', 'customer_name', 'transaction_type', 'status',
            'raw_response', 'error_message', 'items', 'created_at', 'sent_at'
        ]
        read_only_fields = ('id', 'kra_serial', 'receipt_datetime', 'status')


class FiscalReceiptCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating fiscal receipts"""
    items = FiscalReceiptItemSerializer(many=True, required=False)
    
    class Meta:
        model = FiscalReceipt
        fields = [
            'sale', 'return_record', 'receipt_number', 'total_amount',
            'tax_amount', 'discount_amount', 'customer_tin', 'customer_name',
            'transaction_type', 'items'
        ]
    
    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        fiscal_receipt = FiscalReceipt.objects.create(**validated_data)
        
        for item_data in items_data:
            FiscalReceiptItem.objects.create(receipt=fiscal_receipt, **item_data)
        
        return fiscal_receipt


class OfflineTransactionQueueSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfflineTransactionQueue
        fields = [
            'id', 'transaction_type', 'reference_id', 'payload',
            'status', 'retry_count', 'last_error', 'created_at', 'processed_at'
        ]
        read_only_fields = ('id', 'status', 'retry_count', 'created_at', 'processed_at')


class ETimsApiLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ETimsApiLog
        fields = [
            'id', 'endpoint', 'method', 'request_payload', 'response_payload',
            'status_code', 'success', 'error_details', 'duration_ms',
            'fiscal_receipt', 'created_at'
        ]
        read_only_fields = ('id', 'created_at')


# KRA eTIMS API Payload Serializers
class KRAFiscalPayloadSerializer(serializers.Serializer):
    """Serializer for KRA eTIMS fiscal receipt payload"""
    tin = serializers.CharField(max_length=20)
    branch_id = serializers.CharField(max_length=10)
    device_serial = serializers.CharField(max_length=50)
    receipt_number = serializers.CharField(max_length=50)
    receipt_datetime = serializers.DateTimeField()
    transaction_type = serializers.ChoiceField(choices=['sale', 'return', 'void'])
    
    # Customer
    customer_tin = serializers.CharField(max_length=20, required=False, allow_null=True)
    customer_name = serializers.CharField(max_length=200, required=False, allow_null=True)
    
    # Totals
    total_amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    tax_amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    discount_amount = serializers.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Items
    items = serializers.ListField(child=serializers.DictField())


class KRAApiResponseSerializer(serializers.Serializer):
    """Serializer for KRA API response"""
    success = serializers.BooleanField()
    serial_number = serializers.CharField(max_length=50, required=False, allow_null=True)
    receipt_number = serializers.CharField(max_length=50, required=False, allow_null=True)
    message = serializers.CharField(required=False, allow_null=True)
    error = serializers.CharField(required=False, allow_null=True)
    timestamp = serializers.DateTimeField(required=False, allow_null=True)

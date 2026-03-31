from django.db import models
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
import json
import uuid


class ETimsConfiguration(models.Model):
    """
    KRA eTIMS Configuration - Stores TIN, Branch ID, Device Serial, and API credentials
    """
    name = models.CharField(max_length=100, default='Primary POS')
    tin = models.CharField(max_length=20, help_text='Tax Identification Number')
    branch_id = models.CharField(max_length=10, help_text='Branch ID (MRC)')
    device_serial = models.CharField(max_length=50, help_text='Device Serial Number (S/N)')
    
    # API Credentials
    api_key = models.CharField(max_length=256, help_text='eTIMS API Key')
    api_secret = models.CharField(max_length=256, help_text='eTIMS API Secret')
    
    # Environment
    is_sandbox = models.BooleanField(default=True, help_text='Use sandbox/test environment')
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'eTIMS Configuration'
        verbose_name_plural = 'eTIMS Configurations'
    
    def __str__(self):
        return f"{self.name} - {self.tin}"


class FiscalReceipt(models.Model):
    """
    Fiscal Receipt - Stores KRA-compliant fiscal receipt data
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent to KRA'),
        ('signed', 'KRA Signed'),
        ('failed', 'Failed'),
        ('voided', 'Voided'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Link to original sale
    sale = models.ForeignKey('sales.Sale', on_delete=models.CASCADE, null=True, blank=True, related_name='fiscal_receipts')
    return_record = models.ForeignKey('sales.Return', on_delete=models.CASCADE, null=True, blank=True, related_name='fiscal_receipts')
    
    # Receipt Identification
    receipt_number = models.CharField(max_length=50, unique=True)
    kra_serial = models.CharField(max_length=50, blank=True, null=True, help_text='KRA assigned serial number')
    
    # eTIMS Fields
    receipt_datetime = models.DateTimeField(blank=True, null=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Customer Info (for KRA)
    customer_tin = models.CharField(max_length=20, blank=True, null=True, help_text='Customer TIN')
    customer_name = models.CharField(max_length=200, blank=True, null=True)
    
    # Transaction Type
    transaction_type = models.CharField(max_length=20, choices=[
        ('sale', 'Sale'),
        ('return', 'Return/Refund'),
        ('void', 'Void'),
    ])
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # KRA Response
    raw_response = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    error_message = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        verbose_name = 'Fiscal Receipt'
        verbose_name_plural = 'Fiscal Receipts'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.receipt_number} - {self.status}"


class FiscalReceiptItem(models.Model):
    """
    Line items for Fiscal Receipt - KRA compliant item details
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    receipt = models.ForeignKey(FiscalReceipt, on_delete=models.CASCADE, related_name='items')
    
    # Product Info
    product_code = models.CharField(max_length=50, help_text='Product Code (SKU or Barcode)')
    product_name = models.CharField(max_length=200)
    hs_code = models.CharField(max_length=20, blank=True, null=True, help_text='HS Code for customs')
    
    # Quantities
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Tax Info
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=16.0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Discounts
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Line Total
    line_total = models.DecimalField(max_digits=15, decimal_places=2)
    
    class Meta:
        verbose_name = 'Fiscal Receipt Item'
        verbose_name_plural = 'Fiscal Receipt Items'
    
    def __str__(self):
        return f"{self.product_name} - {self.quantity} x {self.unit_price}"


class OfflineTransactionQueue(models.Model):
    """
    Queue for offline transactions - syncs when connection restored
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    TRANSACTION_TYPES = [
        ('sale', 'Sale'),
        ('return', 'Return'),
        ('void', 'Void'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    reference_id = models.CharField(max_length=100, help_text='Reference to original record')
    payload = models.JSONField(encoder=DjangoJSONEncoder)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    last_error = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        verbose_name = 'Offline Transaction Queue'
        verbose_name_plural = 'Offline Transaction Queues'
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.transaction_type} - {self.reference_id} ({self.status})"


class ETimsApiLog(models.Model):
    """
    Complete audit trail for all KRA API interactions
    """
    METHOD_CHOICES = [
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('DELETE', 'DELETE'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    endpoint = models.CharField(max_length=500)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES)
    
    request_payload = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    response_payload = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    
    status_code = models.IntegerField(null=True, blank=True)
    success = models.BooleanField(default=False)
    error_details = models.TextField(blank=True, null=True)
    
    # Fiscal Receipt link
    fiscal_receipt = models.ForeignKey(FiscalReceipt, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Timing
    duration_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'eTIMS API Log'
        verbose_name_plural = 'eTIMS API Logs'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.method} {self.endpoint} - {self.success}"

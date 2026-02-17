from django.contrib import admin
from .models import (
    ETimsConfiguration,
    FiscalReceipt,
    FiscalReceiptItem,
    OfflineTransactionQueue,
    ETimsApiLog
)


@admin.register(ETimsConfiguration)
class ETimsConfigurationAdmin(admin.ModelAdmin):
    list_display = ('name', 'tin', 'branch_id', 'device_serial', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'tin')


@admin.register(FiscalReceipt)
class FiscalReceiptAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'kra_serial', 'sale', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('receipt_number', 'kra_serial', 'sale__receipt_number')
    readonly_fields = ('kra_serial', 'receipt_datetime', 'raw_response')


@admin.register(OfflineTransactionQueue)
class OfflineTransactionQueueAdmin(admin.ModelAdmin):
    list_display = ('transaction_type', 'reference_id', 'status', 'retry_count', 'created_at')
    list_filter = ('status', 'transaction_type')
    search_fields = ('reference_id',)


@admin.register(ETimsApiLog)
class ETimsApiLogAdmin(admin.ModelAdmin):
    list_display = ('endpoint', 'method', 'status_code', 'success', 'created_at')
    list_filter = ('success', 'endpoint')
    search_fields = ('request_payload', 'response_payload')
    readonly_fields = ('request_payload', 'response_payload', 'error_details')

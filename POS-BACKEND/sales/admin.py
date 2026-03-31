from django.contrib import admin
from .models import Cart, CartItem, Sale, SaleItem, Return, ReturnItem, Invoice, InvoiceItem, ReceiptCounter

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'status', 'created_at', 'cashier']
    list_filter = ['status', 'created_at']
    search_fields = ['customer__name']

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['cart', 'product', 'quantity', 'unit_price', 'discount']
    search_fields = ['product__name']

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['receipt_number', 'cart', 'total_amount', 'final_amount', 'sale_date', 'shift']
    list_filter = ['sale_date', 'shift']
    search_fields = ['receipt_number']

@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ['sale', 'product', 'quantity', 'unit_price', 'discount']
    search_fields = ['product__name']

class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0
    readonly_fields = ['sale_item', 'quantity', 'refund_amount', 'reason']
    can_delete = False

@admin.register(Return)
class ReturnAdmin(admin.ModelAdmin):
    list_display = ['id', 'receipt_number', 'sale', 'shift', 'return_type', 'total_refund_amount', 'return_date', 'processed_by']
    list_filter = ['return_type', 'return_date', 'shift']
    search_fields = ['receipt_number', 'sale__receipt_number', 'reason']
    raw_id_fields = ['sale', 'shift', 'processed_by']
    inlines = [ReturnItemInline]

@admin.register(ReceiptCounter)
class ReceiptCounterAdmin(admin.ModelAdmin):
    list_display = ['receipt_type', 'last_number', 'date']
    list_filter = ['date']

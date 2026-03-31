from django.contrib import admin
from .models import Shift
from sales.models import Return

class ReturnInline(admin.TabularInline):
    model = Return
    extra = 0
    readonly_fields = ['receipt_number', 'sale', 'return_type', 'total_refund_amount', 'return_date', 'processed_by']
    can_delete = False
    show_change_link = True

@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ['id', 'cashier', 'start_time', 'end_time', 'status', 'opening_balance', 'closing_balance', 'total_sales', 'total_returns', 'discrepancy']
    list_filter = ['status', 'start_time']
    search_fields = ['cashier__user__username']
    inlines = [ReturnInline]

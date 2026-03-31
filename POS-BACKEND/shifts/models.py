from django.db import models

# Create your models here.

class Shift(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
    ]
    
    cashier = models.ForeignKey('users.UserProfile', on_delete=models.CASCADE)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    opening_balance = models.DecimalField(max_digits=10, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cash_sales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    card_sales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    mobile_sales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_sales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Return fields
    total_returns = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    return_count = models.IntegerField(default=0)
    net_sales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')
    discrepancy = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    approved_by = models.ForeignKey('users.UserProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_shifts')
    notes = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Shift {self.id} - {self.cashier.user.username} - {self.status}"
    
    def update_return_totals(self):
        """Calculate and update return totals from returns processed during this shift"""
        from django.db.models import Sum, Count
        from sales.models import Return
        
        # Get returns processed during this shift
        returns_data = Return.objects.filter(
            shift_id=self.id
        ).aggregate(
            total=Sum('total_refund_amount'),
            count=Count('id')
        )
        
        self.total_returns = returns_data['total'] or 0
        self.return_count = returns_data['count'] or 0
        self.net_sales = self.total_sales - self.total_returns
        
        self.save(update_fields=['total_returns', 'return_count', 'net_sales'])
        return self
    
    def refresh_totals(self):
        """Refresh all calculated totals for the shift"""
        from django.db.models import Sum, Count, Q
        from sales.models import Sale, Return
        
        # Calculate from sales
        sales_qs = self.sale_set.filter(voided=False)
        
        sales_data = sales_qs.aggregate(
            cash=Sum('cash_received', filter=Q(payment_method='cash')),
            card=Sum('cash_received', filter=Q(payment_method='card')),
            mobile=Sum('cash_received', filter=Q(payment_method='mpesa')),
            total=Sum('final_amount'),
            count=Count('id')
        )
        
        self.cash_sales = sales_data['cash'] or 0
        self.card_sales = sales_data['card'] or 0
        self.mobile_sales = sales_data['mobile'] or 0
        self.total_sales = sales_data['total'] or 0
        self.transaction_count = sales_data['count'] or 0
        
        # Calculate returns - filter by return's shift (when return was processed)
        returns_data = Return.objects.filter(
            shift_id=self.id
        ).aggregate(
            total=Sum('total_refund_amount'),
            count=Count('id')
        )
        
        self.total_returns = returns_data['total'] or 0
        self.return_count = returns_data['count'] or 0
        self.net_sales = self.total_sales - self.total_returns
        
        self.save(update_fields=['cash_sales', 'card_sales', 'mobile_sales', 'total_sales', 'transaction_count', 'total_returns', 'return_count', 'net_sales'])
        return self

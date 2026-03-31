from django.db import models
from django.utils import timezone


class ReceiptCounter(models.Model):
    """
    Tracks sequential receipt numbers
    """
    receipt_type = models.CharField(max_length=10, unique=True)
    last_number = models.IntegerField(default=0)
    date = models.DateField(default=timezone.now)

    class Meta:
        verbose_name = 'Receipt Counter'
        verbose_name_plural = 'Receipt Counters'

    def __str__(self):
        return f"{self.receipt_type}: {self.last_number} ({self.date})"


class Cart(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('held', 'Held'),
        ('voided', 'Voided'),
    ]
    
    customer = models.ForeignKey('customers.Customer', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')
    void_reason = models.TextField(blank=True, null=True)  # Reason for voiding held orders
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cashier = models.ForeignKey('users.UserProfile', on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return f"Cart {self.id} - {self.status}"

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    product = models.ForeignKey('inventory.Product', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    def __str__(self):
        return f"{self.product.name} - {self.quantity}"

class Sale(models.Model):
    SALE_TYPES = [
        ('retail', 'Retail Sale'),
        ('wholesale', 'Wholesale Sale'),
    ]

    cart = models.OneToOneField(Cart, on_delete=models.CASCADE)
    customer = models.ForeignKey('customers.Customer', on_delete=models.SET_NULL, null=True, blank=True)
    shift = models.ForeignKey('shifts.Shift', on_delete=models.SET_NULL, null=True, blank=True)
    sale_type = models.CharField(max_length=10, choices=SALE_TYPES, default='retail')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    final_amount = models.DecimalField(max_digits=10, decimal_places=2)
    sale_date = models.DateTimeField(auto_now_add=True)
    receipt_number = models.CharField(max_length=50, unique=True)
    
    # Return code functionality
    return_code_used = models.CharField(max_length=20, null=True, blank=True)
    return_code_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Void functionality
    voided = models.BooleanField(default=False)
    void_reason = models.TextField(blank=True, null=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey('users.UserProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='voided_sales')

    # Edit functionality
    edit_reason = models.TextField(blank=True, null=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    edited_by = models.ForeignKey('users.UserProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='edited_sales')
    
    def __str__(self):
        return f"Sale {self.receipt_number}"

class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE)
    product = models.ForeignKey('inventory.Product', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    returned_quantity = models.PositiveIntegerField(default=0)  # Track how many items have been returned

    def __str__(self):
        return f"{self.product.name} - {self.quantity}"
    
    @property
    def remaining_quantity(self):
        """Returns the quantity that can still be returned"""
        return self.quantity - self.returned_quantity
    
    @property
    def is_fully_returned(self):
        """Returns True if all items have been returned"""
        return self.returned_quantity >= self.quantity

class Return(models.Model):
    RETURN_TYPES = [
        ('full_return', 'Full Return'),
        ('partial_return', 'Partial Return'),
        ('exchange', 'Exchange'),
    ]
    
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE)
    shift = models.ForeignKey('shifts.Shift', on_delete=models.SET_NULL, null=True, blank=True, related_name='returns')
    return_date = models.DateTimeField(auto_now_add=True)
    return_type = models.CharField(max_length=20, choices=RETURN_TYPES, default='partial_return')
    reason = models.TextField()
    total_refund_amount = models.DecimalField(max_digits=10, decimal_places=2)
    processed_by = models.ForeignKey('users.UserProfile', on_delete=models.SET_NULL, null=True)
    receipt_number = models.CharField(max_length=50, unique=True, blank=True, null=True)

    def __str__(self):
        return f"Return for Sale {self.sale.receipt_number}"

    def save(self, *args, **kwargs):
        """Auto-set shift from sale if not provided"""
        if not self.shift and hasattr(self, 'sale') and self.sale:
            self.shift = self.sale.shift
        super().save(*args, **kwargs)

class ReturnItem(models.Model):
    """Individual items in a return"""
    return_record = models.ForeignKey(Return, on_delete=models.CASCADE, related_name='items')
    sale_item = models.ForeignKey(SaleItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    reason = models.TextField()
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x from Return {self.return_record.id}"

class ReturnCode(models.Model):
    """Return codes for tracking refunds"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('used', 'Used'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ]
    
    code = models.CharField(max_length=12, unique=True)
    return_record = models.ForeignKey(Return, on_delete=models.CASCADE, related_name='return_codes', null=True, blank=True)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2)
    original_receipt_number = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    used_in_sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='applied_return_codes')
    
    def __str__(self):
        return f"ReturnCode {self.code}"
    
    @staticmethod
    def generate_code(refund_amount, receipt_number):
        """Generate a unique return code"""
        import random
        import string
        
        # Generate code: 4 letters + 4 numbers
        while True:
            letters = ''.join(random.choices(string.ascii_uppercase, k=4))
            numbers = ''.join(random.choices(string.digits, k=4))
            code = f"{letters}{numbers}"
            
            # Check if code already exists
            if not ReturnCode.objects.filter(code=code).exists():
                return code

class ExchangeItem(models.Model):
    """Items exchanged for other products in a return"""
    return_record = models.ForeignKey(Return, on_delete=models.CASCADE, related_name='exchange_items')
    product = models.ForeignKey('inventory.Product', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.product.name} for Return {self.return_record.id}"

class Invoice(models.Model):
    INVOICE_STATUS = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    invoice_number = models.CharField(max_length=50, unique=True)
    sale = models.OneToOneField(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoice')
    customer = models.ForeignKey('customers.Customer', on_delete=models.CASCADE)
    invoice_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=INVOICE_STATUS, default='draft')

    # Financial details
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)

    # Additional fields
    notes = models.TextField(blank=True)
    terms = models.TextField(blank=True, default="Payment due within 30 days")
    created_by = models.ForeignKey('users.UserProfile', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Invoice {self.invoice_number}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Generate invoice number
            from django.utils import timezone
            self.invoice_number = f"INV{timezone.now().strftime('%Y%m%d')}{self.id or 1:04d}"
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        from django.utils import timezone
        return self.status in ['sent', 'draft'] and self.due_date < timezone.now().date()

class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('inventory.Product', on_delete=models.CASCADE, null=True, blank=True)
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Percentage
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.description} - {self.quantity}"

    @property
    def subtotal(self):
        return self.quantity * self.unit_price

    @property
    def tax_amount(self):
        return self.subtotal * (self.tax_rate / 100)

    @property
    def total(self):
        return self.subtotal + self.tax_amount - self.discount_amount


class AuditLog(models.Model):
    OPERATION_CHOICES = [
        ('sale_create', 'Sale Created'),
        ('sale_complete', 'Sale Completed'),
        ('sale_void', 'Sale Voided'),
        ('sale_edit', 'Sale Edited'),
        ('stock_deduct', 'Stock Deducted'),
        ('stock_restore', 'Stock Restored'),
        ('payment_create', 'Payment Created'),
        ('payment_void', 'Payment Voided'),
        ('cart_hold', 'Cart Held'),
        ('cart_void', 'Cart Voided'),
        ('admin_action', 'Admin Action'),
    ]

    user = models.ForeignKey('users.UserProfile', on_delete=models.SET_NULL, null=True)
    operation = models.CharField(max_length=20, choices=OPERATION_CHOICES)
    entity_type = models.CharField(max_length=50)  # Sale, Cart, Payment, Product, etc.
    entity_id = models.PositiveIntegerField()
    description = models.TextField()
    old_values = models.JSONField(null=True, blank=True)  # Store previous values
    new_values = models.JSONField(null=True, blank=True)  # Store new values
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['operation', 'timestamp']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['entity_type', 'entity_id']),
        ]

    def __str__(self):
        return f"{self.user.user.username if self.user else 'System'} - {self.operation} - {self.timestamp}"

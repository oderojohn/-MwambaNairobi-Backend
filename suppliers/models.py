from django.db import models

# Create your models here.

class Supplier(models.Model):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name

class SupplierPriceHistory(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    product = models.ForeignKey('inventory.Product', on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.supplier.name} - {self.product.name} - {self.price} on {self.date}"

class PurchaseOrder(models.Model):
    ORDER_STATUS = [
        ('pending', 'Pending'),
        ('ordered', 'Ordered'),
        ('partially_received', 'Partially Received'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='purchase_orders')
    order_number = models.CharField(max_length=50, unique=True, blank=True)
    order_date = models.DateField(auto_now_add=True)
    expected_delivery_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"PO-{self.order_number or self.id} - {self.supplier.name}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            # Generate simple sequential order number
            last_order = PurchaseOrder.objects.order_by('-id').first()
            if last_order:
                # Extract the numeric part from last order number
                try:
                    last_num = int(last_order.order_number.replace('PO', ''))
                    new_num = last_num + 1
                except ValueError:
                    # If parsing fails, start from 1
                    new_num = 1
            else:
                new_num = 1
            # Pad with zeros (001, 002, etc.)
            self.order_number = f"PO{new_num:03d}"
        super().save(*args, **kwargs)

    def update_status(self):
        """Update order status based on received items"""
        items = self.items.all()
        if not items.exists():
            self.status = 'pending'
        else:
            received_count = items.filter(received_quantity__gt=0).count()
            total_count = items.count()

            if received_count == 0:
                self.status = 'ordered'
            elif received_count == total_count:
                # Check if all items are fully received
                fully_received = all(item.received_quantity >= item.quantity for item in items)
                self.status = 'received' if fully_received else 'partially_received'
            else:
                self.status = 'partially_received'

        self.save()

class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('inventory.Product', on_delete=models.CASCADE, related_name='purchase_order_items')
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    received_quantity = models.PositiveIntegerField(default=0)
    batch_number = models.CharField(max_length=50, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.product.name} - {self.quantity} units"

    @property
    def total_price(self):
        return self.quantity * self.unit_price

    @property
    def is_fully_received(self):
        return self.received_quantity >= self.quantity

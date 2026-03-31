from django.db import models
from django.contrib.auth.models import User


def default_topbar_permissions():
    """Default visibility for POS top bar buttons."""
    return {
        "pending_orders": True,
        "sales_summary": True,
        "shift": True,
        "order_prep": True,
        "logout": True,
        "global_sales": False,  # see all users' sales/shift data
    }

# Create your models here.

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('cashier', 'Cashier'),
        ('bartender', 'Bartender'),
        ('storekeeper', 'Storekeeper'),
        ('bar_manager', 'Bar Manager'),
        ('manager', 'Manager'),
        ('waiter', 'Waiter'),
        ('supervisor', 'Supervisor'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='cashier')
    phone = models.CharField(max_length=15, blank=True)
    branch = models.ForeignKey('branches.Branch', on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    pin = models.CharField(max_length=5, blank=True, null=True, unique=True)  # 5-digit PIN for quick login

    def __str__(self):
        return f"{self.user.username} - {self.role}"


class TopBarPermission(models.Model):
    """Per-user control over which POS header buttons are visible/usable."""

    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="topbar_permissions"
    )
    allowed_buttons = models.JSONField(default=default_topbar_permissions)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"TopBarPermission for {self.user_profile.user.username}"


class UserAuditLog(models.Model):
    ACTION_CHOICES = [
        ('login', 'Login'),
        ('login_failed', 'Login Failed'),
        ('logout', 'Logout'),
        ('request', 'Request'),
        ('shift_started', 'Shift Started'),
        ('shift_closed', 'Shift Closed'),
        ('user_created', 'User Created'),
        ('user_updated', 'User Updated'),
        ('user_deleted', 'User Deleted'),
        ('group_created', 'Group Created'),
        ('group_updated', 'Group Updated'),
        ('group_deleted', 'Group Deleted'),
        ('permissions_updated', 'Permissions Updated'),
        ('product_created', 'Product Created'),
        ('product_updated', 'Product Updated'),
        ('product_deleted', 'Product Deleted'),
        ('product_price_changed', 'Product Price Changed'),
        ('stock_recalculated', 'Stock Recalculated'),
        ('batch_received', 'Batch Received'),
        ('sale_created', 'Sale Created'),
        ('held_order_created', 'Held Order Created'),
        ('held_order_updated', 'Held Order Updated'),
        ('held_order_voided', 'Held Order Voided'),
        ('sale_voided', 'Sale Voided'),
        ('transaction_voided', 'Transaction Voided'),
        ('return_created', 'Return Created'),
        ('payment_created', 'Payment Created'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    username = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=50, blank=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, default='request')
    method = models.CharField(max_length=16, blank=True)
    path = models.CharField(max_length=255, blank=True)
    status_code = models.PositiveIntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        actor = self.username or 'unknown'
        return f"{actor} - {self.action} - {self.created_at:%Y-%m-%d %H:%M:%S}"

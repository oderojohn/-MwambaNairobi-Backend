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

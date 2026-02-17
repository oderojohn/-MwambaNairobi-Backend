from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Sale, Return
from payments.models import Payment

@receiver(post_save, sender=Sale)
def create_default_payment(sender, instance, created, **kwargs):
    """
    Create a default payment record for sales that don't have any payment.
    This ensures that every sale always has at least one payment record,
    preventing 'N/A' from appearing in payment method displays.
    Only runs for newly created sales.
    """
    # Skip if flagged to skip default payment creation
    if hasattr(instance, '_skip_default_payment') and instance._skip_default_payment:
        return

    if created and not instance.voided and not instance.payment_set.exists():
        # Create a default cash payment for the sale
        Payment.objects.create(
            sale=instance,
            payment_type='cash',
            amount=instance.final_amount,
            status='completed',
            description='Auto-generated default payment'
        )

@receiver(post_save, sender=Return)
def update_shift_return_totals(sender, instance, created, **kwargs):
    """
    Update shift return totals when a return is created or modified.
    """
    from shifts.models import Shift
    
    sale = instance.sale
    if sale and sale.shift:
        try:
            shift = Shift.objects.get(id=sale.shift.id)
            shift.update_return_totals()
        except Shift.DoesNotExist:
            pass

@receiver(post_delete, sender=Return)
def update_shift_return_totals_on_delete(sender, instance, **kwargs):
    """
    Update shift return totals when a return is deleted.
    """
    from shifts.models import Shift
    
    sale = instance.sale
    if sale and sale.shift:
        try:
            shift = Shift.objects.get(id=sale.shift.id)
            shift.update_return_totals()
        except Shift.DoesNotExist:
            pass

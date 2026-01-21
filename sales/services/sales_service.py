from django.utils import timezone
from django.db import transaction
from django.db.models.signals import post_save
from decimal import Decimal
from ..models import Cart, CartItem, Sale, SaleItem
from ..signals import create_default_payment
from shifts.models import Shift


def get_held_orders(cashier):
    """Get all held orders for the current cashier's shift"""
    try:
        current_shift = Shift.objects.get(cashier=cashier, status='open')
    except Shift.DoesNotExist:
        raise ValueError('No active shift found')

    held_carts = Cart.objects.filter(
        cashier=cashier,
        status='held'
    ).prefetch_related('cartitem_set__product').order_by('-created_at')

    return held_carts


def complete_held_order(cart, request_data, cashier, current_shift):
    """Complete a held order by creating the sale and processing payment"""
    # Calculate totals from cart items
    cart_items = cart.cartitem_set.all()
    subtotal = sum(float(item.unit_price) * int(item.quantity) for item in cart_items)
    tax_amount = float(request_data.get('tax_amount', 0))
    discount_amount = float(request_data.get('discount_amount', 0))
    total_amount = float(request_data.get('total_amount', subtotal + tax_amount - discount_amount))
    receipt_number = request_data.get('receipt_number', f'POS-{timezone.now().strftime("%Y%m%d%H%M%S")}')

    # Create sale
    # Temporarily disconnect the signal to prevent duplicate payments
    post_save.disconnect(create_default_payment, sender=Sale)

    sale = Sale.objects.create(
        cart=cart,
        customer=cart.customer,
        shift=current_shift,
        sale_type=request_data.get('sale_type', 'retail'),
        total_amount=float(subtotal),
        tax_amount=float(tax_amount),
        discount_amount=float(discount_amount),
        final_amount=float(total_amount),
        receipt_number=receipt_number
    )

    # Reconnect the signal
    post_save.connect(create_default_payment, sender=Sale)

    # Create sale items
    for cart_item in cart_items:
        SaleItem.objects.create(
            sale=sale,
            product=cart_item.product,
            quantity=int(cart_item.quantity),
            unit_price=float(cart_item.unit_price),
            discount=float(cart_item.discount)
        )

    # Update cart status to closed
    cart.status = 'closed'
    cart.save()

    return sale


def void_held_order(cart, void_reason, cashier):
    """Void/cancel a held order with a reason"""
    cart.status = 'voided'
    cart.void_reason = void_reason
    cart.save()

    return cart


def void_sale(sale, void_reason, user):
    """Void a completed sale with a reason"""
    # Mark sale as voided
    sale.voided = True
    sale.void_reason = void_reason
    sale.voided_at = timezone.now()
    sale.voided_by = user.userprofile if hasattr(user, 'userprofile') else None
    sale.save()

    return sale


def create_sale_from_cart(cart, request_data, cashier, current_shift):
    """Create a sale from cart data (used in the create method)"""
    # Calculate totals
    cart_items = cart.cartitem_set.all()
    subtotal = sum(float(item.unit_price) * int(item.quantity) for item in cart_items)
    tax_amount = float(request_data.get('tax_amount', 0))
    discount_amount = float(request_data.get('discount_amount', 0))
    total_amount = float(request_data.get('total_amount', subtotal + tax_amount - discount_amount))
    receipt_number = request_data.get('receipt_number', f'POS-{timezone.now().strftime("%Y%m%d%H%M%S")}')

    # Create sale
    # Temporarily disconnect the signal to prevent duplicate payments
    post_save.disconnect(create_default_payment, sender=Sale)

    sale = Sale.objects.create(
        cart=cart,
        customer=cart.customer,
        shift=current_shift,
        sale_type=request_data.get('sale_type', 'retail'),
        total_amount=float(subtotal),
        tax_amount=float(tax_amount),
        discount_amount=float(discount_amount),
        final_amount=float(total_amount),
        receipt_number=receipt_number
    )

    # Reconnect the signal
    post_save.connect(create_default_payment, sender=Sale)

    # Create sale items from cart items
    for cart_item in cart_items:
        SaleItem.objects.create(
            sale=sale,
            product=cart_item.product,
            quantity=int(cart_item.quantity),
            unit_price=float(cart_item.unit_price),
            discount=float(cart_item.discount)
        )

    return sale
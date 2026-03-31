from django.db.models import F
from decimal import Decimal
from payments.models import Payment


def validate_payment_method(payment_method, split_data=None):
    """Validate payment method and split data if applicable"""
    valid_payment_methods = ['cash', 'mpesa', 'mobile', 'split']
    if payment_method not in valid_payment_methods:
        raise ValueError(f'Invalid payment method. Must be one of: {", ".join(valid_payment_methods)}')

    if payment_method == 'split':
        if not split_data or (split_data.get('cash', 0) == 0 and split_data.get('mpesa', 0) == 0):
            raise ValueError('Split payment requires cash and/or mpesa amounts in split_data')


def create_payment(sale, payment_method, total_amount, request_data):
    """Create payment record(s) for the sale"""
    created_payments = []

    if payment_method == 'split':
        # For split payments, create appropriate payment records
        split_data = request_data.get('split_data', {})
        cash_amount = split_data.get('cash', 0)
        mpesa_amount = split_data.get('mpesa', 0)

        # Check if it's truly split (both amounts > 0) or pure payment
        if cash_amount > 0 and mpesa_amount > 0:
            # True split payment - create two records
            payment = Payment.objects.create(
                sale=sale,
                payment_type='cash',
                amount=cash_amount,
                status='completed'
            )
            created_payments.append(payment)

            payment = Payment.objects.create(
                sale=sale,
                payment_type='mpesa',
                amount=mpesa_amount,
                mpesa_number=request_data.get('mpesa_number', ''),
                status='completed'
            )
            created_payments.append(payment)
        elif mpesa_amount > 0:
            # Pure M-Pesa payment
            payment = Payment.objects.create(
                sale=sale,
                payment_type='mpesa',
                amount=mpesa_amount,
                mpesa_number=request_data.get('mpesa_number', ''),
                status='completed'
            )
            created_payments.append(payment)
        elif cash_amount > 0:
            # Pure cash payment
            payment = Payment.objects.create(
                sale=sale,
                payment_type='cash',
                amount=cash_amount,
                status='completed'
            )
            created_payments.append(payment)
    else:
        # Single payment method
        payment_type = 'cash'
        if payment_method in ['mpesa', 'mobile']:
            payment_type = 'mpesa'

        payment = Payment.objects.create(
            sale=sale,
            payment_type=payment_type,
            amount=total_amount,
            mpesa_number=request_data.get('mpesa_number', '') if payment_type == 'mpesa' else '',
            status='completed'
        )
        created_payments.append(payment)

    # Validate payment amounts
    if not created_payments:
        raise ValueError("No payment records were created for this transaction")

    total_payment_amount = sum(float(p.amount) for p in created_payments)
    if abs(total_payment_amount - float(total_amount)) > 0.01:
        raise ValueError(f"Payment amount mismatch: payments total {total_payment_amount}, sale total {total_amount}")

    return created_payments


def update_shift_totals(shift, payment_method, total_amount, split_data=None):
    """Update shift totals based on payment method"""
    sale_amount = Decimal(str(total_amount))
    update_fields = ['total_sales']

    if payment_method == 'split':
        # For split payments, use the split data
        cash_amount = Decimal(str(split_data.get('cash', 0)))
        mpesa_amount = Decimal(str(split_data.get('mpesa', 0)))
        shift.cash_sales = F('cash_sales') + cash_amount
        shift.mobile_sales = F('mobile_sales') + mpesa_amount
        update_fields.extend(['cash_sales', 'mobile_sales'])
    elif payment_method == 'cash':
        shift.cash_sales = F('cash_sales') + sale_amount
        update_fields.append('cash_sales')
    elif payment_method in ['mpesa', 'mobile']:
        shift.mobile_sales = F('mobile_sales') + sale_amount
        update_fields.append('mobile_sales')

    shift.total_sales = F('total_sales') + sale_amount
    shift.save(update_fields=update_fields)


def update_shift_totals_on_void(shift, sale):
    """Update shift totals when voiding a sale (subtract the voided sale)"""
    if not shift:
        return

    void_amount = Decimal(str(sale.final_amount))

    # Get payment method from payment record
    payment = sale.payment_set.first()
    payment_method = payment.payment_type if payment else 'cash'

    # Subtract from shift totals based on payment method
    if payment_method == 'cash':
        shift.cash_sales = F('cash_sales') - void_amount
        shift.save(update_fields=['cash_sales'])
    elif payment_method == 'card':
        shift.card_sales = F('card_sales') - void_amount
        shift.save(update_fields=['card_sales'])
    elif payment_method in ['mpesa', 'mobile']:
        shift.mobile_sales = F('mobile_sales') - void_amount
        shift.save(update_fields=['mobile_sales'])

    # Subtract from total sales
    shift.total_sales = F('total_sales') - void_amount
    shift.save(update_fields=['total_sales'])


def update_shift_totals_on_partial_void(shift, void_amount):
    """Update shift totals when voiding specific items from a sale (partial void)"""
    if not shift:
        return

    void_amount = Decimal(str(void_amount))

    # Subtract from total sales
    shift.total_sales = F('total_sales') - void_amount
    shift.save(update_fields=['total_sales'])
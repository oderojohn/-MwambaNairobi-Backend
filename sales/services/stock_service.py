from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from inventory.models import Product, StockMovement, SalesHistory, Batch
from .audit_service import log_stock_operation


def validate_stock_availability(cart_items):
    """Validate that all items in cart have sufficient stock"""
    from inventory.models import Batch
    from django.utils import timezone
    
    stock_deductions = []
    for cart_item in cart_items:
        product = cart_item.product
        requested_quantity = int(cart_item.quantity)

        # Validate quantity is positive
        if requested_quantity <= 0:
            raise ValueError(f'Invalid quantity for product "{product.name}". Quantity must be positive.')

        # Calculate actual available stock from batches (more accurate than product.stock_quantity)
        available_batches = Batch.objects.filter(
            product=product,
            quantity__gt=0
        ).exclude(
            status__in=['damaged', 'expired'],
            expiry_date__lt=timezone.now().date()
        )
        
        actual_available = sum(batch.quantity for batch in available_batches)
        
        # Use actual batch stock if available, otherwise fall back to product.stock_quantity
        available_stock = max(actual_available, float(product.stock_quantity)) if actual_available > 0 else float(product.stock_quantity)
        
        if available_stock < requested_quantity:
            raise ValueError(f'Insufficient stock for product "{product.name}". Available: {int(available_stock)}, Requested: {requested_quantity}')

        stock_deductions.append({
            'product': product,
            'quantity': requested_quantity,
            'cart_item': cart_item
        })

    return stock_deductions


def deduct_stock(stock_deductions, sale, cashier, request=None):
    """Deduct stock from inventory using FIFO batch logic"""
    for deduction in stock_deductions:
        product = deduction['product']
        remaining_quantity = deduction['quantity']

        # Get available batches for this product, ordered by expiry date (FIFO)
        available_batches = Batch.objects.filter(
            product=product,
            quantity__gt=0
        ).exclude(
            status__in=['damaged', 'expired'],
            expiry_date__lt=timezone.now().date()
        ).order_by('expiry_date', 'purchase_date')

        batch_deductions = []
        for batch in available_batches:
            if remaining_quantity <= 0:
                break

            take_quantity = min(remaining_quantity, batch.quantity)

            # Validate take_quantity is positive
            if take_quantity <= 0:
                raise ValueError(f"Invalid take quantity {take_quantity} for batch {batch.batch_number}")
            batch_deductions.append({
                'batch': batch,
                'quantity': take_quantity
            })
            remaining_quantity -= take_quantity

        # Check if we have enough stock across all batches
        total_available = sum(d['quantity'] for d in batch_deductions)
        if total_available < deduction['quantity']:
            # If no batches found but product has stock, allow the sale (fallback for missing batch data)
            if not available_batches.exists() and float(product.stock_quantity) >= deduction['quantity']:
                # Skip batch deduction logic and just reduce product stock
                product.stock_quantity = Decimal(str(product.stock_quantity)) - Decimal(str(deduction['quantity']))
                product.save(update_fields=['stock_quantity'])

                # Create stock movement record without batch
                StockMovement.objects.create(
                    product=product,
                    movement_type='out',
                    quantity=-deduction['quantity'],
                    reason=f'Sale {sale.receipt_number} - No batch tracking',
                    user=cashier
                )

                # Create sales history record without batch
                SalesHistory.objects.create(
                    product=product,
                    batch=None,
                    quantity=deduction['quantity'],
                    unit_price=deduction['cart_item'].unit_price,
                    cost_price=None,
                    total_price=deduction['cart_item'].unit_price * deduction['quantity'],
                    receipt_number=sale.receipt_number,
                    sale_date=sale.sale_date
                )

                # Log stock deduction
                log_stock_operation(
                    user=cashier,
                    operation='stock_deduct',
                    product=product,
                    description=f'Stock deducted for sale {sale.receipt_number}: {deduction["quantity"]} units (no batch)',
                    old_values={'stock_quantity': float(product.stock_quantity) + deduction['quantity']},
                    new_values={'stock_quantity': float(product.stock_quantity)},
                    request=request
                )
                continue
            else:
                raise ValueError(f'Insufficient stock for product "{product.name}". Available: {total_available}, Required: {deduction["quantity"]}')

        # Apply the deductions
        for batch_deduction in batch_deductions:
            batch = batch_deduction['batch']
            quantity = batch_deduction['quantity']

            # Reduce batch quantity
            batch.quantity = Decimal(str(batch.quantity)) - Decimal(str(quantity))
            batch.save(update_fields=['quantity'])

            # Deduct from product total stock
            product.stock_quantity = Decimal(str(product.stock_quantity)) - Decimal(str(quantity))
            product.save(update_fields=['stock_quantity'])

            # Create stock movement record
            StockMovement.objects.create(
                product=product,
                movement_type='out',
                quantity=-quantity,
                reason=f'Sale {sale.receipt_number} - Batch {batch.batch_number}',
                user=cashier
            )

            # Create sales history record with batch information
            SalesHistory.objects.create(
                product=product,
                batch=batch,
                quantity=quantity,
                unit_price=deduction['cart_item'].unit_price,
                cost_price=batch.cost_price,
                total_price=deduction['cart_item'].unit_price * quantity,
                receipt_number=sale.receipt_number,
                sale_date=sale.sale_date
            )

            # Log batch stock deduction
            log_stock_operation(
                user=cashier,
                operation='stock_deduct',
                product=product,
                description=f'Stock deducted for sale {sale.receipt_number}: {quantity} units from batch {batch.batch_number}',
                old_values={'stock_quantity': float(product.stock_quantity) + quantity, 'batch_quantity': float(batch.quantity) + quantity},
                new_values={'stock_quantity': float(product.stock_quantity), 'batch_quantity': float(batch.quantity)},
                request=request
            )


def restore_stock(sale, user, request=None):
    """Restore stock quantities when voiding a sale"""
    for sale_item in sale.saleitem_set.all():
        product = sale_item.product
        quantity_to_restore = sale_item.quantity

        # Validate quantity is positive
        if quantity_to_restore <= 0:
            raise ValueError(f'Invalid quantity for product "{product.name}" in voided sale. Quantity must be positive.')

        # Store old quantity for logging
        old_quantity = float(product.stock_quantity)

        # Restore product stock
        product.stock_quantity = Decimal(str(product.stock_quantity)) + Decimal(str(quantity_to_restore))
        product.save(update_fields=['stock_quantity'])

        # Create stock movement record
        StockMovement.objects.create(
            product=product,
            movement_type='in',
            quantity=quantity_to_restore,
            reason=f'Sale void {sale.receipt_number} - {sale.void_reason}',
            user=user.userprofile if hasattr(user, 'userprofile') else None
        )

        # Log stock restoration
        log_stock_operation(
            user=user.userprofile if hasattr(user, 'userprofile') else None,
            operation='stock_restore',
            product=product,
            description=f'Stock restored for voided sale {sale.receipt_number}: {quantity_to_restore} units',
            old_values={'stock_quantity': old_quantity},
            new_values={'stock_quantity': float(product.stock_quantity)},
            request=request
        )

        # Update batch quantities if applicable
        sales_history_records = SalesHistory.objects.filter(
            product=product,
            receipt_number=sale.receipt_number
        )

        for history_record in sales_history_records:
            if history_record.batch:
                batch = history_record.batch
                batch.quantity = Decimal(str(batch.quantity)) + Decimal(str(history_record.quantity))
                batch.save(update_fields=['quantity'])


def restore_stock_quantity(product, quantity, sale, user, request=None):
    """Restore a specific quantity of stock for a product (used when editing sales)"""
    # Validate quantity is positive
    if quantity <= 0:
        raise ValueError(f'Invalid quantity for product "{product.name}". Quantity must be positive.')

    # Store old quantity for logging
    old_quantity = float(product.stock_quantity)

    # Restore product stock
    product.stock_quantity = Decimal(str(product.stock_quantity)) + Decimal(str(quantity))
    product.save(update_fields=['stock_quantity'])

    # Create stock movement record
    StockMovement.objects.create(
        product=product,
        movement_type='in',
        quantity=quantity,
        reason=f'Sale edit {sale.receipt_number} - quantity adjustment',
        user=user.userprofile if hasattr(user, 'userprofile') else None
    )

    # Log stock restoration
    log_stock_operation(
        user=user.userprofile if hasattr(user, 'userprofile') else None,
        operation='stock_restore',
        product=product,
        description=f'Stock restored for edited sale {sale.receipt_number}: {quantity} units',
        old_values={'stock_quantity': old_quantity},
        new_values={'stock_quantity': float(product.stock_quantity)},
        request=request
    )


def adjust_stock(product_id, quantity, movement_type, reference, cashier):
    """Adjust stock for returns and exchanges - add or remove stock"""
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        raise ValueError(f'Product with ID {product_id} not found')

    # Validate quantity
    abs_quantity = abs(quantity)
    if abs_quantity <= 0:
        raise ValueError('Quantity must be positive or negative')

    # Store old quantity for logging
    old_quantity = float(product.stock_quantity)

    # Determine if adding or removing stock
    is_add = quantity > 0

    # Update product stock
    if is_add:
        product.stock_quantity = Decimal(str(product.stock_quantity)) + Decimal(str(abs_quantity))
    else:
        product.stock_quantity = Decimal(str(product.stock_quantity)) - Decimal(str(abs_quantity))

    # Validate stock doesn't go negative
    if float(product.stock_quantity) < 0:
        raise ValueError(f'Cannot adjust stock for product "{product.name}". Stock would go negative.')

    product.save(update_fields=['stock_quantity'])

    # Determine movement type for the record
    if movement_type == 'return':
        move_type = 'in'
    elif movement_type == 'exchange':
        move_type = 'out'
    else:
        move_type = 'adjustment'

    # Create stock movement record
    StockMovement.objects.create(
        product=product,
        movement_type=move_type,
        quantity=abs_quantity if is_add else -abs_quantity,
        reason=f'{reference}',
        user=cashier
    )

    # Log the operation
    log_stock_operation(
        user=cashier,
        operation='stock_adjustment',
        product=product,
        description=f'Stock {movement_type}: {abs_quantity} units - {reference}',
        old_values={'stock_quantity': old_quantity},
        new_values={'stock_quantity': float(product.stock_quantity)},
        request=None
    )

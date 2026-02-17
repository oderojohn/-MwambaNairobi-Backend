from ..models import AuditLog


def log_action(user, action, details, request=None):
    """
    Log a general action with user attribution
    Simplified version for basic action logging
    """
    try:
        audit_log = AuditLog.objects.create(
            user=user,
            operation=action,
            entity_type='Return',
            entity_id=None,
            description=str(details),
        )
        
        # Add request details if available
        if request:
            audit_log.ip_address = get_client_ip(request)
            audit_log.user_agent = request.META.get('HTTP_USER_AGENT', '')
            audit_log.save()
        
        return audit_log
    except Exception as e:
        print(f"Failed to create audit log: {e}")
        return None


def log_operation(user, operation, entity_type, entity_id, description,
                 old_values=None, new_values=None, request=None):
    """
    Log an audit operation with user attribution and optional request details
    """
    try:
        audit_log = AuditLog.objects.create(
            user=user,
            operation=operation,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            old_values=old_values,
            new_values=new_values,
        )

        # Add request details if available
        if request:
            audit_log.ip_address = get_client_ip(request)
            audit_log.user_agent = request.META.get('HTTP_USER_AGENT', '')
            audit_log.save()

        return audit_log
    except Exception as e:
        # Log the error but don't fail the operation
        print(f"Failed to create audit log: {e}")
        return None


def get_client_ip(request):
    """Get the client IP address from the request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def log_sale_operation(user, operation, sale, description, old_values=None, new_values=None, request=None):
    """Log sale-related operations"""
    return log_operation(
        user=user,
        operation=operation,
        entity_type='Sale',
        entity_id=sale.id,
        description=description,
        old_values=old_values,
        new_values=new_values,
        request=request
    )


def log_stock_operation(user, operation, product, description, old_values=None, new_values=None, request=None):
    """Log stock-related operations"""
    return log_operation(
        user=user,
        operation=operation,
        entity_type='Product',
        entity_id=product.id,
        description=description,
        old_values=old_values,
        new_values=new_values,
        request=request
    )


def log_payment_operation(user, operation, payment, description, old_values=None, new_values=None, request=None):
    """Log payment-related operations"""
    return log_operation(
        user=user,
        operation=operation,
        entity_type='Payment',
        entity_id=payment.id,
        description=description,
        old_values=old_values,
        new_values=new_values,
        request=request
    )


def log_cart_operation(user, operation, cart, description, old_values=None, new_values=None, request=None):
    """Log cart-related operations"""
    return log_operation(
        user=user,
        operation=operation,
        entity_type='Cart',
        entity_id=cart.id,
        description=description,
        old_values=old_values,
        new_values=new_values,
        request=request
    )
"""
Sequential Receipt Number Generator
Generates consistent, sequential receipt numbers starting from the highest existing number
"""

from django.db import transaction
from django.utils import timezone
from ..models import ReceiptCounter, Sale, Return


def get_next_receipt_number(receipt_type='POS'):
    """
    Get the next sequential receipt number.
    
    Args:
        receipt_type: Type of receipt ('POS' for sales, 'RET' for returns)
    
    Returns:
        str: Receipt number in format 'POS-0001', 'POS-0002', etc. (up to 1000000)
    """
    with transaction.atomic():
        # Get the highest existing number first (this is the source of truth)
        highest_number = get_highest_existing_number(receipt_type)
        
        # Use select_for_update to prevent concurrent modifications
        counter, created = ReceiptCounter.objects.select_for_update().get_or_create(
            receipt_type=receipt_type,
            defaults={
                'last_number': 0,
                'date': timezone.now().date()
            }
        )
        
        # Always start from the highest existing number + 1
        # This ensures we don't skip numbers even if the counter is out of sync
        next_number = max(highest_number, counter.last_number) + 1
        
        # Check if we've reached the limit (1000000)
        if next_number > 1000000:
            next_number = 1  # Reset to 1 after reaching 1000000
        
        # Update the counter
        counter.last_number = next_number
        counter.save()
        
        # Format with zero-padding (4 digits: 0001, 0002, up to 1000000)
        return f"{receipt_type}-{next_number:04d}"


def get_highest_existing_number(receipt_type):
    """
    Get the highest existing receipt number from sales/returns.
    Only looks at sequential format (4 digits like POS-0001, POS-0999, POS-1000).
    Ignores old timestamp format (POS-1770976971366) to allow fresh sequential numbering.
    
    Args:
        receipt_type: Type of receipt ('POS' for sales, 'RET' for returns)
    
    Returns:
        int: The highest existing sequential receipt number (0 if none)
    """
    import re
    prefix = f"{receipt_type}-"
    
    highest = 0
    
    # Check sales
    if receipt_type == 'POS':
        from ..models import Sale
        sales = Sale.objects.filter(receipt_number__startswith=prefix)
        for sale in sales:
            try:
                num_str = sale.receipt_number.replace(prefix, '')
                # Only consider sequential format (up to 7 digits, typically 4 digits for our use case)
                # Match numbers that look like sequential format (not timestamps)
                if len(num_str) <= 7 and num_str.isdigit():
                    num = int(num_str)
                    if num > highest:
                        highest = num
            except (ValueError, AttributeError):
                pass
    
    # Check returns
    elif receipt_type == 'RET':
        from ..models import Return
        returns = Return.objects.filter(receipt_number__startswith=prefix)
        for ret in returns:
            try:
                num_str = ret.receipt_number.replace(prefix, '')
                # Only consider sequential format (up to 7 digits)
                if len(num_str) <= 7 and num_str.isdigit():
                    num = int(num_str)
                    if num > highest:
                        highest = num
            except (ValueError, AttributeError):
                pass
    
    return highest


def get_next_sale_receipt_number():
    """Get the next sequential sale receipt number (POS-0001)"""
    return get_next_receipt_number('POS')


def get_next_return_receipt_number():
    """Get the next sequential return receipt number (RET-0001)"""
    return get_next_receipt_number('RET')

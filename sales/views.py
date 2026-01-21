from rest_framework import viewsets, status, serializers
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from django.db.models import Q
from .models import Cart, CartItem, Sale, SaleItem, Return, Invoice, InvoiceItem, AuditLog
from .serializers import CartSerializer, CartItemSerializer, SaleSerializer, SaleItemSerializer, ReturnSerializer, InvoiceSerializer, InvoiceItemSerializer, AuditLogSerializer
from inventory.models import Product, StockMovement, SalesHistory
from shifts.models import Shift
from payments.models import Payment
from .services import sales_service, stock_service, payment_service, audit_service

class CartViewSet(viewsets.ModelViewSet):
    queryset = Cart.objects.all()
    serializer_class = CartSerializer

class CartItemViewSet(viewsets.ModelViewSet):
    queryset = CartItem.objects.all()
    serializer_class = CartItemSerializer

class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer
    pagination_class = PageNumberPagination

    @action(detail=False, methods=['get'])
    def held_orders(self, request):
        """Get all held orders for the current cashier's shift"""
        cashier = None
        if hasattr(request.user, 'userprofile'):
            cashier = request.user.userprofile

        if not cashier:
            return Response(
                {'error': 'User profile not found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            held_carts = sales_service.get_held_orders(cashier)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CartSerializer(held_carts, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def complete_held_order(self, request, pk=None):
        """Complete a held order by creating the sale and processing payment"""
        try:
            cart = Cart.objects.get(id=pk, status='held')
        except Cart.DoesNotExist:
            return Response(
                {'error': 'Held order not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if cashier has active shift
        cashier = None
        if hasattr(request.user, 'userprofile'):
            cashier = request.user.userprofile

        if not cashier or cart.cashier != cashier:
            return Response(
                {'error': 'Unauthorized to complete this order'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            current_shift = Shift.objects.get(cashier=cashier, status='open')
        except Shift.DoesNotExist:
            return Response(
                {'error': 'No active shift found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                # Calculate totals from cart items
                cart_items = cart.cartitem_set.all()
                subtotal = sum(float(item.unit_price) * int(item.quantity) for item in cart_items)
                tax_amount = float(request.data.get('tax_amount', 0))
                discount_amount = float(request.data.get('discount_amount', 0))
                total_amount = float(request.data.get('total_amount', subtotal + tax_amount - discount_amount))

                # Validate payment method
                payment_method = request.data.get('payment_method', '').strip().lower()
                if not payment_method:
                    return Response(
                        {'error': 'Payment method is required for all transactions'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                try:
                    payment_service.validate_payment_method(payment_method, request.data.get('split_data'))
                except ValueError as e:
                    return Response(
                        {'error': str(e)},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Create sale
                sale = sales_service.complete_held_order(cart, request.data, cashier, current_shift)

                # Log sale completion
                audit_service.log_sale_operation(
                    user=cashier,
                    operation='sale_complete',
                    sale=sale,
                    description=f'Completed held order {cart.id} into sale {sale.receipt_number}',
                    request=request
                )

                # Update shift totals
                payment_service.update_shift_totals(current_shift, payment_method, total_amount, request.data.get('split_data'))

                # Validate and deduct stock
                try:
                    stock_deductions = stock_service.validate_stock_availability(cart_items)
                    stock_service.deduct_stock(stock_deductions, sale, cashier, request)
                except ValueError as e:
                    return Response(
                        {'error': str(e)},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Create payment
                try:
                    created_payments = payment_service.create_payment(sale, payment_method, total_amount, request.data)
                    # Log payment creation
                    for payment in created_payments:
                        audit_service.log_payment_operation(
                            user=cashier,
                            operation='payment_create',
                            payment=payment,
                            description=f'Created payment for sale {sale.receipt_number}',
                            request=request
                        )
                except ValueError as e:
                    return Response(
                        {'error': str(e)},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Serialize and return the sale
                serializer = self.get_serializer(sale)
                return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(f"Error completing held order: {str(e)}")
            import traceback
            traceback.print_exc()

            # Provide user-friendly error messages
            error_message = str(e)
            if 'stock' in error_message.lower():
                user_error = '❌ Insufficient Stock'
                user_message = 'One or more items in this order are out of stock.'
                user_details = 'Please check inventory levels and restock if necessary.'
            elif 'payment' in error_message.lower():
                user_error = '❌ Payment Error'
                user_message = 'There was an issue processing the payment.'
                user_details = 'Please check your payment details and try again.'
            elif 'split payment requires' in error_message.lower():
                user_error = '❌ Payment Error'
                user_message = 'Split payment requires cash and/or M-Pesa amounts.'
                user_details = 'Please enter valid amounts for both payment methods or choose a single payment method.'
            else:
                user_error = '❌ Order Completion Error'
                user_message = 'An unexpected error occurred while completing the order.'
                user_details = 'Please contact your administrator if this problem persists.'

            return Response({
                'error': user_error,
                'message': user_message,
                'details': user_details,
                'technical_error': error_message if settings.DEBUG else None
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def void_held_order(self, request, pk=None):
        """Void/cancel a held order with a reason"""
        try:
            cart = Cart.objects.get(id=pk, status='held')
        except Cart.DoesNotExist:
            return Response(
                {'error': 'Held order not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if cashier has permission to void this order
        cashier = None
        if hasattr(request.user, 'userprofile'):
            cashier = request.user.userprofile

        if not cashier or cart.cashier != cashier:
            return Response(
                {'error': 'Unauthorized to void this order'},
                status=status.HTTP_403_FORBIDDEN
            )

        void_reason = request.data.get('void_reason', '').strip()
        if not void_reason:
            return Response(
                {'error': 'Void reason is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Void the order
        sales_service.void_held_order(cart, void_reason, cashier)

        return Response({
            'message': 'Held order voided successfully',
            'void_reason': void_reason
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def void_sale(self, request, pk=None):
        """Void a completed sale with a reason"""
        try:
            sale = Sale.objects.get(id=pk)
        except Sale.DoesNotExist:
            return Response(
                {'error': 'Sale not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if sale is already voided
        if sale.voided:
            return Response(
                {'error': 'Sale is already voided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        void_reason = request.data.get('reason', '').strip()
        if not void_reason:
            return Response(
                {'error': 'Void reason is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                # Mark sale as voided
                sales_service.void_sale(sale, void_reason, request.user)

                # Restore stock quantities
                try:
                    stock_service.restore_stock(sale, request.user)
                except ValueError as e:
                    return Response(
                        {'error': str(e)},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Update shift totals (subtract the voided sale)
                payment_service.update_shift_totals_on_void(sale.shift, sale)

                return Response({
                    'message': 'Sale voided successfully',
                    'void_reason': void_reason,
                    'sale_id': sale.id
                }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error voiding sale: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({
                'error': 'Failed to void sale',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # POS Admin Actions
    @action(detail=True, methods=['post'], permission_classes=[])
    def admin_void_sale(self, request, pk=None):
        """Admin void a completed sale with a reason (requires admin/manager role)"""
        # Check admin permissions
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.role not in ['admin', 'manager']:
            return Response(
                {'error': 'Admin or Manager role required for this action'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            sale = Sale.objects.get(id=pk)
        except Sale.DoesNotExist:
            return Response(
                {'error': 'Sale not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if sale is already voided
        if sale.voided:
            return Response(
                {'error': 'Sale is already voided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        void_reason = request.data.get('reason', '').strip()
        if not void_reason:
            return Response(
                {'error': 'Void reason is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                # Mark sale as voided
                sales_service.void_sale(sale, void_reason, request.user)

                # Log admin void operation
                audit_service.log_sale_operation(
                    user=request.user.userprofile,
                    operation='admin_action',
                    sale=sale,
                    description=f'Admin voided sale {sale.receipt_number}: {void_reason}',
                    request=request
                )

                # Restore stock quantities
                try:
                    stock_service.restore_stock(sale, request.user, request)
                except ValueError as e:
                    return Response(
                        {'error': str(e)},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Update shift totals (subtract the voided sale)
                payment_service.update_shift_totals_on_void(sale.shift, sale)

                return Response({
                    'message': 'Sale voided successfully by admin',
                    'void_reason': void_reason,
                    'sale_id': sale.id,
                    'voided_by': request.user.username
                }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error admin voiding sale: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({
                'error': 'Failed to void sale',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], permission_classes=[])
    def sales_by_user(self, request):
        """View sales by user (requires admin/manager role)"""
        # Check admin permissions
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.role not in ['admin', 'manager']:
            return Response(
                {'error': 'Admin or Manager role required for this action'},
                status=status.HTTP_403_FORBIDDEN
            )

        user_id = request.query_params.get('user_id')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        queryset = Sale.objects.filter(voided=False)

        if user_id:
            queryset = queryset.filter(shift__cashier__user_id=user_id)

        if date_from:
            queryset = queryset.filter(sale_date__gte=date_from)

        if date_to:
            queryset = queryset.filter(sale_date__lte=date_to)

        # Group by user
        sales_by_user = {}
        for sale in queryset.select_related('shift__cashier__user'):
            user = sale.shift.cashier.user if sale.shift and sale.shift.cashier else None
            if user:
                user_key = f"{user.username} ({user.id})"
                if user_key not in sales_by_user:
                    sales_by_user[user_key] = {
                        'user_id': user.id,
                        'username': user.username,
                        'total_sales': 0,
                        'total_amount': 0,
                        'sales_count': 0,
                        'sales': []
                    }

                sales_by_user[user_key]['total_sales'] += 1
                sales_by_user[user_key]['total_amount'] += float(sale.final_amount)
                sales_by_user[user_key]['sales_count'] += 1
                sales_by_user[user_key]['sales'].append({
                    'id': sale.id,
                    'receipt_number': sale.receipt_number,
                    'final_amount': sale.final_amount,
                    'sale_date': sale.sale_date
                })

        return Response({
            'sales_by_user': sales_by_user,
            'total_users': len(sales_by_user),
            'filters': {
                'user_id': user_id,
                'date_from': date_from,
                'date_to': date_to
            }
        })

    @action(detail=True, methods=['patch'], permission_classes=[])
    def admin_edit_sale(self, request, pk=None):
        """Admin/Manager edit sale details (requires admin or manager role)"""
        # Check admin/manager permissions
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.role not in ['admin', 'manager']:
            return Response(
                {'error': 'Admin or Manager role required for this action'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            sale = Sale.objects.get(id=pk)
        except Sale.DoesNotExist:
            return Response(
                {'error': 'Sale not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Prevent editing voided sales
        if sale.voided:
            return Response(
                {'error': 'Cannot edit voided sales'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Allowed fields for editing
        allowed_fields = ['tax_amount', 'discount_amount', 'final_amount', 'receipt_number', 'edit_reason']
        updated_fields = []

        # Handle item quantity changes
        items_changed = False
        if 'items' in request.data and isinstance(request.data['items'], list):
            items_changed = True
            stock_adjustments = []
            total_amount_change = 0

            for item_data in request.data['items']:
                item_id = item_data.get('id')
                new_quantity = int(item_data.get('quantity', 0))

                if not item_id or new_quantity < 0:
                    continue

                try:
                    sale_item = SaleItem.objects.get(id=item_id, sale=sale)
                    old_quantity = sale_item.quantity

                    if new_quantity != old_quantity:
                        quantity_diff = new_quantity - old_quantity

                        # Calculate amount change
                        amount_change = float(sale_item.unit_price) * quantity_diff
                        total_amount_change += amount_change

                        # Prepare stock adjustment
                        stock_adjustments.append({
                            'product': sale_item.product,
                            'quantity_diff': quantity_diff,
                            'sale_item': sale_item,
                            'old_quantity': old_quantity,
                            'new_quantity': new_quantity
                        })

                        # Update sale item quantity
                        sale_item.quantity = new_quantity
                        sale_item.save()

                        updated_fields.append({
                            'field': f'item_{sale_item.product.name}_quantity',
                            'old_value': old_quantity,
                            'new_value': new_quantity
                        })

                except SaleItem.DoesNotExist:
                    continue

            # Apply stock adjustments
            if stock_adjustments:
                for adjustment in stock_adjustments:
                    if adjustment['quantity_diff'] > 0:
                        # Additional stock deduction needed
                        stock_service.deduct_stock(
                            [{adjustment['product']: adjustment['quantity_diff']}],
                            sale,
                            request.user,
                            request
                        )
                    elif adjustment['quantity_diff'] < 0:
                        # Stock restoration needed
                        stock_service.restore_stock_quantity(
                            adjustment['product'],
                            abs(adjustment['quantity_diff']),
                            sale,
                            request.user,
                            request
                        )

            # Update sale totals if items changed
            if total_amount_change != 0:
                sale.total_amount += Decimal(str(total_amount_change))
                sale.final_amount = sale.total_amount + sale.tax_amount - sale.discount_amount
                updated_fields.append({
                    'field': 'total_amount',
                    'old_value': 'auto-calculated',
                    'new_value': float(sale.total_amount)
                })
                updated_fields.append({
                    'field': 'final_amount',
                    'old_value': 'auto-calculated',
                    'new_value': float(sale.final_amount)
                })

        for field in allowed_fields:
            if field in request.data:
                old_value = getattr(sale, field)
                new_value = request.data[field]

                # Basic validation
                if field in ['tax_amount', 'discount_amount', 'final_amount']:
                    try:
                        new_value = float(new_value)
                        if new_value < 0:
                            return Response(
                                {'error': f'{field} cannot be negative'},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                    except (ValueError, TypeError):
                        return Response(
                            {'error': f'Invalid value for {field}'},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                setattr(sale, field, new_value)
                updated_fields.append({
                    'field': field,
                    'old_value': old_value,
                    'new_value': new_value
                })

        if not updated_fields:
            return Response(
                {'error': 'No valid fields to update'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Recalculate final amount if tax or discount changed
        if any(f['field'] in ['tax_amount', 'discount_amount'] for f in updated_fields):
            sale.final_amount = sale.total_amount + sale.tax_amount - sale.discount_amount
            updated_fields.append({
                'field': 'final_amount',
                'old_value': 'auto-calculated',
                'new_value': sale.final_amount
            })

        # Set edit tracking fields if edit_reason is provided
        if 'edit_reason' in request.data and request.data['edit_reason'].strip():
            sale.edited_by = request.user.userprofile
            sale.edited_at = timezone.now()
            updated_fields.append({
                'field': 'edited_by',
                'old_value': sale.edited_by.user.username if sale.edited_by else None,
                'new_value': request.user.username
            })
            updated_fields.append({
                'field': 'edited_at',
                'old_value': sale.edited_at,
                'new_value': sale.edited_at
            })

        # Store old final amount for shift total adjustment
        old_final_amount = float(sale.final_amount)

        sale.save()

        # Update shift totals if final amount changed
        new_final_amount = float(sale.final_amount)
        if new_final_amount != old_final_amount:
            amount_diff = new_final_amount - old_final_amount
            if sale.shift:
                # Get payment method from payment record
                payment = sale.payment_set.first()
                payment_method = payment.payment_type if payment else 'cash'

                # Update shift totals based on payment method
                if payment_method == 'cash':
                    sale.shift.cash_sales = F('cash_sales') + amount_diff
                    sale.shift.save(update_fields=['cash_sales'])
                elif payment_method == 'card':
                    sale.shift.card_sales = F('card_sales') + amount_diff
                    sale.shift.save(update_fields=['card_sales'])
                elif payment_method in ['mpesa', 'mobile']:
                    sale.shift.mobile_sales = F('mobile_sales') + amount_diff
                    sale.shift.save(update_fields=['mobile_sales'])

                # Update total sales
                sale.shift.total_sales = F('total_sales') + amount_diff
                sale.shift.save(update_fields=['total_sales'])

        # Log admin edit operation
        audit_service.log_sale_operation(
            user=request.user.userprofile,
            operation='sale_edit',
            sale=sale,
            description=f'Admin edited sale {sale.receipt_number}: {sale.edit_reason or "No reason provided"}',
            old_values={f['field']: f['old_value'] for f in updated_fields},
            new_values={f['field']: f['new_value'] for f in updated_fields},
            request=request
        )

        return Response({
            'message': 'Sale updated successfully',
            'sale_id': sale.id,
            'updated_fields': updated_fields,
            'updated_by': request.user.username
        })

    @action(detail=False, methods=['get'], permission_classes=[])
    def sales_by_date(self, request):
        """View all sales by date (Admin/Manager only)"""
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.role not in ['admin', 'manager']:
            return Response(
                {'error': 'Admin or Manager role required'},
                status=status.HTTP_403_FORBIDDEN
            )

        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        status_filter = request.query_params.get('status')  # completed, voided, held

        queryset = Sale.objects.select_related('customer', 'shift__cashier__user')

        # Apply branch filter for managers
        if request.user.userprofile.role == 'manager' and request.user.userprofile.branch:
            queryset = queryset.filter(shift__cashier__branch=request.user.userprofile.branch)

        # Date filters
        if date_from:
            queryset = queryset.filter(sale_date__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(sale_date__date__lte=date_to)

        # Status filter
        if status_filter:
            if status_filter == 'voided':
                queryset = queryset.filter(voided=True)
            elif status_filter == 'held':
                queryset = queryset.filter(cart__status='held')
            elif status_filter == 'completed':
                queryset = queryset.filter(voided=False, cart__status='closed')

        # Group by date
        sales_by_date = {}
        for sale in queryset.order_by('-sale_date'):
            date_key = sale.sale_date.date().isoformat()
            if date_key not in sales_by_date:
                sales_by_date[date_key] = {
                    'date': date_key,
                    'total_sales': 0,
                    'total_amount': 0,
                    'voided_count': 0,
                    'completed_count': 0,
                    'sales': []
                }

            sales_by_date[date_key]['total_sales'] += 1
            sales_by_date[date_key]['total_amount'] += float(sale.final_amount)

            if sale.voided:
                sales_by_date[date_key]['voided_count'] += 1
            else:
                sales_by_date[date_key]['completed_count'] += 1

            sales_by_date[date_key]['sales'].append({
                'id': sale.id,
                'receipt_number': sale.receipt_number,
                'customer': sale.customer.name if sale.customer else None,
                'cashier': sale.shift.cashier.user.username if sale.shift and sale.shift.cashier else None,
                'final_amount': sale.final_amount,
                'voided': sale.voided,
                'sale_date': sale.sale_date,
                'item_count': sale.saleitem_set.count()
            })

        return Response({
            'sales_by_date': sales_by_date,
            'total_dates': len(sales_by_date),
            'filters': {
                'date_from': date_from,
                'date_to': date_to,
                'status': status_filter
            }
        })

    @action(detail=False, methods=['get'], permission_classes=[])
    def held_orders_admin(self, request):
        """View all held orders for admin/manager review"""
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.role not in ['admin', 'manager']:
            return Response(
                {'error': 'Admin or Manager role required'},
                status=status.HTTP_403_FORBIDDEN
            )

        queryset = Cart.objects.filter(status='held').select_related('customer', 'cashier__user')

        # Branch filter for managers
        if request.user.userprofile.role == 'manager' and request.user.userprofile.branch:
            queryset = queryset.filter(cashier__branch=request.user.userprofile.branch)

        held_orders = []
        for cart in queryset.order_by('-created_at'):
            items = cart.cartitem_set.select_related('product')
            held_orders.append({
                'id': cart.id,
                'customer': cart.customer.name if cart.customer else None,
                'cashier': cart.cashier.user.username if cart.cashier else None,
                'created_at': cart.created_at,
                'item_count': items.count(),
                'total_quantity': sum(item.quantity for item in items),
                'estimated_total': sum(float(item.unit_price) * item.quantity for item in items),
                'items': [{
                    'product': item.product.name,
                    'quantity': item.quantity,
                    'unit_price': item.unit_price,
                    'total': float(item.unit_price) * item.quantity
                } for item in items]
            })

        return Response({
            'held_orders': held_orders,
            'total_count': len(held_orders)
        })

    @action(detail=False, methods=['get'], permission_classes=[])
    def voided_orders(self, request):
        """View all voided sales and orders (Admin/Manager only)"""
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.role not in ['admin', 'manager']:
            return Response(
                {'error': 'Admin or Manager role required'},
                status=status.HTTP_403_FORBIDDEN
            )

        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        # Voided sales
        voided_sales_queryset = Sale.objects.filter(voided=True).select_related('customer', 'shift__cashier__user', 'voided_by__user')

        # Branch filter for managers
        if request.user.userprofile.role == 'manager' and request.user.userprofile.branch:
            voided_sales_queryset = voided_sales_queryset.filter(shift__cashier__branch=request.user.userprofile.branch)

        # Date filters
        if date_from:
            voided_sales_queryset = voided_sales_queryset.filter(sale_date__date__gte=date_from)
        if date_to:
            voided_sales_queryset = voided_sales_queryset.filter(sale_date__date__lte=date_to)

        voided_sales = []
        for sale in voided_sales_queryset.order_by('-voided_at'):
            items = sale.saleitem_set.select_related('product')
            voided_sales.append({
                'id': sale.id,
                'type': 'sale',
                'receipt_number': sale.receipt_number,
                'customer': sale.customer.name if sale.customer else None,
                'cashier': sale.shift.cashier.user.username if sale.shift and sale.shift.cashier else None,
                'void_reason': sale.void_reason,
                'voided_by': sale.voided_by.user.username if sale.voided_by else None,
                'voided_at': sale.voided_at,
                'original_amount': sale.final_amount,
                'item_count': items.count(),
                'items': [{
                    'product': item.product.name,
                    'quantity': item.quantity,
                    'unit_price': item.unit_price
                } for item in items]
            })

        # Voided carts (held orders that were voided)
        voided_carts_queryset = Cart.objects.filter(status='voided').select_related('customer', 'cashier__user')

        if request.user.userprofile.role == 'manager' and request.user.userprofile.branch:
            voided_carts_queryset = voided_carts_queryset.filter(cashier__branch=request.user.userprofile.branch)

        voided_carts = []
        for cart in voided_carts_queryset.order_by('-created_at'):
            items = cart.cartitem_set.select_related('product')
            voided_carts.append({
                'id': cart.id,
                'type': 'cart',
                'customer': cart.customer.name if cart.customer else None,
                'cashier': cart.cashier.user.username if cart.cashier else None,
                'void_reason': cart.void_reason,
                'voided_at': cart.created_at,  # No specific void timestamp for carts
                'estimated_amount': sum(float(item.unit_price) * item.quantity for item in items),
                'item_count': items.count(),
                'items': [{
                    'product': item.product.name,
                    'quantity': item.quantity,
                    'unit_price': item.unit_price
                } for item in items]
            })

        return Response({
            'voided_sales': voided_sales,
            'voided_carts': voided_carts,
            'total_voided': len(voided_sales) + len(voided_carts),
            'filters': {
                'date_from': date_from,
                'date_to': date_to
            }
        })

    @action(detail=True, methods=['get'], permission_classes=[])
    def transaction_details(self, request, pk=None):
        """Get detailed transaction information including all items (Admin/Manager only)"""
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.role not in ['admin', 'manager']:
            return Response(
                {'error': 'Admin or Manager role required'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            sale = Sale.objects.select_related('customer', 'shift__cashier__user', 'cart').get(id=pk)
        except Sale.DoesNotExist:
            return Response(
                {'error': 'Sale not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check branch access for managers
        if (request.user.userprofile.role == 'manager' and request.user.userprofile.branch and
            sale.shift and sale.shift.cashier and sale.shift.cashier.branch != request.user.userprofile.branch):
            return Response(
                {'error': 'Access denied - sale from different branch'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get sale items with product details
        items = sale.saleitem_set.select_related('product').order_by('product__name')

        # Get payment details
        payments = sale.payment_set.select_related('sale').order_by('created_at')

        # Get audit logs for this sale
        audit_logs = AuditLog.objects.filter(
            entity_type='Sale',
            entity_id=sale.id
        ).select_related('user__user').order_by('-timestamp')[:10]  # Last 10 operations

        transaction_data = {
            'sale': {
                'id': sale.id,
                'receipt_number': sale.receipt_number,
                'sale_date': sale.sale_date,
                'customer': sale.customer.name if sale.customer else None,
                'cashier': sale.shift.cashier.user.username if sale.shift and sale.shift.cashier else None,
                'sale_type': sale.sale_type,
                'voided': sale.voided,
                'void_reason': sale.void_reason,
                'voided_by': sale.voided_by.user.username if sale.voided_by else None,
                'voided_at': sale.voided_at,
            },
            'financials': {
                'subtotal': sale.total_amount,
                'tax_amount': sale.tax_amount,
                'discount_amount': sale.discount_amount,
                'final_amount': sale.final_amount,
            },
            'items': [{
                'id': item.id,
                'product': item.product.name,
                'product_id': item.product.id,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'discount': item.discount,
                'line_total': (item.unit_price * item.quantity) - item.discount
            } for item in items],
            'payments': [{
                'id': payment.id,
                'payment_type': payment.payment_type,
                'amount': payment.amount,
                'status': payment.status,
                'mpesa_number': payment.mpesa_number,
                'created_at': payment.created_at
            } for payment in payments],
            'audit_trail': [{
                'id': log.id,
                'operation': log.operation,
                'description': log.description,
                'user': log.user.user.username if log.user else 'System',
                'timestamp': log.timestamp,
                'old_values': log.old_values,
                'new_values': log.new_values
            } for log in audit_logs]
        }

        return Response(transaction_data)

    @action(detail=True, methods=['patch'], permission_classes=[])
    def edit_transaction(self, request, pk=None):
        """Edit entire transaction including items (Admin/Manager only)"""
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.role not in ['admin', 'manager']:
            return Response(
                {'error': 'Admin or Manager role required'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            sale = Sale.objects.select_related('cart').get(id=pk)
        except Sale.DoesNotExist:
            return Response(
                {'error': 'Sale not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check branch access for managers
        if (request.user.userprofile.role == 'manager' and request.user.userprofile.branch and
            sale.shift and sale.shift.cashier and sale.shift.cashier.branch != request.user.userprofile.branch):
            return Response(
                {'error': 'Access denied - sale from different branch'},
                status=status.HTTP_403_FORBIDDEN
            )

        if sale.voided:
            return Response(
                {'error': 'Cannot edit voided sales'},
                status=status.HTTP_400_BAD_REQUEST
            )

        updated_fields = []
        old_sale_data = {
            'total_amount': sale.total_amount,
            'tax_amount': sale.tax_amount,
            'discount_amount': sale.discount_amount,
            'final_amount': sale.final_amount,
            'receipt_number': sale.receipt_number
        }

        # Update sale header fields
        sale_fields = ['tax_amount', 'discount_amount', 'receipt_number']
        for field in sale_fields:
            if field in request.data:
                old_value = getattr(sale, field)
                new_value = request.data[field]

                if field in ['tax_amount', 'discount_amount']:
                    try:
                        new_value = float(new_value)
                        if new_value < 0:
                            return Response(
                                {'error': f'{field} cannot be negative'},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                    except (ValueError, TypeError):
                        return Response(
                            {'error': f'Invalid value for {field}'},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                setattr(sale, field, new_value)
                updated_fields.append({
                    'field': field,
                    'old_value': old_value,
                    'new_value': new_value
                })

        # Recalculate final amount
        sale.final_amount = sale.total_amount + sale.tax_amount - sale.discount_amount
        updated_fields.append({
            'field': 'final_amount',
            'old_value': old_sale_data['final_amount'],
            'new_value': sale.final_amount
        })

        # Handle item updates if provided
        if 'items' in request.data:
            items_data = request.data['items']
            existing_items = {item.id: item for item in sale.saleitem_set.all()}

            for item_data in items_data:
                item_id = item_data.get('id')
                if item_id and item_id in existing_items:
                    # Update existing item
                    item = existing_items[item_id]
                    old_item_data = {
                        'quantity': item.quantity,
                        'unit_price': item.unit_price,
                        'discount': item.discount
                    }

                    item.quantity = item_data.get('quantity', item.quantity)
                    item.unit_price = item_data.get('unit_price', item.unit_price)
                    item.discount = item_data.get('discount', item.discount)
                    item.save()

                    updated_fields.append({
                        'field': f'item_{item_id}',
                        'old_value': old_item_data,
                        'new_value': {
                            'quantity': item.quantity,
                            'unit_price': item.unit_price,
                            'discount': item.discount
                        }
                    })

            # Recalculate sale totals based on items
            items = sale.saleitem_set.all()
            sale.total_amount = sum(float(item.unit_price) * item.quantity for item in items)
            sale.final_amount = sale.total_amount + sale.tax_amount - sale.discount_amount

        sale.save()

        # Log the comprehensive edit
        audit_service.log_sale_operation(
            user=request.user.userprofile,
            operation='admin_action',
            sale=sale,
            description=f'Comprehensive transaction edit by {request.user.userprofile.role}',
            old_values=old_sale_data,
            new_values={
                'total_amount': sale.total_amount,
                'tax_amount': sale.tax_amount,
                'discount_amount': sale.discount_amount,
                'final_amount': sale.final_amount,
                'receipt_number': sale.receipt_number
            },
            request=request
        )

        return Response({
            'message': 'Transaction updated successfully',
            'sale_id': sale.id,
            'updated_fields': updated_fields,
            'new_totals': {
                'total_amount': sale.total_amount,
                'tax_amount': sale.tax_amount,
                'discount_amount': sale.discount_amount,
                'final_amount': sale.final_amount
            },
            'updated_by': request.user.username
        })

    @action(detail=True, methods=['post'], permission_classes=[])
    def void_transaction(self, request, pk=None):
        """Void entire transaction and restock all items (Admin/Manager only)"""
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.role not in ['admin', 'manager']:
            return Response(
                {'error': 'Admin or Manager role required'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            sale = Sale.objects.get(id=pk)
        except Sale.DoesNotExist:
            return Response(
                {'error': 'Sale not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check branch access for managers
        if (request.user.userprofile.role == 'manager' and request.user.userprofile.branch and
            sale.shift and sale.shift.cashier and sale.shift.cashier.branch != request.user.userprofile.branch):
            return Response(
                {'error': 'Access denied - sale from different branch'},
                status=status.HTTP_403_FORBIDDEN
            )

        if sale.voided:
            return Response(
                {'error': 'Sale is already voided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        void_reason = request.data.get('reason', '').strip()
        if not void_reason:
            return Response(
                {'error': 'Void reason is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                # Mark sale as voided
                sales_service.void_sale(sale, void_reason, request.user)

                # Restock all items
                try:
                    stock_service.restore_stock(sale, request.user, request)
                except ValueError as e:
                    return Response(
                        {'error': f'Stock restoration failed: {str(e)}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Update shift totals (subtract the voided sale)
                payment_service.update_shift_totals_on_void(sale.shift, sale)

                # Log comprehensive void operation
                audit_service.log_sale_operation(
                    user=request.user.userprofile,
                    operation='sale_void',
                    sale=sale,
                    description=f'Complete transaction void by {request.user.userprofile.role}: {void_reason}',
                    request=request
                )

                return Response({
                    'message': 'Transaction voided successfully - all items restocked',
                    'sale_id': sale.id,
                    'void_reason': void_reason,
                    'items_restocked': sale.saleitem_set.count(),
                    'amount_refunded': sale.final_amount,
                    'voided_by': request.user.username
                }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error voiding transaction: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({
                'error': 'Failed to void transaction',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, *args, **kwargs):
        """
        Custom create method to handle sale creation from frontend cart data
        """
        try:
            with transaction.atomic():
                # Check if this is a hold order request
                is_hold_order = request.data.get('hold_order', False)

                # Get items from request (frontend cart data)
                items_data = request.data.get('items', [])
                print(f"Received items data: {items_data}")
                print(f"Request data types: {[type(item.get('unit_price')) for item in items_data]}")
                if not items_data:
                    return Response(
                        {'error': 'No items provided'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Get cashier from authenticated user (required for shift validation)
                cashier = None
                if hasattr(request.user, 'userprofile'):
                    cashier = request.user.userprofile

                # Require active shift for all sales
                if not cashier:
                    return Response(
                        {'error': 'User profile not found. Please contact administrator.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                try:
                    current_shift = Shift.objects.get(cashier=cashier, status='open')
                except Shift.DoesNotExist:
                    return Response(
                        {'error': 'No active shift found. Please start a shift before processing sales.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Create cart first
                cart_status = 'held' if is_hold_order else 'closed'
                cart = Cart.objects.create(
                    cashier=cashier,
                    status=cart_status
                )

                # Create cart items from frontend data
                cart_items = []
                for item_data in items_data:
                    try:
                        print(f"Processing item: {item_data}")
                        print(f"Item types - product: {type(item_data.get('product'))}, quantity: {type(item_data.get('quantity'))}, unit_price: {type(item_data.get('unit_price'))}")

                        cart_item = CartItem.objects.create(
                            cart=cart,
                            product_id=item_data.get('product'),
                            quantity=int(item_data.get('quantity', 1)),
                            unit_price=float(item_data.get('unit_price', 0)),
                            discount=float(item_data.get('discount', 0))
                        )
                        cart_items.append(cart_item)
                    except Exception as item_error:
                        print(f"Error creating cart item: {str(item_error)}")
                        print(f"Item data: {item_data}")
                        return Response(
                            {'error': f'Error creating cart item for product {item_data.get("product")}: {str(item_error)}'},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                # Get sale type and apply wholesale business rules
                sale_type = request.data.get('sale_type', 'retail')

                # Get customer if provided (needed for wholesale validation)
                customer_id = request.data.get('customer')

                # Validate stock availability
                try:
                    stock_deductions = stock_service.validate_stock_availability(cart_items)
                except ValueError as e:
                    return Response(
                        {'error': str(e)},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Calculate totals (ensure numeric types)
                print(f"Cart items for calculation: {[(item.unit_price, type(item.unit_price), item.quantity, type(item.quantity)) for item in cart_items]}")
                subtotal = sum(float(item.unit_price) * int(item.quantity) for item in cart_items)
                tax_amount = float(request.data.get('tax_amount', 0))
                discount_amount = float(request.data.get('discount_amount', 0))
                total_amount = float(request.data.get('total_amount', subtotal + tax_amount - discount_amount))
                print(f"Calculated amounts - subtotal: {subtotal}, total: {total_amount}")
                receipt_number = request.data.get('receipt_number', f'POS-{timezone.now().strftime("%Y%m%d%H%M%S")}')

                # Get customer if provided
                customer = None
                if customer_id:
                    from customers.models import Customer
                    try:
                        customer = Customer.objects.get(id=customer_id, is_active=True)
                        cart.customer = customer
                        cart.save()
                    except Customer.DoesNotExist:
                        return Response(
                            {'error': 'Customer not found or inactive'},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                # If this is a hold order, don't create sale or deduct stock
                if is_hold_order:
                    # Serialize and return the cart
                    cart_serializer = CartSerializer(cart)
                    return Response(cart_serializer.data, status=status.HTTP_201_CREATED)

                # Create sale
                sale = sales_service.create_sale_from_cart(cart, request.data, cashier, current_shift)

                # Update shift totals
                payment_method = request.data.get('payment_method', 'cash').lower()
                payment_service.update_shift_totals(current_shift, payment_method, total_amount, request.data.get('split_data'))

                # Deduct stock
                try:
                    stock_service.deduct_stock(stock_deductions, sale, cashier)
                except ValueError as e:
                    return Response(
                        {'error': str(e)},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Validate and create payment
                payment_method = request.data.get('payment_method', '').strip().lower()
                if not payment_method:
                    return Response(
                        {'error': 'Payment method is required for all transactions'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                try:
                    payment_service.validate_payment_method(payment_method, request.data.get('split_data'))
                    created_payments = payment_service.create_payment(sale, payment_method, total_amount, request.data)
                except ValueError as e:
                    return Response(
                        {'error': str(e)},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Serialize and return the sale
                serializer = self.get_serializer(sale)
                return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(f"Error creating sale: {str(e)}")
            import traceback
            traceback.print_exc()

            # Provide user-friendly error messages
            error_message = str(e)
            if 'stock' in error_message.lower():
                user_error = '❌ Insufficient Stock'
                user_message = 'One or more items in your cart are out of stock.'
                user_details = 'Please remove out-of-stock items or check inventory levels.'
            elif 'credit' in error_message.lower():
                user_error = '❌ Credit Limit Exceeded'
                user_message = 'The customer has exceeded their credit limit.'
                user_details = 'Please choose a different payment method or contact the customer.'
            elif 'split payment requires' in error_message.lower():
                user_error = '❌ Payment Error'
                user_message = 'Split payment requires cash and/or M-Pesa amounts.'
                user_details = 'Please enter valid amounts for both payment methods or choose a single payment method.'
            else:
                user_error = '❌ Sale Error'
                user_message = 'An unexpected error occurred while processing the sale.'
                user_details = 'Please try again or contact your administrator.'

            return Response({
                'error': user_error,
                'message': user_message,
                'details': user_details,
                'technical_error': error_message if settings.DEBUG else None
            }, status=status.HTTP_400_BAD_REQUEST)

class SaleItemViewSet(viewsets.ModelViewSet):
    queryset = SaleItem.objects.all()
    serializer_class = SaleItemSerializer

class ReturnViewSet(viewsets.ModelViewSet):
    queryset = Return.objects.all()
    serializer_class = ReturnSerializer

class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['customer', 'status', 'sale']
    search_fields = ['invoice_number', 'customer__name', 'notes']
    ordering_fields = ['invoice_date', 'due_date', 'total_amount', 'created_at']
    ordering = ['-invoice_date']

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        """Mark invoice as paid"""
        invoice = self.get_object()
        invoice.status = 'paid'
        invoice.save()
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def send_invoice(self, request, pk=None):
        """Mark invoice as sent"""
        invoice = self.get_object()
        invoice.status = 'sent'
        invoice.save()
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def generate_from_sale(self, request):
        """Generate invoice from an existing sale"""
        sale_id = request.data.get('sale_id')
        customer_id = request.data.get('customer_id')
        due_date = request.data.get('due_date')

        try:
            sale = Sale.objects.get(id=sale_id)
        except Sale.DoesNotExist:
            return Response({'error': 'Sale not found'}, status=status.HTTP_404_NOT_FOUND)

        # Check if invoice already exists for this sale
        if hasattr(sale, 'invoice'):
            return Response({'error': 'Invoice already exists for this sale'}, status=status.HTTP_400_BAD_REQUEST)

        # Get customer (from sale or specified)
        customer = sale.customer
        if customer_id:
            from customers.models import Customer
            try:
                customer = Customer.objects.get(id=customer_id)
            except Customer.DoesNotExist:
                return Response({'error': 'Customer not found'}, status=status.HTTP_404_NOT_FOUND)

        if not customer:
            return Response({'error': 'No customer associated with sale'}, status=status.HTTP_400_BAD_REQUEST)

        # Create invoice
        invoice = Invoice.objects.create(
            sale=sale,
            customer=customer,
            due_date=due_date or (timezone.now().date() + timezone.timedelta(days=30)),
            subtotal=sale.total_amount,
            total_amount=sale.final_amount,
            status='sent',
            notes=f'Invoice generated from sale {sale.receipt_number}'
        )

        # Create invoice items from sale items
        for sale_item in sale.saleitem_set.all():
            InvoiceItem.objects.create(
                invoice=invoice,
                product=sale_item.product,
                description=sale_item.product.name,
                quantity=sale_item.quantity,
                unit_price=sale_item.unit_price,
                tax_rate=0,  # Could be enhanced to include tax
                discount_amount=sale_item.discount
            )

        serializer = self.get_serializer(invoice)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class InvoiceItemViewSet(viewsets.ModelViewSet):
    queryset = InvoiceItem.objects.all()
    serializer_class = InvoiceItemSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['invoice', 'product']
    search_fields = ['description', 'product__name']
    ordering_fields = ['quantity', 'unit_price']
    ordering = ['description']


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset for audit logs (admin/manager only)"""
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['operation', 'user', 'entity_type']
    search_fields = ['description', 'user__user__username']
    ordering_fields = ['timestamp', 'operation']
    ordering = ['-timestamp']

    def get_queryset(self):
        """Filter audit logs based on user permissions"""
        queryset = super().get_queryset()

        # Only admin and manager can view audit logs
        if not hasattr(self.request.user, 'userprofile'):
            return queryset.none()

        user_profile = self.request.user.userprofile
        if user_profile.role not in ['admin', 'manager']:
            return queryset.none()

        # Managers can only see logs from their branch
        if user_profile.role == 'manager' and user_profile.branch:
            queryset = queryset.filter(
                Q(user__branch=user_profile.branch) |
                Q(user__isnull=True)  # System operations
            )

        return queryset

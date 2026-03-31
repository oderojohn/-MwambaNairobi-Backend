from rest_framework import viewsets, generics, status, serializers
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Prefetch
import logging
logger = logging.getLogger(__name__)
from .models import Shift
from .serializers import ShiftSerializer
from sales.models import Sale
from users.audit import log_user_activity

class ShiftViewSet(viewsets.ModelViewSet):
    queryset = Shift.objects.prefetch_related(
        Prefetch('sale_set', queryset=Sale.objects.select_related('customer'))
    ).select_related('cashier', 'cashier__user', 'approved_by')
    serializer_class = ShiftSerializer
    pagination_class = PageNumberPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['cashier', 'status', 'start_time', 'end_time']
    search_fields = ['cashier__user__username', 'cashier__user__first_name', 'cashier__user__last_name']
    ordering_fields = ['start_time', 'end_time', 'total_sales', 'transaction_count']
    ordering = ['-start_time']
    
    def list(self, request, *args, **kwargs):
        # Check if limit is provided and bypass pagination
        limit = request.query_params.get('limit')
        if limit:
            try:
                queryset = self.filter_queryset(self.get_queryset())
                # Apply limit directly
                page = queryset[:int(limit)]
                serializer = self.get_serializer(page, many=True)
                return Response(serializer.data)
            except ValueError:
                pass
        # Default behavior
        return super().list(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by user_id if provided - ensure data isolation between users
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(cashier__user_id=user_id)
        
        # Filter by date range if provided
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        # Accept shorthand start/end to align with frontend filters
        start_fallback = self.request.query_params.get('start')
        end_fallback = self.request.query_params.get('end')
        start_date = start_date or start_fallback
        end_date = end_date or end_fallback
        
        if start_date:
            queryset = queryset.filter(start_time__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(start_time__date__lte=end_date)
            
        return queryset


class CurrentShiftView(generics.RetrieveAPIView):
    """Get the current active shift for the authenticated cashier"""
    serializer_class = ShiftSerializer
    permission_classes = []
    
    def get_object(self):
        # Get the user ID from request - user_id is REQUIRED
        user_id = self.request.query_params.get('user_id') or \
                  self.request.data.get('user_id')
        
        if not user_id:
            # Return no shift if user_id is not provided
            return None
        
        # Look for active shift for this specific user
        from users.models import UserProfile
        from django.contrib.auth.models import User
        
        profile = None
        try:
            # First try to get UserProfile by ID (userprofile.id)
            profile = UserProfile.objects.get(id=user_id)
        except (UserProfile.DoesNotExist, ValueError):
            try:
                # Fallback: try to get UserProfile by user_id (Django User ID)
                user = User.objects.get(id=user_id)
                profile = user.userprofile
            except (User.DoesNotExist, UserProfile.DoesNotExist, AttributeError):
                pass
        
        if not profile:
            return None
        
        shift = Shift.objects.filter(
            cashier=profile,
            status='open'
        ).first()
        
        if shift:
            return shift
        
        # No active shift for this user - return None (don't return last closed shift)
        logger.info(f"No active shift for user_id: {user_id}")
        return None
    
    def retrieve(self, request, *args, **kwargs):
        """Override retrieve to handle None case properly"""
        instance = self.get_object()
        
        if instance is None:
            # No active shift - check for last closed shift
            user_id = request.query_params.get('user_id')
            last_shift_info = None
            
            if user_id:
                from users.models import UserProfile
                from django.contrib.auth.models import User
                
                profile = None
                try:
                    profile = UserProfile.objects.get(id=user_id)
                except (UserProfile.DoesNotExist, ValueError):
                    try:
                        user = User.objects.get(id=user_id)
                        profile = user.userprofile
                    except (User.DoesNotExist, UserProfile.DoesNotExist, AttributeError):
                        pass
                
                if profile:
                    last_shift = Shift.objects.filter(
                        cashier=profile,
                        status='closed'
                    ).order_by('-end_time').first()
                    
                    if last_shift:
                        last_shift_info = {
                            'id': last_shift.id,
                            'end_time': last_shift.end_time,
                            'closing_balance': float(last_shift.closing_balance or 0),
                            'total_sales': float(last_shift.total_sales or 0),
                            'discrepancy': float(last_shift.discrepancy or 0),
                            'status': last_shift.status
                        }
            
            return Response({
                'has_active_shift': False,
                'status': 'closed',
                'last_shift_info': last_shift_info
            })
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class StartShiftView(generics.CreateAPIView):
    """Start a new shift"""
    serializer_class = ShiftSerializer
    from rest_framework.permissions import IsAuthenticated
    permission_classes = [IsAuthenticated]
    
    def create(self, request, *args, **kwargs):
        logger.info(f"[StartShift] Request user: {request.user}")
        logger.info(f"[StartShift] Request data: {request.data}")
        logger.info(f"[StartShift] Is authenticated: {request.user.is_authenticated}")
        
        # Accept both 'opening_balance' and 'starting_cash' for flexibility
        opening_balance = request.data.get('opening_balance') or request.data.get('starting_cash', 0)
        
        # Get user from authenticated request - create profile if missing
        try:
            profile = request.user.userprofile
            logger.info(f"[StartShift] Found profile: {profile.id}")
        except Exception as e:
            logger.warning(f"[StartShift] Profile not found, creating one: {e}")
            # Create missing UserProfile
            from users.models import UserProfile
            profile = UserProfile.objects.create(
                user=request.user,
                role='cashier',
                is_active=True
            )
            logger.info(f"[StartShift] Created profile: {profile.id}")
        
        # Check for existing active shift
        existing_shift = Shift.objects.filter(
            cashier=profile,
            status='open'
        ).first()
        
        if existing_shift:
            return Response(
                {'error': 'You already have an active shift', 'shift_id': existing_shift.id},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create new shift
        shift = Shift.objects.create(
            cashier=profile,
            opening_balance=opening_balance,
            start_time=timezone.now(),
            status='open'
        )
        
        logger.info(f"[StartShift] Created shift: {shift.id}")
        log_user_activity(
            action='shift_started',
            user=request.user,
            request=request,
            status_code=status.HTTP_201_CREATED,
            metadata={
                'shift_id': shift.id,
                'opening_balance': float(opening_balance or 0),
            },
        )
        return Response(
            ShiftSerializer(shift).data,
            status=status.HTTP_201_CREATED
        )


class EndShiftView(generics.GenericAPIView):
    """End the current shift"""
    serializer_class = ShiftSerializer
    permission_classes = []
    
    def get_queryset(self):
        return Shift.objects.filter(status='open').exclude(status__isnull=True)
    
    def get_object(self):
        """Get the active shift - either from shift_id param or find the active one"""
        shift_id = self.request.data.get('shift_id') or self.request.query_params.get('shift_id')
        
        if shift_id:
            try:
                shift = Shift.objects.get(id=shift_id, status='open')
                logger.error(f"Active shift found by shift_id: {shift.id}")
                return shift
            except Shift.DoesNotExist:
                # Check if shift exists but is closed
                try:
                    closed_shift = Shift.objects.get(id=shift_id, status='closed')
                    logger.error(f"Shift exists but is closed: {shift_id}")
                    return closed_shift
                except Shift.DoesNotExist:
                    logger.error(f"No shift found with shift_id: {shift_id}")
        
        # Fallback: get the first active shift for the user
        user_id = self.request.data.get('user_id') or self.request.query_params.get('user_id')
        if user_id:
            from users.models import UserProfile
            try:
                profile = UserProfile.objects.get(id=user_id)
                # First check for open shift
                shift = Shift.objects.get(cashier=profile, status='open')
                logger.error(f"Active shift found by user_id: {user_id}, shift_id: {shift.id}")
                return shift
            except Shift.DoesNotExist:
                # Check if user has any closed shifts
                from users.models import UserProfile
                try:
                    profile = UserProfile.objects.get(id=user_id)
                    closed_shift = Shift.objects.filter(cashier=profile, status='closed').order_by('-end_time').first()
                    if closed_shift:
                        logger.error(f"User has closed shifts, latest: {closed_shift.id}")
                        return closed_shift
                except (UserProfile.DoesNotExist, ValueError):
                    pass
                logger.error(f"No active shift found for user_id: {user_id}")
        
        # Final fallback: require user_id - do NOT return any shift
        logger.error(f"No active shift found - user_id required")
        return None
    
    def post(self, request, *args, **kwargs):
        """End a shift using POST"""
        logger.error(f"Shift data: {request.data}")
        
        instance = self.get_object()
        
        if not instance:
            logger.error("No active shift found")
            # Try to find any closed shift to return its status
            user_id = request.data.get('user_id') or request.query_params.get('user_id')
            if user_id:
                from users.models import UserProfile
                try:
                    profile = UserProfile.objects.get(id=user_id)
                    closed_shift = Shift.objects.filter(cashier=profile, status='closed').order_by('-end_time').first()
                    if closed_shift:
                        return Response(
                            {
                                'message': 'Shift is already closed',
                                'shift': ShiftSerializer(closed_shift).data,
                                'shift_status': 'closed'
                            },
                            status=status.HTTP_200_OK
                        )
                except (UserProfile.DoesNotExist, ValueError):
                    pass
            
            # Return proper error - require user_id to check for shifts
            return Response(
                {'error': 'No active shift found. Please start a shift first.', 'no_active_shift': True},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if shift is already closed
        if instance.status == 'closed':
            logger.error(f"Shift {instance.id} is already closed")
            return Response(
                {
                    'message': 'Shift is already closed',
                    'shift': ShiftSerializer(instance).data,
                    'shift_status': 'closed'
                },
                status=status.HTTP_200_OK
            )
        
        # Get cash count from request - accept both 'ending_cash' and 'actual_cash'
        # Note: we must check for None explicitly since 0 is a valid cash amount
        actual_cash = request.data.get('ending_cash')
        if actual_cash is None:
            actual_cash = request.data.get('actual_cash')
        
        # Calculate expected cash considering returns (cash refunds reduce expected cash)
        # Formula: expected = opening_balance + cash_sales - cash_returns
        total_returns = float(instance.total_returns) if instance.total_returns else 0
        expected_cash = float(instance.opening_balance) + float(instance.cash_sales) - total_returns
        
        # Calculate discrepancy: actual - expected
        # Positive = overage (more cash than expected)
        # Negative = shortage (less cash than expected)
        discrepancy = float(actual_cash) - expected_cash if actual_cash is not None else 0
        
        # Determine discrepancy type
        if discrepancy < 0:
            discrepancy_type = 'shortage'
            discrepancy_description = f'Shortage: KSh {abs(discrepancy):.2f}'
        elif discrepancy > 0:
            discrepancy_type = 'overage'
            discrepancy_description = f'Overage: KSh {abs(discrepancy):.2f}'
        else:
            discrepancy_type = 'balanced'
            discrepancy_description = 'Perfect balance'
        
        # Update shift
        instance.end_time = timezone.now()
        instance.closing_balance = actual_cash
        instance.discrepancy = discrepancy
        instance.status = 'closed'
        instance.save()
        
        # Build reconciliation response
        reconciliation = {
            'shift_id': instance.id,
            'shift_status': instance.status,
            'opening_balance': float(instance.opening_balance),
            'cash_sales': float(instance.cash_sales),
            'card_sales': float(instance.card_sales),
            'mobile_sales': float(instance.mobile_sales),
            'total_sales': float(instance.total_sales),
            'total_returns': float(total_returns),
            'expected_closing_balance': expected_cash,
            'actual_closing_balance': float(actual_cash) if actual_cash is not None else 0,
            'discrepancy': discrepancy,
            'discrepancy_type': discrepancy_type,
            'discrepancy_description': discrepancy_description,
            'end_time': instance.end_time.isoformat() if instance.end_time else None,
        }
        log_user_activity(
            action='shift_closed',
            user=request.user if getattr(request.user, 'is_authenticated', False) else None,
            request=request,
            status_code=status.HTTP_200_OK,
            metadata=reconciliation,
        )
        
        return Response(
            {
                'message': 'Shift ended successfully',
                'shift': ShiftSerializer(instance).data,
                'reconciliation': reconciliation,
                'shift_status': 'closed'
            },
            status=status.HTTP_200_OK
        )
    
    def put(self, request, *args, **kwargs):
        """End a shift using PUT (alias for POST)"""
        return self.post(request, *args, **kwargs)
    
    def patch(self, request, *args, **kwargs):
        """End a shift using PATCH (alias for POST)"""
        return self.post(request, *args, **kwargs)


class EndShiftTestView(generics.GenericAPIView):
    """Test endpoint to verify POST works"""
    serializer_class = ShiftSerializer
    permission_classes = []
    
    def post(self, request, *args, **kwargs):
        return Response({'message': 'POST to end-test works!', 'data': request.data})
    
    def get(self, request, *args, **kwargs):
        return Response({'message': 'GET to end-test works!'})


class AllShiftsView(generics.ListAPIView):
    """Get all shifts with optional filtering"""
    serializer_class = ShiftSerializer
    permission_classes = []
    pagination_class = PageNumberPagination
    
    def get_queryset(self):
        queryset = Shift.objects.prefetch_related(
            'sale_set__customer',
            'cashier__user'
        ).select_related(
            'cashier__user',
            'approved_by'
        ).order_by('-start_time')
        
        # Filter by user_id - ensure data isolation
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(cashier__user_id=user_id)

        username = self.request.query_params.get('user') or self.request.query_params.get('username')
        if username:
            queryset = queryset.filter(cashier__user__username__icontains=username)

        role_param = self.request.query_params.get('role')
        if role_param:
            queryset = queryset.filter(cashier__role=role_param)
        
        # Filter by cashier (UserProfile ID)
        cashier_id = self.request.query_params.get('cashier_id')
        if cashier_id:
            queryset = queryset.filter(cashier_id=cashier_id)
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        include_all_shifts = str(self.request.query_params.get('all_shifts', '')).lower() in ['1', 'true', 'yes']
        if status_param:
            queryset = queryset.filter(status=status_param)
        elif include_all_shifts:
            recent_closed_ids = list(
                queryset.filter(status='closed')
                .order_by('-start_time')
                .values_list('id', flat=True)[:5]
            )
            queryset = queryset.filter(
                Q(status='open') | Q(id__in=recent_closed_ids)
            )
        else:
            queryset = queryset.filter(status='open')
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            queryset = queryset.filter(start_time__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(start_time__date__lte=end_date)
        
        return queryset


class AdminShiftManagementView(generics.UpdateAPIView):
    """Admin endpoint to manage shifts"""
    serializer_class = ShiftSerializer
    permission_classes = []
    lookup_field = 'id'
    lookup_url_kwarg = 'shift_id'
    
    def get_queryset(self):
        return Shift.objects.all()
    
    def update(self, request, *args, **kwargs):
        action = kwargs.pop('action', None)
        instance = self.get_object()
        
        if action == 'reopen':
            # Reopen a closed shift
            instance.end_time = None
            instance.status = 'open'
            instance.save()
            return Response(ShiftSerializer(instance).data)
        
        elif action == 'force_close':
            # Force close an active shift
            instance.end_time = timezone.now()
            instance.status = 'closed'
            instance.save()
            return Response(ShiftSerializer(instance).data)
        
        return super().update(request, *args, **kwargs)

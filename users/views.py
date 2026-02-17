from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import (
    AllowAny,
    IsAdminUser,
    IsAuthenticated,
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import logout
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)

from .models import UserProfile
from .serializers import UserProfileSerializer


class UserProfileViewSet(viewsets.ModelViewSet):
    """
    Admin-only user profile management.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return UserProfile.objects.all()
        # If multi-tenant:
        # return UserProfile.objects.filter(tenant=self.request.user.tenant)


class LoginView(TokenObtainPairView):
    """
    Issues JWT access + refresh tokens and returns user roles and current shift.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            # Get user from login credentials since authentication_classes = []
            username = request.data.get('username')
            from django.contrib.auth import authenticate
            user = authenticate(username=username, password=request.data.get('password'))

            if user:
                groups = list(user.groups.values_list('name', flat=True))
                response.data["roles"] = groups  # Frontend expects array
                response.data["role"] = groups[0] if groups else None
                response.data["user_group"] = groups[0] if groups else None
                response.data["username"] = user.username  # Add username for display
                response.data["name"] = user.get_full_name() or user.username  # Add full name for display
                
                # Ensure UserProfile exists - create if missing
                if not hasattr(user, 'userprofile'):
                    from .models import UserProfile
                    UserProfile.objects.get_or_create(
                        user=user,
                        defaults={'role': 'cashier', 'is_active': True}
                    )
                    logger.info(f"Created missing UserProfile for user: {user.username}")
                
                if hasattr(user, 'userprofile'):
                    response.data["user_id"] = user.userprofile.id  # Add user_id for shift operations
                    response.data["branch"] = user.userprofile.branch.name if user.userprofile.branch else None
                    response.data["branch_id"] = user.userprofile.branch.id if user.userprofile.branch else None
                    
                    # Get current active shift for this user
                    from shifts.models import Shift
                    from shifts.serializers import ShiftSerializer
                    try:
                        logger.info(f"[DEBUG] Checking shift for user: {user.username} (userprofile id: {user.userprofile.id})")
                        
                        # Check for open shift
                        current_shift = Shift.objects.filter(
                            cashier=user.userprofile,
                            status='open'
                        ).first()
                        
                        if current_shift:
                            logger.info(f"[DEBUG] Found open shift: {current_shift.id}")
                            response.data["current_shift"] = ShiftSerializer(current_shift).data
                            response.data["shift_status"] = "open"
                        else:
                            logger.info(f"[DEBUG] No open shift found for user {user.username}")
                            # Check if there are any closed shifts
                            has_closed_shifts = Shift.objects.filter(
                                cashier=user.userprofile,
                                status='closed'
                            ).exists()
                            
                            if has_closed_shifts:
                                response.data["shift_status"] = "closed"
                            else:
                                response.data["shift_status"] = "none"
                            
                            response.data["current_shift"] = None
                    except Exception as e:
                        logger.error(f"[DEBUG] Error fetching shift: {str(e)}", exc_info=True)
                        response.data["current_shift"] = None
                        response.data["shift_status"] = "error"

        return response


class RefreshView(TokenRefreshView):
    """
    Refresh access token using refresh token.
    """
    permission_classes = [AllowAny]
    authentication_classes = []


class LogoutView(APIView):
    """
    Blacklists refresh token (secure logout).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return Response(
                {"error": "Refresh token required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            logout(request)

            return Response(
                {"message": "Successfully logged out"},
                status=status.HTTP_200_OK,
            )
        except Exception:
            return Response(
                {"error": "Invalid or expired token"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class RoleListView(APIView):
    """
    Returns system roles.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(
            [
                {"value": key, "label": label}
                for key, label in UserProfile.ROLE_CHOICES
            ]
        )


class CurrentUserView(APIView):
    """
    Returns the current authenticated user's profile information.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.userprofile
            from shifts.models import Shift
            from shifts.serializers import ShiftSerializer
            
            # Get current active shift
            current_shift = Shift.objects.filter(
                cashier=profile,
                status='open'
            ).first()
            
            return Response({
                'user_id': profile.id,
                'username': request.user.username,
                'email': request.user.email,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'role': profile.role,
                'branch': profile.branch.name if profile.branch else None,
                'branch_id': profile.branch.id if profile.branch else None,
                'current_shift': ShiftSerializer(current_shift).data if current_shift else None,
                'shift_status': 'open' if current_shift else 'closed'
            })
        except Exception as e:
            logger.error(f"Error getting current user: {str(e)}")
            return Response(
                {'error': 'User profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

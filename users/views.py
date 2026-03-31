import logging

from django.contrib.auth import logout
from django.contrib.auth.models import Group, User
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import TopBarPermission, UserProfile, default_topbar_permissions
from .serializers import GroupSerializer, TopBarPermissionSerializer, UserProfileSerializer

logger = logging.getLogger(__name__)


class IsAdminOrManager(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user = request.user
        if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
            return True
        profile = getattr(user, 'userprofile', None)
        return getattr(profile, 'role', None) in ['admin', 'manager']


class UserProfileViewSet(viewsets.ModelViewSet):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAdminOrManager]

    def get_queryset(self):
        return UserProfile.objects.select_related('user', 'branch').prefetch_related('user__groups').all()


class TopBarPermissionViewSet(viewsets.ModelViewSet):
    serializer_class = TopBarPermissionSerializer
    lookup_field = 'user_profile_id'
    lookup_value_regex = r'[^/]+'

    def get_permissions(self):
        if self.action in ['list', 'create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsAdminOrManager]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        qs = TopBarPermission.objects.select_related('user_profile', 'user_profile__user')
        user = self.request.user
        if user.is_staff:
            return qs
        if hasattr(user, 'userprofile'):
            return qs.filter(user_profile=user.userprofile)
        return qs.none()

    def retrieve(self, request, *args, **kwargs):
        user_profile_id = kwargs.get(self.lookup_field)
        permission_obj, _ = TopBarPermission.objects.get_or_create(
            user_profile_id=user_profile_id,
            defaults={'allowed_buttons': default_topbar_permissions()}
        )
        serializer = self.get_serializer(permission_obj)
        return Response(serializer.data)


class GroupListCreateView(APIView):
    permission_classes = [IsAdminOrManager]

    def get(self, request):
        return Response(GroupSerializer(Group.objects.order_by('name'), many=True).data)

    def post(self, request):
        serializer = GroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class GroupDetailView(APIView):
    permission_classes = [IsAdminOrManager]

    def patch(self, request, pk):
        try:
            group = Group.objects.get(pk=pk)
        except Group.DoesNotExist:
            return Response({'error': 'Group not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = GroupSerializer(group, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        try:
            group = Group.objects.get(pk=pk)
        except Group.DoesNotExist:
            return Response({'error': 'Group not found'}, status=status.HTTP_404_NOT_FOUND)

        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        pin = request.data.get('pin')

        if pin:
            return self.pin_login(request, pin, *args, **kwargs)

        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            username = request.data.get('username')
            from django.contrib.auth import authenticate
            user = authenticate(username=username, password=request.data.get('password'))

            if user:
                response = self.add_user_data(response, user)

        return response

    def pin_login(self, request, pin, *args, **kwargs):
        try:
            user_profile = UserProfile.objects.get(pin=pin, is_active=True)
            user = user_profile.user
        except (UserProfile.DoesNotExist, UserProfile.MultipleObjectsReturned):
            return Response({"error": "Invalid PIN"}, status=status.HTTP_400_BAD_REQUEST)

        if not user.is_active:
            return Response({"error": "User account is disabled"}, status=status.HTTP_400_BAD_REQUEST)

        refresh = RefreshToken.for_user(user)
        response = Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }, status=status.HTTP_200_OK)

        return self.add_user_data(response, user)

    def add_user_data(self, response, user):
        profile = getattr(user, 'userprofile', None)
        if not profile:
            profile, _ = UserProfile.objects.get_or_create(
                user=user,
                defaults={'role': 'cashier', 'is_active': True}
            )
            logger.info(f"Created missing UserProfile for user: {user.username}")

        role = profile.role if profile else None
        roles = [role] if role else []

        response.data["roles"] = roles
        response.data["role"] = role
        response.data["user_group"] = role
        response.data["username"] = user.username
        response.data["name"] = user.get_full_name() or user.username
        response.data["groups"] = list(user.groups.values('id', 'name'))
        response.data["is_staff"] = user.is_staff
        response.data["is_superuser"] = user.is_superuser

        if profile:
            response.data["user_id"] = profile.id
            response.data["branch"] = profile.branch.name if profile.branch else None
            response.data["branch_id"] = profile.branch.id if profile.branch else None
            try:
                permissions, _ = TopBarPermission.objects.get_or_create(
                    user_profile=profile,
                    defaults={'allowed_buttons': default_topbar_permissions()}
                )
                response.data["topbar_permissions"] = permissions.allowed_buttons
            except Exception as e:
                logger.error(f"[DEBUG] Error fetching top bar permissions: {str(e)}", exc_info=True)
                response.data["topbar_permissions"] = default_topbar_permissions()

            from shifts.models import Shift
            from shifts.serializers import ShiftSerializer
            try:
                logger.info(f"[DEBUG] Checking shift for user: {user.username} (userprofile id: {profile.id})")
                current_shift = Shift.objects.filter(cashier=profile, status='open').first()

                if current_shift:
                    logger.info(f"[DEBUG] Found open shift: {current_shift.id}")
                    response.data["current_shift"] = ShiftSerializer(current_shift).data
                    response.data["shift_status"] = "open"
                else:
                    logger.info(f"[DEBUG] No open shift found for user {user.username}")
                    has_closed_shifts = Shift.objects.filter(cashier=profile, status='closed').exists()
                    response.data["shift_status"] = "closed" if has_closed_shifts else "none"
                    response.data["current_shift"] = None
            except Exception as e:
                logger.error(f"[DEBUG] Error fetching shift: {str(e)}", exc_info=True)
                response.data["current_shift"] = None
                response.data["shift_status"] = "error"

        return response


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    authentication_classes = []


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return Response({"error": "Refresh token required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            logout(request)
            return Response({"message": "Successfully logged out"}, status=status.HTTP_200_OK)
        except Exception:
            return Response({"error": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)


class RoleListView(APIView):
    permission_classes = [IsAdminOrManager]

    def get(self, request):
        return Response([
            {"value": key, "label": label}
            for key, label in UserProfile.ROLE_CHOICES
        ])


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.userprofile
            from shifts.models import Shift
            from shifts.serializers import ShiftSerializer

            current_shift = Shift.objects.filter(cashier=profile, status='open').first()

            return Response({
                'user_id': profile.id,
                'username': request.user.username,
                'email': request.user.email,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'role': profile.role,
                'groups': list(request.user.groups.values('id', 'name')),
                'is_staff': request.user.is_staff,
                'is_superuser': request.user.is_superuser,
                'branch': profile.branch.name if profile.branch else None,
                'branch_id': profile.branch.id if profile.branch else None,
                'topbar_permissions': getattr(profile.topbar_permissions, 'allowed_buttons', default_topbar_permissions()),
                'current_shift': ShiftSerializer(current_shift).data if current_shift else None,
                'shift_status': 'open' if current_shift else 'closed'
            })
        except Exception as e:
            logger.error(f"Error getting current user: {str(e)}")
            return Response({'error': 'User profile not found'}, status=status.HTTP_404_NOT_FOUND)

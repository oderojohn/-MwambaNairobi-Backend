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
    Issues JWT access + refresh tokens and returns user roles.
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
                if hasattr(user, 'userprofile'):
                    response.data["branch"] = user.userprofile.branch.name if user.userprofile.branch else None
                    response.data["branch_id"] = user.userprofile.branch.id if user.userprofile.branch else None

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

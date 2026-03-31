from django.contrib.auth.models import Group, User
from rest_framework import serializers

from .models import TopBarPermission, UserProfile, default_topbar_permissions


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']


class UserSerializer(serializers.ModelSerializer):
    groups = GroupSerializer(many=True, read_only=True)
    group_ids = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        many=True,
        required=False,
        source='groups',
        write_only=True,
    )

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'password',
            'is_staff',
            'is_superuser',
            'groups',
            'group_ids',
        ]
        extra_kwargs = {
            'password': {'write_only': True, 'required': False},
            'username': {'validators': []},
            'email': {'validators': []},
            'is_staff': {'required': False},
            'is_superuser': {'required': False},
        }


class TopBarPermissionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user_profile.user.username', read_only=True)
    role = serializers.CharField(source='user_profile.role', read_only=True)

    class Meta:
        model = TopBarPermission
        fields = ['id', 'user_profile', 'username', 'role', 'allowed_buttons', 'updated_at']


class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    topbar_permissions = serializers.JSONField(required=False)

    class Meta:
        model = UserProfile
        fields = [
            'id', 'user', 'role', 'phone', 'branch', 'is_active', 'pin',
            'topbar_permissions'
        ]
        extra_kwargs = {
            'branch': {'required': False, 'allow_null': True},
            'phone': {'required': False, 'allow_blank': True},
            'pin': {'required': False, 'allow_null': True, 'allow_blank': True},
        }

    def _upsert_topbar(self, profile, allowed_buttons=None):
        allowed = allowed_buttons if allowed_buttons is not None else default_topbar_permissions()
        TopBarPermission.objects.update_or_create(
            user_profile=profile,
            defaults={'allowed_buttons': allowed}
        )

    def _sync_user_flags(self, user, role, is_staff=None, is_superuser=None):
        if role == 'admin':
            user.is_staff = True if is_staff is None else is_staff
            user.is_superuser = True if is_superuser is None else is_superuser
            return

        if is_staff is not None:
            user.is_staff = is_staff
        if is_superuser is not None:
            user.is_superuser = is_superuser

    def create(self, validated_data):
        user_data = validated_data.pop('user', {})
        topbar_data = validated_data.pop('topbar_permissions', None)

        password = user_data.pop('password', None)
        groups = user_data.pop('groups', [])
        is_staff = user_data.pop('is_staff', None)
        is_superuser = user_data.pop('is_superuser', None)
        role = validated_data.get('role', 'cashier')

        user = User(**user_data)
        if password:
          user.set_password(password)
        else:
          user.set_unusable_password()
        self._sync_user_flags(user, role, is_staff, is_superuser)
        user.save()

        if groups:
            user.groups.set(groups)

        profile = UserProfile.objects.create(user=user, **validated_data)
        self._upsert_topbar(profile, topbar_data)
        return profile

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', None)
        topbar_data = validated_data.pop('topbar_permissions', None)
        role = validated_data.get('role', instance.role)

        if user_data:
            password = user_data.pop('password', None)
            groups = user_data.pop('groups', None)
            is_staff = user_data.pop('is_staff', None)
            is_superuser = user_data.pop('is_superuser', None)

            for attr, value in user_data.items():
                if value is not None:
                    setattr(instance.user, attr, value)
            if password:
                instance.user.set_password(password)
            self._sync_user_flags(instance.user, role, is_staff, is_superuser)
            instance.user.save()

            if groups is not None:
                instance.user.groups.set(groups)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if topbar_data is not None:
            self._upsert_topbar(instance, topbar_data)

        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        try:
            data['topbar_permissions'] = getattr(
                instance.topbar_permissions, 'allowed_buttons', default_topbar_permissions()
            )
        except Exception:
            data['topbar_permissions'] = default_topbar_permissions()
        return data

from django.contrib import admin
from .models import TopBarPermission, UserAuditLog, UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'phone', 'branch', 'is_active', 'pin')
    list_filter = ('role', 'branch', 'is_active')
    search_fields = ['user__username', 'user__email', 'phone']
    fields = ('user', 'role', 'phone', 'branch', 'is_active', 'pin')
    readonly_fields = ('user',)


@admin.register(TopBarPermission)
class TopBarPermissionAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'updated_at')
    search_fields = ['user_profile__user__username']


@admin.register(UserAuditLog)
class UserAuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'username', 'action', 'method', 'path', 'status_code', 'ip_address')
    list_filter = ('action', 'method', 'status_code', 'created_at')
    search_fields = ('username', 'path', 'ip_address', 'user_agent')
    readonly_fields = (
        'user', 'user_profile', 'username', 'role', 'action', 'method',
        'path', 'status_code', 'ip_address', 'user_agent', 'metadata', 'created_at'
    )

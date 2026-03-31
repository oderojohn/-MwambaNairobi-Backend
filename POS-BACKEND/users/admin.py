from django.contrib import admin
from .models import UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'phone', 'branch', 'is_active', 'pin')
    list_filter = ('role', 'branch', 'is_active')
    search_fields = ['user__username', 'user__email', 'phone']
    fields = ('user', 'role', 'phone', 'branch', 'is_active', 'pin')
    readonly_fields = ('user',)

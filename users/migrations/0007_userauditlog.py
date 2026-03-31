# Generated manually for user activity tracing

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0006_add_waiter_bartender_roles'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UserAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('username', models.CharField(blank=True, max_length=150)),
                ('role', models.CharField(blank=True, max_length=50)),
                ('action', models.CharField(choices=[('login', 'Login'), ('login_failed', 'Login Failed'), ('logout', 'Logout'), ('request', 'Request'), ('user_created', 'User Created'), ('user_updated', 'User Updated'), ('user_deleted', 'User Deleted'), ('group_created', 'Group Created'), ('group_updated', 'Group Updated'), ('group_deleted', 'Group Deleted'), ('permissions_updated', 'Permissions Updated')], default='request', max_length=50)),
                ('method', models.CharField(blank=True, max_length=16)),
                ('path', models.CharField(blank=True, max_length=255)),
                ('status_code', models.PositiveIntegerField(blank=True, null=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_logs', to=settings.AUTH_USER_MODEL)),
                ('user_profile', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_logs', to='users.userprofile')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]

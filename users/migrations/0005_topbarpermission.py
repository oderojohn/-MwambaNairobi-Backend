from django.db import migrations, models
import users.models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_alter_userprofile_pin_unique'),
    ]

    operations = [
        migrations.CreateModel(
            name='TopBarPermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('allowed_buttons', models.JSONField(default=users.models.default_topbar_permissions)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user_profile', models.OneToOneField(on_delete=models.CASCADE, related_name='topbar_permissions', to='users.userprofile')),
            ],
        ),
    ]

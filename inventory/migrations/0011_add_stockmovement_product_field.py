# Generated manually to add missing product field to StockMovement

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0010_create_missing_models'),
        ('users', '0002_alter_userprofile_role'),
    ]

    operations = []

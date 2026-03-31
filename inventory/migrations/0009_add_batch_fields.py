# Generated manually to add missing batch fields

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0010_create_missing_models'),
        ('suppliers', '0003_remove_purchaseorder_expected_delivery_and_more'),
    ]

    operations = []

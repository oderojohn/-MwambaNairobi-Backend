# Generated manually to add missing supplier field to Batch

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0013_add_batch_product_field'),
        ('suppliers', '0003_remove_purchaseorder_expected_delivery_and_more'),
    ]

    operations = []

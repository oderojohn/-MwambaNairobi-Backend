# Generated migration for Return model - adds return_type and receipt_number fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0018_return_shift'),
        ('shifts', '0005_shift_net_sales_shift_return_count_and_more'),
    ]

    operations = []

# Generated migration for Return model - adds return_type and receipt_number fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0018_return_shift'),
        ('shifts', '0005_shift_net_sales_shift_return_count_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='return',
            name='return_type',
            field=models.CharField(
                choices=[('full_return', 'Full Return'), ('partial_return', 'Partial Return'), ('exchange', 'Exchange')],
                default='partial_return',
                max_length=20
            ),
        ),
        migrations.AddField(
            model_name='return',
            name='receipt_number',
            field=models.CharField(max_length=50, unique=True, blank=True, null=True),
        ),
    ]

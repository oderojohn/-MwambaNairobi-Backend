# Generated migration to add returned_quantity field to SaleItem

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0022_return_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='saleitem',
            name='returned_quantity',
            field=models.PositiveIntegerField(default=0),
        ),
    ]

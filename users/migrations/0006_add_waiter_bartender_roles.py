from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_topbarpermission'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(choices=[('admin', 'Admin'), ('cashier', 'Cashier'), ('bartender', 'Bartender'), ('storekeeper', 'Storekeeper'), ('bar_manager', 'Bar Manager'), ('manager', 'Manager'), ('waiter', 'Waiter'), ('supervisor', 'Supervisor')], default='cashier', max_length=20),
        ),
    ]

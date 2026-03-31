from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_userprofile_pin'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='pin',
            field=models.CharField(blank=True, max_length=5, null=True, unique=True),
        ),
    ]

# Generated by Django 4.1.13 on 2024-08-08 13:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0006_service_service_tags'),
    ]

    operations = [
        migrations.AddField(
            model_name='host',
            name='host_tags',
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
    ]
# Generated by Django 4.1.13 on 2024-08-13 13:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0008_alter_editlock_username_alter_hosteventlog_username_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='host',
            name='ip_address',
            field=models.CharField(blank=True, max_length=256),
        ),
    ]
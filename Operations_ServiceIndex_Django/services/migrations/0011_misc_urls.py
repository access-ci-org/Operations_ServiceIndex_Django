# Generated by Django 4.1.13 on 2024-08-28 18:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0010_rename_ip_address_host_ip_addresses'),
    ]

    operations = [
        migrations.CreateModel(
            name='Misc_urls',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50)),
                ('urls', models.URLField(max_length=512)),
            ],
            options={
                'db_table': '"serviceindex"."misc_urls"',
            },
        ),
    ]

# Generated by Django 4.1.3 on 2022-11-28 17:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='host',
            name='syslog_relp_10515',
            field=models.BooleanField(null=True),
        ),
        migrations.AddField(
            model_name='host',
            name='syslog_standard_10514',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='host',
            name='nagios',
            field=models.BooleanField(null=True),
        ),
        migrations.AlterField(
            model_name='host',
            name='qualys',
            field=models.BooleanField(null=True),
        ),
    ]

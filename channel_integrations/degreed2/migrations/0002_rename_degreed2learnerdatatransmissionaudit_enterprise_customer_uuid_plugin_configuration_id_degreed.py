# Generated by Django 4.2.21 on 2025-06-10 08:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('degreed2_channel', '0001_initial'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='degreed2learnerdatatransmissionaudit',
            new_name='degreed2_ch_enterpr_e3b210_idx',
            old_fields=('enterprise_customer_uuid', 'plugin_configuration_id'),
        ),
        migrations.AlterField(
            model_name='degreed2enterprisecustomerconfiguration',
            name='id',
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
        ),
        migrations.AlterField(
            model_name='degreed2learnerdatatransmissionaudit',
            name='id',
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
        ),
    ]

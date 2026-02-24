# Generated migration for adding OAuth2 client credentials to EnterpriseWebhookConfiguration

import django.core.validators
from django.db import migrations, models
import fernet_fields.fields


class Migration(migrations.Migration):

    dependencies = [
        ('channel_integration', '0007_add_enrollment_events_processing'),
    ]

    operations = [
        migrations.AddField(
            model_name='enterprisewebhookconfiguration',
            name='token_api_url',
            field=models.URLField(blank=True, help_text='OAuth2 token endpoint URL to fetch bearer token (e.g., Skillsoft Provider API)', max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='enterprisewebhookconfiguration',
            name='decrypted_client_id',
            field=fernet_fields.fields.EncryptedCharField(blank=True, help_text='OAuth2 Client ID for token API authentication. Encrypted at rest.', max_length=255, null=True, verbose_name='Client ID'),
        ),
        migrations.AddField(
            model_name='enterprisewebhookconfiguration',
            name='decrypted_client_secret',
            field=fernet_fields.fields.EncryptedCharField(blank=True, help_text='OAuth2 Client Secret for token API authentication. Encrypted at rest.', max_length=255, null=True, verbose_name='Client Secret'),
        ),
        migrations.AddField(
            model_name='enterprisewebhookconfiguration',
            name='provider_name',
            field=models.CharField(blank=True, help_text='Provider name to be sent to the token API (e.g., for Skillsoft)', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='enterprisewebhookconfiguration',
            name='webhook_auth_token',
            field=models.CharField(blank=True, help_text='(Deprecated) Static bearer token for webhook authentication. Use client credentials instead.', max_length=255, null=True),
        ),
    ]

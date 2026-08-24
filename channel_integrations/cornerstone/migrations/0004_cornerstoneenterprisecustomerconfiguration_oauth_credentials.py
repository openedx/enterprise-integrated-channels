import fernet_fields.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cornerstone_channel', '0003_alter_cornerstoneenterprisecustomerconfiguration_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='cornerstoneenterprisecustomerconfiguration',
            name='decrypted_client_id',
            field=fernet_fields.fields.EncryptedCharField(blank=True, default='', help_text="The encrypted OAuth Client ID provided to edX by the enterprise customer, used to obtain access tokens for pushing course completions. When both this and the client secret are set, completions are authenticated with OAuth instead of the learner's launch-time session token.", max_length=255, null=True, verbose_name='Encrypted OAuth Client ID'),
        ),
        migrations.AddField(
            model_name='cornerstoneenterprisecustomerconfiguration',
            name='decrypted_client_secret',
            field=fernet_fields.fields.EncryptedCharField(blank=True, default='', help_text='The encrypted OAuth Client Secret provided to edX by the enterprise customer, used to obtain access tokens for pushing course completions.', max_length=255, null=True, verbose_name='Encrypted OAuth Client Secret'),
        ),
    ]

# Generated by Django 4.2.17 on 2025-01-31 10:32

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import model_utils.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('enterprise', '0228_alter_defaultenterpriseenrollmentrealization_realized_enrollment'),
        ('channel_integration', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DegreedGlobalConfiguration',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('change_date', models.DateTimeField(auto_now_add=True, verbose_name='Change date')),
                ('enabled', models.BooleanField(default=False, verbose_name='Enabled')),
                ('completion_status_api_path', models.CharField(help_text='The API path for making completion POST/DELETE requests to Degreed.', max_length=255, verbose_name='Completion Status API Path')),
                ('course_api_path', models.CharField(help_text='The API path for making course metadata POST/DELETE requests to Degreed.', max_length=255, verbose_name='Course Metadata API Path')),
                ('oauth_api_path', models.CharField(help_text='The API path for making OAuth-related POST requests to Degreed. This will be used to gain the OAuth access token which is required for other API calls.', max_length=255, verbose_name='OAuth API Path')),
                ('changed_by', models.ForeignKey(blank=True, help_text='The user who last changed this configuration.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='degreed_channel_global_configurations', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='DegreedEnterpriseCustomerConfiguration',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('display_name', models.CharField(blank=True, default='', help_text='A configuration nickname.', max_length=255)),
                ('idp_id', models.CharField(blank=True, default='', help_text='If provided, will be used as IDP slug to locate remote id for learners', max_length=255)),
                ('active', models.BooleanField(help_text='Is this configuration active?')),
                ('dry_run_mode_enabled', models.BooleanField(default=False, help_text='Is this configuration in dry-run mode? (experimental)')),
                ('show_course_price', models.BooleanField(default=False, help_text='Displays course price')),
                ('transmission_chunk_size', models.IntegerField(default=500, help_text='The maximum number of data items to transmit to the integrated channel with each request.')),
                ('channel_worker_username', models.CharField(blank=True, default='', help_text='Enterprise channel worker username to get JWT tokens for authenticating LMS APIs.', max_length=255)),
                ('catalogs_to_transmit', models.TextField(blank=True, default='', help_text='A comma-separated list of catalog UUIDs to transmit. If blank, all customer catalogs will be transmitted. If there are overlapping courses in the customer catalogs, the overlapping course metadata will be selected from the newest catalog.')),
                ('disable_learner_data_transmissions', models.BooleanField(default=False, help_text='When set to True, the configured customer will no longer receive learner data transmissions, both scheduled and signal based', verbose_name='Disable Learner Data Transmission')),
                ('last_sync_attempted_at', models.DateTimeField(blank=True, help_text='The DateTime of the most recent Content or Learner data record sync attempt', null=True)),
                ('last_content_sync_attempted_at', models.DateTimeField(blank=True, help_text='The DateTime of the most recent Content data record sync attempt', null=True)),
                ('last_learner_sync_attempted_at', models.DateTimeField(blank=True, help_text='The DateTime of the most recent Learner data record sync attempt', null=True)),
                ('last_sync_errored_at', models.DateTimeField(blank=True, help_text='The DateTime of the most recent failure of a Content or Learner data record sync attempt', null=True)),
                ('last_content_sync_errored_at', models.DateTimeField(blank=True, help_text='The DateTime of the most recent failure of a Content data record sync attempt', null=True)),
                ('last_learner_sync_errored_at', models.DateTimeField(blank=True, help_text='The DateTime of the most recent failure of a Learner data record sync attempt', null=True)),
                ('last_modified_at', models.DateTimeField(auto_now=True, help_text='The DateTime of the last change made to this configuration.', null=True)),
                ('key', models.CharField(blank=True, default='', help_text='The API Client ID provided to edX by the enterprise customer to be used to make API calls to Degreed on behalf of the customer.', max_length=255, verbose_name='API Client ID')),
                ('secret', models.CharField(blank=True, default='', help_text='The API Client Secret provided to edX by the enterprise customer to be used to make API calls to Degreed on behalf of the customer.', max_length=255, verbose_name='API Client Secret')),
                ('degreed_company_id', models.CharField(blank=True, default='', help_text='The organization code provided to the enterprise customer by Degreed.', max_length=255, verbose_name='Degreed Organization Code')),
                ('degreed_base_url', models.CharField(blank=True, default='', help_text='The base URL used for API requests to Degreed, i.e. https://degreed.com.', max_length=255, verbose_name='Degreed Base URL')),
                ('degreed_user_id', models.CharField(blank=True, default='', help_text='The Degreed User ID provided to the content provider by Degreed. It is required for getting the OAuth access token.', max_length=255, verbose_name='Degreed User ID')),
                ('degreed_user_password', models.CharField(blank=True, default='', help_text='The Degreed User Password provided to the content provider by Degreed. It is required for getting the OAuth access token.', max_length=255, verbose_name='Degreed User Password')),
                ('provider_id', models.CharField(default='EDX', help_text='The provider code that Degreed gives to the content provider.', max_length=100, verbose_name='Provider Code')),
                ('enterprise_customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='degreed_enterprise_customer_configurations', to='enterprise.enterprisecustomer')),
            ],
        ),
        migrations.CreateModel(
            name='DegreedLearnerDataTransmissionAudit',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('enterprise_customer_uuid', models.UUIDField(blank=True, null=True)),
                ('user_email', models.CharField(blank=True, max_length=255, null=True)),
                ('plugin_configuration_id', models.IntegerField(blank=True, null=True)),
                ('enterprise_course_enrollment_id', models.IntegerField(blank=True, db_index=True, null=True)),
                ('course_id', models.CharField(max_length=255)),
                ('content_title', models.CharField(blank=True, default=None, max_length=255, null=True)),
                ('course_completed', models.BooleanField(default=True)),
                ('progress_status', models.CharField(blank=True, max_length=255)),
                ('completed_timestamp', models.DateTimeField(blank=True, null=True)),
                ('instructor_name', models.CharField(blank=True, max_length=255)),
                ('grade', models.FloatField(blank=True, null=True)),
                ('total_hours', models.FloatField(blank=True, null=True)),
                ('subsection_id', models.CharField(blank=True, db_index=True, max_length=255, null=True)),
                ('subsection_name', models.CharField(max_length=255, null=True)),
                ('status', models.CharField(blank=True, max_length=100, null=True)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('is_transmitted', models.BooleanField(default=False)),
                ('friendly_status_message', models.CharField(blank=True, default=None, help_text='A user-friendly API response status message.', max_length=255, null=True)),
                ('degreed_user_email', models.CharField(max_length=255)),
                ('degreed_completed_timestamp', models.CharField(blank=True, help_text='Represents the Degreed representation of a timestamp: yyyy-mm-dd, which is always 10 characters.', max_length=10, null=True)),
                ('api_record', models.OneToOneField(blank=True, help_text='Data pertaining to the transmissions API request response.', null=True, on_delete=django.db.models.deletion.CASCADE, to='channel_integration.apiresponserecord')),
            ],
            options={
                'index_together': {('enterprise_customer_uuid', 'plugin_configuration_id')},
            },
        ),
    ]

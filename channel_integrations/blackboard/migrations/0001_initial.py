# Generated by Django 4.2.18 on 2025-02-21 07:42

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import fernet_fields.fields
import model_utils.fields
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('enterprise', '0228_alter_defaultenterpriseenrollmentrealization_realized_enrollment'),
        ('channel_integration', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BlackboardLearnerDataTransmissionAudit',
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
                ('blackboard_user_email', models.EmailField(help_text='The learner`s Blackboard email. This must match the email on edX in order for both learner and content metadata integrations.', max_length=255)),
                ('blackboard_completed_timestamp', models.CharField(blank=True, help_text='Represents the Blackboard representation of a timestamp: yyyy-mm-dd, which is always 10 characters. Can be left unset for audit transmissions.', max_length=10, null=True)),
                ('api_record', models.OneToOneField(blank=True, help_text='Data pertaining to the transmissions API request response.', null=True, on_delete=django.db.models.deletion.CASCADE, to='channel_integration.apiresponserecord')),
            ],
        ),
        migrations.CreateModel(
            name='BlackboardLearnerAssessmentDataTransmissionAudit',
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
                ('blackboard_user_email', models.CharField(max_length=255)),
                ('grade_point_score', models.FloatField(help_text='The amount of points that the learner scored on the subsection.')),
                ('grade_points_possible', models.FloatField(help_text='The total amount of points that the learner could score on the subsection.')),
                ('api_record', models.OneToOneField(blank=True, help_text='Data pertaining to the transmissions API request response.', null=True, on_delete=django.db.models.deletion.CASCADE, to='channel_integration.apiresponserecord')),
            ],
        ),
        migrations.CreateModel(
            name='BlackboardGlobalConfiguration',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('change_date', models.DateTimeField(auto_now_add=True, verbose_name='Change date')),
                ('enabled', models.BooleanField(default=False, verbose_name='Enabled')),
                ('app_key', models.CharField(blank=True, default='', help_text='The application API key identifying the edX integration application to be used in the API oauth handshake.', max_length=255, verbose_name='Blackboard Application Key')),
                ('app_secret', models.CharField(blank=True, default='', help_text='The application API secret used to make to identify ourselves as the edX integration app to customer instances. Called Application Secret in Blackboard', max_length=255, verbose_name='API Client Secret or Application Secret')),
                ('changed_by', models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='blackboard_global_configuration_changed_by', to=settings.AUTH_USER_MODEL, verbose_name='Changed by')),
            ],
        ),
        migrations.CreateModel(
            name='BlackboardEnterpriseCustomerConfiguration',
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
                ('decrypted_client_id', fernet_fields.fields.EncryptedCharField(blank=True, default='', help_text='The API Client ID (encrypted at db level) provided to edX by the enterprise customer to be used to make API calls to Degreed on behalf of the customer.', max_length=255, verbose_name='API Client ID encrypted at db level')),
                ('decrypted_client_secret', fernet_fields.fields.EncryptedCharField(blank=True, default='', help_text='The API Client Secret (encrypted at db level) provided to edX by the enterprise customer to be used to make API calls to Degreed on behalf of the customer.', max_length=255, verbose_name='API Client Secret encrypted at db level')),
                ('blackboard_base_url', models.CharField(blank=True, default='', help_text='The base URL used for API requests to Blackboard, i.e. https://blackboard.com.', max_length=255, verbose_name='Base URL')),
                ('refresh_token', models.CharField(blank=True, help_text='The refresh token provided by Blackboard along with the access token request,used to re-request the access tokens over multiple client sessions.', max_length=255, verbose_name='Oauth2 Refresh Token')),
                ('transmission_chunk_size', models.IntegerField(default=1, help_text='The maximum number of data items to transmit to the integrated channel with each request.')),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, help_text='A UUID for use in public-facing urls such as oauth state variables.', unique=True)),
                ('enterprise_customer', models.ForeignKey(help_text='Enterprise Customer associated with the configuration.', on_delete=django.db.models.deletion.CASCADE, related_name='blackboard_enterprisecustomerpluginconfiguration', to='enterprise.enterprisecustomer')),
            ],
        ),
        migrations.AddConstraint(
            model_name='blackboardlearnerdatatransmissionaudit',
            constraint=models.UniqueConstraint(fields=('enterprise_course_enrollment_id', 'course_id'), name='blackboard_ch_unique_enrollment_course_id'),
        ),
        migrations.AlterIndexTogether(
            name='blackboardlearnerdatatransmissionaudit',
            index_together={('enterprise_customer_uuid', 'plugin_configuration_id')},
        ),
    ]

# Generated by Django 4.2.18 on 2025-02-19 14:32

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import fernet_fields.fields
import model_utils.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('channel_integration', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='MoodleLearnerDataTransmissionAudit',
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
                ('moodle_user_email', models.EmailField(help_text='The learner`s Moodle email. This must match the email on edX', max_length=255)),
                ('moodle_completed_timestamp', models.CharField(blank=True, help_text='Represents the Moodle representation of a timestamp: yyyy-mm-dd, which is always 10 characters. Can be left unset for audit transmissions.', max_length=10, null=True)),
                ('api_record', models.OneToOneField(blank=True, help_text='Data pertaining to the transmissions API request response.', null=True, on_delete=django.db.models.deletion.CASCADE, to='channel_integration.apiresponserecord')),
            ],
        ),
        migrations.CreateModel(
            name='MoodleEnterpriseCustomerConfiguration',
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
                ('moodle_base_url', models.CharField(blank=True, help_text='The base URL used for API requests to Moodle', max_length=255, verbose_name='Moodle Base URL')),
                ('service_short_name', models.CharField(blank=True, help_text='The short name for the Moodle webservice.', max_length=255, verbose_name='Webservice Short Name')),
                ('category_id', models.IntegerField(blank=True, help_text='The category ID for what edX courses should be associated with.', null=True, verbose_name='Category ID')),
                ('decrypted_username', fernet_fields.fields.EncryptedCharField(blank=True, help_text="The encrypted API user's username used to obtain new tokens. It will be encrypted when stored in the database.", max_length=255, null=True, verbose_name='Encrypted Webservice Username')),
                ('decrypted_password', fernet_fields.fields.EncryptedCharField(blank=True, help_text="The encrypted API user's password used to obtain new tokens. It will be encrypted when stored in the database.", max_length=255, null=True, verbose_name='Encrypted Webservice Password')),
                ('decrypted_token', fernet_fields.fields.EncryptedCharField(blank=True, help_text="The encrypted API user's token used to obtain new tokens. It will be encrypted when stored in the database.", max_length=255, null=True, verbose_name='Encrypted Webservice Token')),
                ('transmission_chunk_size', models.IntegerField(default=1, help_text='The maximum number of data items to transmit to the integrated channel with each request.')),
                ('grade_scale', models.IntegerField(default=100, help_text='The maximum grade points for the courses. Default: 100', verbose_name='Grade Scale')),
                ('grade_assignment_name', models.CharField(default='(edX integration) Final Grade', help_text='The name for the grade assigment created for the grade integration.', max_length=255, verbose_name='Grade Assignment Name')),
                ('enable_incomplete_progress_transmission', models.BooleanField(default=False, help_text='When set to True, the configured customer will receive learner data transmissions, for incomplete courses as well')),
                ('enterprise_customer', models.ForeignKey(help_text='Enterprise Customer associated with the configuration.', on_delete=django.db.models.deletion.CASCADE, related_name='moodle_enterprisecustomerpluginconfiguration', to='enterprise.enterprisecustomer')),
            ],
        ),
        migrations.AddConstraint(
            model_name='moodlelearnerdatatransmissionaudit',
            constraint=models.UniqueConstraint(fields=('enterprise_course_enrollment_id', 'course_id'), name='moodle_ch_unique_enrollment_course_id'),
        ),
        migrations.AlterIndexTogether(
            name='moodlelearnerdatatransmissionaudit',
            index_together={('enterprise_customer_uuid', 'plugin_configuration_id')},
        ),
    ]

"""
Truncate non-empty destination tables in the channel_integrations app.

This command is designed to clean up destination tables before running the migration
from legacy integrated_channels app to the new channel_integrations app.

Use this when:
- The migration command failed midway and left partial data
- There is dummy/test data in destination tables that needs to be removed
- You want to ensure a clean slate before migrating

NOTE: This is a temporary migration command that will be used only during the migration
process for Integrated Channels. Once the migration work is complete, this command
will be deleted.

Coverage is intentionally skipped for this file using # pragma: no cover comments
because this is temporary migration code that will be removed after the migration
process is complete.
"""

import logging  # pragma: no cover

from django.apps import apps  # pragma: no cover
from django.core.management.base import BaseCommand, CommandError  # pragma: no cover
from django.db import connections  # pragma: no cover
from django.utils.translation import gettext as _  # pragma: no cover

LOGGER = logging.getLogger(__name__)  # pragma: no cover


class Command(BaseCommand):  # pragma: no cover
    """
    Management command to truncate non-empty destination tables in channel_integrations app.

    Provides safety features like dry-run and confirmation prompts.
    """

    help = _(
        '''
    Truncate non-empty destination tables in the channel_integrations app.

    Usage:

    # Show which tables would be truncated (dry run)
    ./manage.py lms ic_truncate_destination_tables --dry-run

    # Truncate all non-empty destination tables with confirmation
    ./manage.py lms ic_truncate_destination_tables

    # Truncate all without confirmation prompt (use with caution!)
    ./manage.py lms ic_truncate_destination_tables --no-input

    # Truncate only specific models
    ./manage.py lms ic_truncate_destination_tables --only-models ApiResponseRecord,ContentMetadataItemTransmission
    '''
    )

    def add_arguments(self, parser):
        """
        Add arguments to the parser.
        """
        parser.add_argument(
            '--dry-run',
            dest='dry_run',
            action='store_true',
            default=False,
            help=_('Show which tables would be truncated without actually truncating them.'),
        )
        parser.add_argument(
            '--no-input',
            dest='no_input',
            action='store_true',
            default=False,
            help=_('Skip confirmation prompt. USE WITH CAUTION!'),
        )
        parser.add_argument(
            '--only-models',
            dest='only_models',
            default='',
            help=_(
                'Comma-separated list of model names to truncate. If provided, only these models will be truncated.'
            ),
        )

    def handle(self, *args, **options):
        """
        Execute the command to truncate destination tables.
        """
        dry_run = options['dry_run']
        no_input = options['no_input']
        only_models = options['only_models'].split(',') if options['only_models'] else []

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE: No tables will be truncated."))

        # Get model mapping (destination tables only)
        model_mapping = self.get_model_mapping()

        # Collect tables to truncate
        tables_to_truncate = []

        for dest_app, dest_model in model_mapping:
            # Skip if only_models is specified and this model is not in the list
            if only_models and dest_model not in only_models:
                continue

            try:
                destination_model = apps.get_model(dest_app, dest_model)
            except LookupError:
                self.stdout.write(
                    self.style.WARNING(f"Destination model {dest_app}.{dest_model} not found, skipping...")
                )
                continue

            # Check if table has records
            record_count = destination_model.objects.count()
            if record_count > 0:
                table_name = destination_model._meta.db_table
                tables_to_truncate.append(
                    {
                        'model': dest_model,
                        'app': dest_app,
                        'table': table_name,
                        'count': record_count,
                    }
                )

        if not tables_to_truncate:
            self.stdout.write(self.style.SUCCESS("No non-empty tables found. Nothing to truncate."))
            return

        # Display tables to be truncated
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.WARNING("Tables to be truncated:"))
        self.stdout.write("=" * 70)

        total_records = 0
        for table_info in tables_to_truncate:
            self.stdout.write(
                f"• {table_info['app']}.{table_info['model']} "
                f"({table_info['table']}) - {table_info['count']} records"
            )
            total_records += table_info['count']

        self.stdout.write("-" * 70)
        self.stdout.write(f"Total tables: {len(tables_to_truncate)}")
        self.stdout.write(f"Total records to delete: {total_records}")
        self.stdout.write("=" * 70)

        if dry_run:
            self.stdout.write(self.style.WARNING("\nThis was a dry run - no tables were truncated."))
            return

        # Confirmation prompt (unless --no-input is specified)
        if not no_input:
            self.stdout.write(
                self.style.ERROR("\n⚠️  WARNING: This will permanently delete all data from the tables listed above!")
            )
            confirmation = input("\nType 'yes' to confirm truncation: ")
            if confirmation.lower() != 'yes':
                self.stdout.write(self.style.WARNING("Truncation cancelled."))
                return

        # Perform truncation
        self.stdout.write("\nTruncating tables...")
        successful = 0
        failed = 0

        with connections['default'].cursor() as cursor:
            # Disable foreign key checks for MySQL to avoid constraint issues
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

            for table_info in tables_to_truncate:
                try:
                    self.stdout.write(f"Truncating {table_info['table']}...")
                    cursor.execute(f"TRUNCATE TABLE {table_info['table']}")
                    successful += 1
                    self.stdout.write(self.style.SUCCESS(f"  ✓ Truncated {table_info['count']} records"))
                except Exception as e:
                    failed += 1
                    self.stderr.write(self.style.ERROR(f"  ✗ Error truncating {table_info['table']}: {str(e)}"))
                    LOGGER.exception(f"Error truncating {table_info['table']}")

            # Re-enable foreign key checks
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("Truncation Summary:"))
        self.stdout.write("=" * 70)
        self.stdout.write(f"Successful: {self.style.SUCCESS(successful)}")
        self.stdout.write(f"Failed: {self.style.ERROR(failed) if failed > 0 else 0}")
        self.stdout.write(f"Total records deleted: {total_records}")

    def get_model_mapping(self):
        """
        Get the destination model mapping list.

        Returns a list of tuples: (dest_app, dest_model)
        """
        return [
            # Integrated Channel Models
            ('channel_integration', 'ContentMetadataItemTransmission'),
            ('channel_integration', 'ApiResponseRecord'),
            ('channel_integration', 'IntegratedChannelAPIRequestLogs'),
            # SAP Success Factors Models
            ('sap_success_factors_channel', 'SAPSuccessFactorsEnterpriseCustomerConfiguration'),
            ('sap_success_factors_channel', 'SapSuccessFactorsGlobalConfiguration'),
            ('sap_success_factors_channel', 'SapSuccessFactorsLearnerDataTransmissionAudit'),
            # Degreed2 Models
            ('degreed2_channel', 'Degreed2EnterpriseCustomerConfiguration'),
            ('degreed2_channel', 'Degreed2GlobalConfiguration'),
            ('degreed2_channel', 'Degreed2LearnerDataTransmissionAudit'),
            # Canvas Models
            ('canvas_channel', 'CanvasEnterpriseCustomerConfiguration'),
            ('canvas_channel', 'CanvasLearnerDataTransmissionAudit'),
            ('canvas_channel', 'CanvasLearnerAssessmentDataTransmissionAudit'),
            # Blackboard Models
            ('blackboard_channel', 'BlackboardEnterpriseCustomerConfiguration'),
            ('blackboard_channel', 'BlackboardLearnerDataTransmissionAudit'),
            ('blackboard_channel', 'BlackboardLearnerAssessmentDataTransmissionAudit'),
            # Cornerstone Models
            ('cornerstone_channel', 'CornerstoneEnterpriseCustomerConfiguration'),
            ('cornerstone_channel', 'CornerstoneLearnerDataTransmissionAudit'),
            # Moodle Models
            ('moodle_channel', 'MoodleEnterpriseCustomerConfiguration'),
            ('moodle_channel', 'MoodleLearnerDataTransmissionAudit'),
            # xAPI Models
            ('xapi_channel', 'XAPILRSConfiguration'),
            ('xapi_channel', 'XAPILearnerDataTransmissionAudit'),
        ]

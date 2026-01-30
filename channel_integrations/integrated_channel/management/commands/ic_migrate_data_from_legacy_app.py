"""
Migrate data from legacy integrated_channels app to the new channel_integrations app.

This command efficiently copies data from legacy tables to new tables with identical schemas.
The tables have the same structure but different names (e.g., integrated_channel_apiresponserecord
vs channel_integration_apiresponserecord).

NOTE: This is a temporary migration command that will be used only during the migration
process for Integrated Channels. Once the migration work is complete and all customer data
has been successfully migrated from the legacy integrated_channels app to the new
channel_integrations app, this command will be deleted.

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
    Management command to efficiently migrate data from legacy integrated_channels app to new channel_integrations app.

    Uses optimized bulk operations to copy entire tables between apps.
    """

    help = _(
        '''
    Migrate data from legacy integrated_channels app to the new channel_integrations app.

    Usage:

    # Migrate all tables
    ./manage.py lms ic_migrate_data_from_legacy_app

    # Migrate specific models only
    ./manage.py lms ic_migrate_data_from_legacy_app --only-models ApiResponseRecord,ContentMetadataItemTransmission

    # Skip specific models
    ./manage.py lms ic_migrate_data_from_legacy_app --skip-models SapSuccessFactorsGlobalConfiguration

    # Migrate only configuration tables
    ./manage.py lms ic_migrate_data_from_legacy_app --config-only

    # Migrate only logs and audit tables
    ./manage.py lms ic_migrate_data_from_legacy_app --logs-only

    # Do a dry run without making changes
    ./manage.py lms ic_migrate_data_from_legacy_app --dry-run
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
            help=_('Perform a dry run without actually migrating data.'),
        )
        parser.add_argument(
            '--skip-models',
            dest='skip_models',
            default='',
            help=_(
                'Comma-separated list of model names to skip (e.g., "SapSuccessFactorsGlobalConfiguration,ContentMetadataItemTransmission").'
            ),
        )
        parser.add_argument(
            '--only-models',
            dest='only_models',
            default='',
            help=_('Comma-separated list of model names to process. If provided, only these models will be migrated.'),
        )
        parser.add_argument(
            '--continue-on-error',
            dest='continue_on_error',
            action='store_true',
            default=False,
            help=_('Continue processing even if an error occurs for a specific model.'),
        )
        parser.add_argument(
            '--config-only',
            dest='config_only',
            action='store_true',
            default=False,
            help=_('Migrate only configuration tables, excluding logs and audit records.'),
        )
        parser.add_argument(
            '--logs-only',
            dest='logs_only',
            action='store_true',
            default=False,
            help=_('Migrate only logs and audit records, excluding configuration tables.'),
        )

    def handle(self, *args, **options):
        """
        Execute the command to migrate data from legacy app to new app.
        """
        dry_run = options['dry_run']
        skip_models = options['skip_models'].split(',') if options['skip_models'] else []
        only_models = options['only_models'].split(',') if options['only_models'] else []
        continue_on_error = options['continue_on_error']
        config_only = options['config_only']
        logs_only = options['logs_only']

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE: No data will be migrated."))

        if config_only and logs_only:
            raise CommandError("Cannot use both --config-only and --logs-only together. Choose one option.")

        # Define the mapping of old models to new models (src_app, src_model, dest_app, dest_model, model_type)
        model_mapping = self.get_model_mapping()

        # Filter models based on config_only or logs_only flags
        if config_only:
            model_mapping = [m for m in model_mapping if m[4] == 'config']
            self.stdout.write("Migrating configuration tables only.")
        elif logs_only:
            model_mapping = [m for m in model_mapping if m[4] == 'log']
            self.stdout.write("Migrating logs and audit tables only.")

        total_models = len(model_mapping)
        processed_models = 0
        successful_models = 0
        failed_models = 0
        skipped_models = 0

        for model_info in model_mapping:
            src_app, src_model, dest_app, dest_model, model_type = model_info
            processed_models += 1

            # Skip models if they are in the skip list
            if src_model in skip_models:
                self.stdout.write(f"Skipping {src_model} (in skip list)")
                skipped_models += 1
                continue

            # Skip models if they are not in the only_models list when it's provided
            if only_models and src_model not in only_models:
                self.stdout.write(f"Skipping {src_model} (not in only_models list)")
                skipped_models += 1
                continue

            try:
                self.migrate_model_data(
                    src_app=src_app,
                    src_model=src_model,
                    dest_app=dest_app,
                    dest_model=dest_model,
                    dry_run=dry_run,
                )
                successful_models += 1
            except Exception as e:
                failed_models += 1
                self.stderr.write(self.style.ERROR(f"Error processing model {src_model}: {str(e)}"))
                LOGGER.exception(f"Error processing model {src_model}")

                if not continue_on_error:
                    raise

            self.stdout.write(f"Progress: {processed_models}/{total_models} models processed")

        # Count how many of each type we processed
        config_count = sum(
            1
            for m in model_mapping
            if m[4] == 'config' and m[1] not in skip_models and (not only_models or m[1] in only_models)
        )
        log_count = sum(
            1
            for m in model_mapping
            if m[4] == 'log' and m[1] not in skip_models and (not only_models or m[1] in only_models)
        )

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("Migration Summary:"))
        self.stdout.write("=" * 70)
        self.stdout.write(f"Total models: {total_models}")
        self.stdout.write(f"Processed: {processed_models}")
        self.stdout.write(f"  - Configuration tables: {config_count}")
        self.stdout.write(f"  - Log/audit tables: {log_count}")
        self.stdout.write(f"Successful: {self.style.SUCCESS(successful_models)}")
        self.stdout.write(f"Failed: {self.style.ERROR(failed_models) if failed_models > 0 else 0}")
        self.stdout.write(f"Skipped: {skipped_models}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nThis was a dry run - no data was actually migrated."))

    def get_model_mapping(self):
        """
        Get the model mapping list.

        Returns a list of tuples: (src_app, src_model, dest_app, dest_model, model_type)
        """
        return [
            # Integrated Channel Models
            (
                'integrated_channel',
                'ContentMetadataItemTransmission',
                'channel_integration',
                'ContentMetadataItemTransmission',
                'log',
            ),
            ('integrated_channel', 'ApiResponseRecord', 'channel_integration', 'ApiResponseRecord', 'log'),
            # SAP Success Factors Models
            (
                'sap_success_factors',
                'SAPSuccessFactorsEnterpriseCustomerConfiguration',
                'sap_success_factors_channel',
                'SAPSuccessFactorsEnterpriseCustomerConfiguration',
                'config',
            ),
            (
                'sap_success_factors',
                'SapSuccessFactorsGlobalConfiguration',
                'sap_success_factors_channel',
                'SapSuccessFactorsGlobalConfiguration',
                'config',
            ),
            (
                'sap_success_factors',
                'SapSuccessFactorsLearnerDataTransmissionAudit',
                'sap_success_factors_channel',
                'SapSuccessFactorsLearnerDataTransmissionAudit',
                'log',
            ),
            # Degreed2 Models
            (
                'degreed2',
                'Degreed2EnterpriseCustomerConfiguration',
                'degreed2_channel',
                'Degreed2EnterpriseCustomerConfiguration',
                'config',
            ),
            ('degreed2', 'Degreed2GlobalConfiguration', 'degreed2_channel', 'Degreed2GlobalConfiguration', 'config'),
            (
                'degreed2',
                'Degreed2LearnerDataTransmissionAudit',
                'degreed2_channel',
                'Degreed2LearnerDataTransmissionAudit',
                'log',
            ),
            # Canvas Models
            (
                'canvas',
                'CanvasEnterpriseCustomerConfiguration',
                'canvas_channel',
                'CanvasEnterpriseCustomerConfiguration',
                'config',
            ),
            (
                'canvas',
                'CanvasLearnerDataTransmissionAudit',
                'canvas_channel',
                'CanvasLearnerDataTransmissionAudit',
                'log',
            ),
            (
                'canvas',
                'CanvasLearnerAssessmentDataTransmissionAudit',
                'canvas_channel',
                'CanvasLearnerAssessmentDataTransmissionAudit',
                'log',
            ),
            # Blackboard Models
            (
                'blackboard',
                'BlackboardEnterpriseCustomerConfiguration',
                'blackboard_channel',
                'BlackboardEnterpriseCustomerConfiguration',
                'config',
            ),
            (
                'blackboard',
                'BlackboardLearnerDataTransmissionAudit',
                'blackboard_channel',
                'BlackboardLearnerDataTransmissionAudit',
                'log',
            ),
            (
                'blackboard',
                'BlackboardLearnerAssessmentDataTransmissionAudit',
                'blackboard_channel',
                'BlackboardLearnerAssessmentDataTransmissionAudit',
                'log',
            ),
            # Cornerstone Models
            (
                'cornerstone',
                'CornerstoneEnterpriseCustomerConfiguration',
                'cornerstone_channel',
                'CornerstoneEnterpriseCustomerConfiguration',
                'config',
            ),
            (
                'cornerstone',
                'CornerstoneLearnerDataTransmissionAudit',
                'cornerstone_channel',
                'CornerstoneLearnerDataTransmissionAudit',
                'log',
            ),
            # Moodle Models
            (
                'moodle',
                'MoodleEnterpriseCustomerConfiguration',
                'moodle_channel',
                'MoodleEnterpriseCustomerConfiguration',
                'config',
            ),
            (
                'moodle',
                'MoodleLearnerDataTransmissionAudit',
                'moodle_channel',
                'MoodleLearnerDataTransmissionAudit',
                'log',
            ),
            # xAPI Models
            ('xapi', 'XAPILRSConfiguration', 'xapi_channel', 'XAPILRSConfiguration', 'config'),
            ('xapi', 'XAPILearnerDataTransmissionAudit', 'xapi_channel', 'XAPILearnerDataTransmissionAudit', 'log'),
        ]

    def get_table_name(self, model):
        """
        Get the database table name for a model.

        Args:
            model: Django model class

        Returns:
            str: Database table name
        """
        return model._meta.db_table

    def get_column_names(self, model):
        """
        Get all column names for a model.

        Args:
            model: Django model class

        Returns:
            list: List of column names
        """
        return [field.column for field in model._meta.fields]

    def migrate_model_data(self, src_app, src_model, dest_app, dest_model, dry_run):
        """
        Efficiently migrate data from a source table to a destination table using raw SQL.

        This method uses optimized bulk INSERT operations for maximum performance when
        copying between tables with identical schemas.

        Args:
            src_app (str): Source app name
            src_model (str): Source model name
            dest_app (str): Destination app name
            dest_model (str): Destination model name
            dry_run (bool): If True, don't actually perform the migration
        """
        self.stdout.write(f"\n{'-' * 70}")
        self.stdout.write(f"Migrating: {src_app}.{src_model} → {dest_app}.{dest_model}")
        self.stdout.write(f"{'-' * 70}")

        try:
            # Get source and destination models
            try:
                source_model = apps.get_model(src_app, src_model)
            except LookupError:
                self.stdout.write(self.style.WARNING(f"Source model {src_app}.{src_model} not found, skipping..."))
                return

            try:
                destination_model = apps.get_model(dest_app, dest_model)
            except LookupError:
                self.stdout.write(
                    self.style.WARNING(f"Destination model {dest_app}.{dest_model} not found, skipping...")
                )
                return

            # Get table names
            source_table = self.get_table_name(source_model)
            dest_table = self.get_table_name(destination_model)

            self.stdout.write(f"Source table: {source_table}")
            self.stdout.write(f"Destination table: {dest_table}")

            # Get column names
            source_columns = self.get_column_names(source_model)
            dest_columns = self.get_column_names(destination_model)

            # Find common columns, preserving source column order
            common_columns = [col for col in source_columns if col in dest_columns]

            if not common_columns:
                self.stdout.write(
                    self.style.WARNING(f"No common columns found between {source_table} and {dest_table}, skipping...")
                )
                return

            self.stdout.write(
                f"Common columns ({len(common_columns)}): {', '.join(common_columns[:10])}{'...' if len(common_columns) > 10 else ''}"
            )

            # Get counts
            source_count = source_model.objects.count()
            dest_count_before = destination_model.objects.count()

            self.stdout.write(f"Source records: {source_count}")
            self.stdout.write(f"Destination records (before): {dest_count_before}")

            if source_count == 0:
                self.stdout.write(self.style.WARNING("No records to migrate."))
                return

            if dry_run:
                self.stdout.write(self.style.WARNING(f"DRY RUN: Would migrate {source_count} records"))
                return

            # Use raw SQL for efficient bulk copy (MySQL-specific)
            with connections['default'].cursor() as cursor:
                # Build the INSERT IGNORE INTO ... SELECT query (MySQL)
                columns_str = ', '.join(common_columns)

                insert_query = f"""
                    INSERT IGNORE INTO {dest_table} ({columns_str})
                    SELECT {columns_str}
                    FROM {source_table}
                """

                self.stdout.write("Executing bulk copy (MySQL INSERT IGNORE)...")
                cursor.execute(insert_query)
                rows_affected = cursor.rowcount

            # Get final count
            dest_count_after = destination_model.objects.count()

            self.stdout.write(self.style.SUCCESS(f"✓ Migration complete!"))
            self.stdout.write(f"Rows affected: {rows_affected}")
            self.stdout.write(f"Destination records (after): {dest_count_after}")
            self.stdout.write(f"New records added: {dest_count_after - dest_count_before}")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error migrating {src_app}.{src_model}: {str(e)}"))
            LOGGER.exception(f"Error migrating {src_app}.{src_model}")
            raise

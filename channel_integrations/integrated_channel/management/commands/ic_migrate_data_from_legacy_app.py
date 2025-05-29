"""
Migrate data from legacy integrated_channels app to the new channel_integrations app.

This command is designed to facilitate the migration from the old integrated_channels app
in edx-enterprise to the new channel_integrations app in enterprise-integrated-channels.
"""

import logging  # pragma: no cover
import json  # pragma: no cover
from django.apps import apps  # pragma: no cover
from django.core.management.base import BaseCommand, CommandError  # pragma: no cover
from django.db import IntegrityError, models, connections  # pragma: no cover
from django.utils.translation import gettext as _  # pragma: no cover
from django.db.models.fields.related import ForeignKey, OneToOneField  # pragma: no cover

LOGGER = logging.getLogger(__name__)  # pragma: no cover


class Command(BaseCommand):  # pragma: no cover
    """
    Management command to migrate data from legacy integrated_channels app to new channel_integrations app.

    This migrates all relevant data from the old models to the corresponding new models.
    """

    help = _(
        '''
    Migrate data from legacy integrated_channels app to the new channel_integrations app.

    Usage:

    # Migrate all data (configs and logs)
    ./manage.py lms ic_migrate_data_from_legacy_app

    # Migrate only configuration tables
    ./manage.py lms ic_migrate_data_from_legacy_app --config-only

    # Migrate only logs and audit tables
    ./manage.py lms ic_migrate_data_from_legacy_app --logs-only

    # Do a dry run without making any changes
    ./manage.py lms ic_migrate_data_from_legacy_app --dry-run

    # Migrate specific models only
    ./manage.py lms ic_migrate_data_from_legacy_app --only-models SAPSuccessFactorsEnterpriseCustomerConfiguration,SapSuccessFactorsGlobalConfiguration
    '''
    )

    def add_arguments(self, parser):
        """
        Add arguments to the parser.
        """
        parser.add_argument(
            '--batch-size',
            dest='batch_size',
            type=int,
            default=100,
            help=_('Number of records to process in a single batch.'),
        )
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
        batch_size = options['batch_size']
        dry_run = options['dry_run']
        skip_models = options['skip_models'].split(',') if options['skip_models'] else []
        only_models = options['only_models'].split(',') if options['only_models'] else []
        continue_on_error = options['continue_on_error']
        config_only = options['config_only']
        logs_only = options['logs_only']

        if dry_run:
            self.stdout.write("DRY RUN: No data will be migrated.")

        if config_only and logs_only:
            raise CommandError("Cannot use both --config-only and --logs-only together. Choose one option.")

        # Define the mapping of old models to new models (src_app, src_model, dest_app, dest_model, model_type)
        model_mapping = [
            # Integrated Channel Models
            (
                'integrated_channel',
                'ContentMetadataItemTransmission',
                'channel_integration',
                'ContentMetadataItemTransmission',
                'log',
            ),
            ('integrated_channel', 'ApiResponseRecord', 'channel_integration', 'ApiResponseRecord', 'log'),
            (
                'integrated_channel',
                'IntegratedChannelAPIRequestLogs',
                'channel_integration',
                'IntegratedChannelAPIRequestLogs',
                'log',
            ),
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
                    batch_size=batch_size,
                    dry_run=dry_run,
                )
                successful_models += 1
            except Exception as e:
                failed_models += 1
                self.stderr.write(f"Error processing model {src_model}: {str(e)}")
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

        self.stdout.write("\nMigration Summary:")
        self.stdout.write(f"Total models: {total_models}")
        self.stdout.write(f"Processed: {processed_models}")
        self.stdout.write(f"  - Configuration tables: {config_count}")
        self.stdout.write(f"  - Log/audit tables: {log_count}")
        self.stdout.write(f"Successful: {successful_models}")
        self.stdout.write(f"Failed: {failed_models}")
        self.stdout.write(f"Skipped: {skipped_models}")

        if dry_run:
            self.stdout.write("\nThis was a dry run - no data was actually migrated.")

    def get_field_mapping(self, source_model, destination_model):
        """
        Create a mapping between source model fields and destination model fields.

        This handles cases where field names might have changed between models.

        Args:
            source_model: The source model class
            destination_model: The destination model class

        Returns:
            dict: A mapping from source field names to destination field names
        """
        # Default mapping is source field name -> same field name in destination
        field_mapping = {}

        # Get all fields from both models
        source_fields = {f.name: f for f in source_model._meta.fields}
        dest_fields = {f.name: f for f in destination_model._meta.fields}

        self.stdout.write(f"Source fields: {list(source_fields.keys())}")
        self.stdout.write(f"Destination fields: {list(dest_fields.keys())}")

        # For each source field, see if there's a matching destination field
        for src_field_name, src_field in source_fields.items():
            # Skip 'id' field if destination model doesn't have it
            if src_field_name == 'id' and 'id' not in dest_fields:
                self.stdout.write(f"WARNING: Skipping 'id' field since it's not in destination model")
                continue

            # Direct name match
            if src_field_name in dest_fields:
                field_mapping[src_field_name] = src_field_name
            # Special case mappings could be added here for fields that have been renamed

        # Handle primary key fields specially
        source_pk = source_model._meta.pk.name
        dest_pk = destination_model._meta.pk.name

        self.stdout.write(f"Source primary key: {source_pk}, Destination primary key: {dest_pk}")

        # If both models use different primary key field names but there's a uuid field
        if source_pk != dest_pk and 'uuid' in source_fields and 'uuid' in dest_fields:
            self.stdout.write(f"Primary key fields differ: {source_pk} vs {dest_pk}, but both have uuid field")
            if source_pk not in field_mapping:
                field_mapping[source_pk] = 'uuid'

        return field_mapping

    def handle_foreign_key(self, source_record, field_name, field, dest_model_field):
        """
        Handle foreign key relationships when copying data.

        Args:
            source_record: The source record
            field_name: The name of the field
            field: The field value
            dest_model_field: The destination model field

        Returns:
            The value to use for the foreign key in the destination model
        """
        if field is None:
            return None

        related_model = dest_model_field.related_model

        if isinstance(field, models.Model):
            fk_value = field.pk
        else:
            fk_value = field

        try:
            if related_model.__name__ == 'EnterpriseCustomer' and hasattr(related_model, 'uuid'):
                if hasattr(field, 'uuid'):
                    related_instance = related_model.objects.get(uuid=field.uuid)
                else:
                    related_instance = related_model.objects.get(pk=fk_value)
            else:
                related_instance = related_model.objects.get(pk=fk_value)
            return related_instance
        except related_model.DoesNotExist:
            self.stdout.write(f"WARNING: Related instance with PK {fk_value} not found in {related_model.__name__}")
            return None
        except Exception as e:
            self.stdout.write(f"WARNING: Error resolving foreign key {field_name}: {str(e)}")
            return None

    def handle_many_to_many(self, source_record, destination_record, source_model, destination_model):
        """
        Handle many-to-many relationships when copying data.

        Args:
            source_record: The source record instance
            destination_record: The destination record instance
            source_model: The source model class
            destination_model: The destination model class
        """
        # Get all M2M fields from both models
        src_m2m_fields = {f.name: f for f in source_model._meta.many_to_many}
        dest_m2m_fields = {f.name: f for f in destination_model._meta.many_to_many}

        # For each M2M field in the source model, find the corresponding field in the destination model
        for field_name, field in src_m2m_fields.items():
            if field_name in dest_m2m_fields:
                src_related_model = field.related_model
                dest_related_model = dest_m2m_fields[field_name].related_model

                related_objects = getattr(source_record, field_name).all()

                for related_obj in related_objects:
                    try:
                        if hasattr(related_obj, 'uuid') and hasattr(dest_related_model, 'uuid'):
                            dest_related_obj = dest_related_model.objects.get(uuid=related_obj.uuid)
                        else:
                            dest_related_obj = dest_related_model.objects.get(pk=related_obj.pk)
                        getattr(destination_record, field_name).add(dest_related_obj)
                    except dest_related_model.DoesNotExist:
                        self.stdout.write(
                            f"WARNING: Related object {related_obj.pk} in {src_related_model.__name__} "
                            f"not found in {dest_related_model.__name__}"
                        )
                    except Exception as e:
                        self.stderr.write(f"Error adding M2M relationship: {str(e)}")

    def log_model_stats(self, source_model, destination_model):
        """
        Log statistics about the models being migrated.

        Args:
            source_model: The source model class
            destination_model: The destination model class
        """
        source_count = source_model.objects.count()
        destination_count_before = destination_model.objects.count()

        self.stdout.write(f"Source model ({source_model.__name__}) count: {source_count}")
        self.stdout.write(
            f"Destination model ({destination_model.__name__}) count before migration: {destination_count_before}"
        )

        source_fields = [f.name for f in source_model._meta.fields]
        destination_fields = [f.name for f in destination_model._meta.fields]

        source_only = set(source_fields) - set(destination_fields)
        destination_only = set(destination_fields) - set(source_fields)

        if source_only:
            self.stdout.write(f"Fields only in source model: {', '.join(source_only)}")
        if destination_only:
            self.stdout.write(f"Fields only in destination model: {', '.join(destination_only)}")

    def clear_transaction_errors(self):
        """
        Clear any transaction errors to prevent them from affecting subsequent operations.
        This closes and reopens connections to reset transaction state.
        """
        for conn in connections.all():
            conn.close()

    def migrate_model_data(self, src_app, src_model, dest_app, dest_model, batch_size, dry_run):
        """
        Migrate data from a source model to a destination model.

        Args:
            src_app (str): Source app name
            src_model (str): Source model name
            dest_app (str): Destination app name
            dest_model (str): Destination model name
            batch_size (int): Number of records to process in a batch
            dry_run (bool): If True, don't actually perform the migration
        """
        self.stdout.write(f"\nMigrating data from {src_app}.{src_model} to {dest_app}.{dest_model}")

        try:
            try:
                source_model = apps.get_model(f'{src_app}', src_model)
            except LookupError:
                self.stdout.write(f"Source model integrated_channels.{src_app}.{src_model} not found, skipping...")
                return

            try:
                destination_model = apps.get_model(f'{dest_app}', dest_model)
            except LookupError:
                self.stdout.write(
                    f"Destination model channel_integrations.{dest_app}.{dest_model} not found, skipping..."
                )
                return

            self.log_model_stats(source_model, destination_model)

            destination_count_before = destination_model.objects.count()

            field_mapping = self.get_field_mapping(source_model, destination_model)

            dest_field_objs = {f.name: f for f in destination_model._meta.fields}

            total_records = source_model.objects.count()
            self.stdout.write(f"Total records to migrate: {total_records}")

            if total_records == 0:
                self.stdout.write(f"No records found for {src_app}.{src_model}, skipping...")
                return

            # Get all source records at once (outside any transaction)
            # Instead of fetching just IDs, fetch the entire records to avoid ID field issues
            all_source_records = list(source_model.objects.all())

            # Process in batches
            records_processed = 0
            records_succeeded = 0
            records_failed = 0

            for offset in range(0, total_records, batch_size):
                self.clear_transaction_errors()

                batch_records = all_source_records[offset:offset + batch_size]
                batch_succeeded = 0
                batch_failed = 0

                for source_record in batch_records:
                    self.clear_transaction_errors()

                    try:
                        record_data = {}

                        for src_field_name, dest_field_name in field_mapping.items():
                            try:
                                value = getattr(source_record, src_field_name)
                            except AttributeError:
                                continue

                            dest_field = dest_field_objs.get(dest_field_name)
                            if dest_field and isinstance(dest_field, (ForeignKey, OneToOneField)):
                                value = self.handle_foreign_key(source_record, src_field_name, value, dest_field)

                            record_data[dest_field_name] = value

                        if hasattr(source_record, 'enterprise_customer') and 'enterprise_customer' in record_data:
                            if hasattr(destination_model, 'enterprise_customer'):
                                if hasattr(source_record, 'enterprise_customer_uuid'):
                                    enterprise_customer_uuid = source_record.enterprise_customer_uuid
                                    try:
                                        enterprise_customer = apps.get_model(
                                            'enterprise', 'EnterpriseCustomer'
                                        ).objects.get(uuid=enterprise_customer_uuid)
                                        record_data['enterprise_customer'] = enterprise_customer
                                    except Exception as e:
                                        self.stdout.write(f"WARNING: Error resolving enterprise_customer: {str(e)}")

                        # Handle JSON fields that might have changed structure
                        for field_name, field in dest_field_objs.items():
                            if (
                                field_name in record_data
                                and hasattr(field, 'get_internal_type')
                                and field.get_internal_type() == 'JSONField'
                            ):
                                # Make sure the JSON data is compatible
                                if record_data[field_name] is not None:
                                    if not isinstance(record_data[field_name], dict):
                                        try:
                                            record_data[field_name] = json.loads(record_data[field_name])
                                        except (TypeError, json.JSONDecodeError):
                                            record_data[field_name] = {}

                        if not dry_run:
                            lookup = None

                            if hasattr(source_record, 'uuid') and 'uuid' in dest_field_objs:
                                lookup = {'uuid': source_record.uuid}
                                self.stdout.write(f"Using uuid field for lookup: {source_record.uuid}")
                            elif (
                                hasattr(source_record, 'enterprise_customer')
                                and 'enterprise_customer' in dest_field_objs
                            ):
                                if record_data.get('enterprise_customer'):
                                    lookup = {'enterprise_customer': record_data['enterprise_customer']}
                                    self.stdout.write(f"Using enterprise_customer for lookup")

                            valid_record_data = {}
                            for k, v in record_data.items():
                                if k in dest_field_objs:
                                    valid_record_data[k] = v

                            try:
                                if lookup and destination_model.objects.filter(**lookup).exists():
                                    destination_model.objects.filter(**lookup).update(**valid_record_data)
                                    dest_record = destination_model.objects.get(**lookup)
                                    self.handle_many_to_many(
                                        source_record, dest_record, source_model, destination_model
                                    )
                                    self.stdout.write(f"Updated existing record")
                                else:
                                    if hasattr(source_record, 'uuid') and 'uuid' in dest_field_objs:
                                        valid_record_data['uuid'] = source_record.uuid

                                    dest_record = destination_model.objects.create(**valid_record_data)
                                    self.handle_many_to_many(
                                        source_record, dest_record, source_model, destination_model
                                    )
                                    self.stdout.write(f"Created new record")

                                batch_succeeded += 1
                                records_succeeded += 1
                            except Exception as e:
                                batch_failed += 1
                                records_failed += 1
                                self.stderr.write(f"Error creating/updating record: {str(e)}")
                                continue
                        else:
                            batch_succeeded += 1
                            records_succeeded += 1

                    except IntegrityError as e:
                        batch_failed += 1
                        records_failed += 1
                        pk_value = getattr(source_record, 'uuid', source_record.pk)
                        self.stderr.write(f"Integrity error for record with ID {pk_value}: {str(e)}")
                        self.clear_transaction_errors()
                    except Exception as e:
                        batch_failed += 1
                        records_failed += 1
                        pk_value = getattr(source_record, 'uuid', source_record.pk)
                        self.stderr.write(f"Error migrating record with ID {pk_value}: {str(e)}")
                        self.clear_transaction_errors()

                    records_processed += 1

                self.stdout.write(
                    f"Processed {min(records_processed, total_records)}/{total_records} records "
                    f"in this batch: {batch_succeeded} succeeded, {batch_failed} failed"
                )

            destination_count_after = destination_model.objects.count()
            if dry_run:
                self.stdout.write(f"DRY RUN: Would have migrated {total_records} records from {src_app}.{src_model}")
            else:
                self.stdout.write(
                    f"Migration complete for {src_app}.{src_model}: "
                    f"{records_succeeded} succeeded, {records_failed} failed"
                )
                self.stdout.write(
                    f"Destination model count after migration: {destination_count_after} "
                    f"(delta: {destination_count_after - destination_count_before})"
                )

        except Exception as e:
            self.stderr.write(f"Error migrating data from {src_app}.{src_model}: {str(e)}")
            LOGGER.exception(f"Error migrating data from {src_app}.{src_model}")
            self.clear_transaction_errors()

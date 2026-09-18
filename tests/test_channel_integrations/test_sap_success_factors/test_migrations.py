"""
Tests for the `channel_integrations.sap_success_factors` schema migrations.
"""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from test_utils.factories import EnterpriseCustomerFactory

APP_LABEL = 'sap_success_factors_channel'
MIGRATE_FROM = '0006_sapsuccessfactorsenterprisecustomerconfiguration_transmit_course_hours'
MIGRATE_TO = '0007_sapsuccessfactorsenterprisecustomerconfiguration_auth_type_and_more'


class TestAuthTypeAndPrivateKeyMigration(TransactionTestCase):
    """
    The migration adding modern auth support must leave pre-existing customer rows on legacy auth.
    """

    def _migrate(self, target):
        """
        Migrate the SAP channel app to ``target`` and return the resulting historical app registry.
        """
        targets = [(APP_LABEL, target)]
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        executor.loader.build_graph()
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        # Leave the test database at the latest migration for the rest of the suite.
        self._migrate(MIGRATE_TO)
        super().tearDown()

    def test_existing_rows_get_legacy_auth_defaults(self):
        """
        A row written before the migration comes out of it on legacy auth, with no private key and
        with the standard tenant endpoint paths.
        """
        enterprise_customer = EnterpriseCustomerFactory(name='Pre-existing Customer')

        old_apps = self._migrate(MIGRATE_FROM)
        old_config_model = old_apps.get_model(APP_LABEL, 'SAPSuccessFactorsEnterpriseCustomerConfiguration')

        old_config = old_config_model.objects.create(
            enterprise_customer_id=enterprise_customer.uuid,
            active=True,
            sapsf_base_url='https://sap.example.com',
            sapsf_company_id='COMP1',
            sapsf_user_id='user-1',
        )

        # The columns this migration adds do not exist yet.
        assert not hasattr(old_config, 'auth_type')

        new_apps = self._migrate(MIGRATE_TO)
        new_config_model = new_apps.get_model(APP_LABEL, 'SAPSuccessFactorsEnterpriseCustomerConfiguration')
        migrated_config = new_config_model.objects.get(pk=old_config.pk)

        assert migrated_config.auth_type == 'legacy'
        assert migrated_config.decrypted_private_key == ''
        assert migrated_config.saml_assertion_api_path == '/oauth/idp'
        assert migrated_config.oauth_token_api_path == '/oauth/token'
        assert migrated_config.saml_assertion_audience == 'www.successfactors.com'

        # Pre-existing values are untouched.
        assert migrated_config.sapsf_base_url == 'https://sap.example.com'
        assert migrated_config.sapsf_company_id == 'COMP1'

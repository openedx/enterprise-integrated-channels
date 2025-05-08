"""
Test suite surrounding the database models for Enterprise Integrated Channels.
"""

import unittest

import ddt
from pytest import mark

from channel_integrations.blackboard.models import BlackboardEnterpriseCustomerConfiguration
from channel_integrations.canvas.models import CanvasEnterpriseCustomerConfiguration
from channel_integrations.cornerstone.models import CornerstoneEnterpriseCustomerConfiguration
from channel_integrations.degreed2.models import Degreed2EnterpriseCustomerConfiguration
from channel_integrations.moodle.models import MoodleEnterpriseCustomerConfiguration
from channel_integrations.sap_success_factors.models import SAPSuccessFactorsEnterpriseCustomerConfiguration
from test_utils import factories


@mark.django_db
@ddt.ddt
class TestIntegratedChannelsModels(unittest.TestCase):
    """
    Test suite for Integrated Channels models
    """
    def setUp(self):
        self.blackboard_config = factories.BlackboardEnterpriseCustomerConfigurationFactory()
        self.canvas_config = factories.CanvasEnterpriseCustomerConfigurationFactory()
        self.cornerstone_config = factories.CornerstoneEnterpriseCustomerConfigurationFactory()
        self.degreed2_config = factories.Degreed2EnterpriseCustomerConfigurationFactory()
        self.moodle_config = factories.MoodleEnterpriseCustomerConfigurationFactory()
        self.sap_config = factories.SAPSuccessFactorsEnterpriseCustomerConfigurationFactory()
        super().setUp()

    @ddt.data(
        BlackboardEnterpriseCustomerConfiguration,
        CanvasEnterpriseCustomerConfiguration,
        CornerstoneEnterpriseCustomerConfiguration,
        Degreed2EnterpriseCustomerConfiguration,
        MoodleEnterpriseCustomerConfiguration,
        SAPSuccessFactorsEnterpriseCustomerConfiguration,
    )
    def test_integration_customer_config_soft_delete(self, channel_config):
        """
        Test that the all integration customer configs support soft delete
        """
        # Assert we have something to work with
        assert len(channel_config.objects.all()) == 1

        # Soft delete
        existing_config = channel_config.objects.first()
        existing_config.delete()
        assert not channel_config.objects.all()

        # Assert record not actually deleted
        assert len(channel_config.all_objects.all()) == 1
        assert channel_config.all_objects.first().deleted_at

        # Resurrect the record
        channel_config.all_objects.first().revive()
        assert len(channel_config.objects.all()) == 1
        assert not channel_config.objects.first().deleted_at

        # Hard delete the record
        channel_config.objects.first().hard_delete()
        assert not channel_config.objects.all()
        assert not channel_config.all_objects.all()

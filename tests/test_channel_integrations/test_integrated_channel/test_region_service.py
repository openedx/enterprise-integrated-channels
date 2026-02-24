"""
Tests for region detection service.
"""
import logging
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model

from channel_integrations.integrated_channel.services.region_service import get_user_region

User = get_user_model()


@pytest.mark.django_db
class TestRegionService:
    """Tests for region_service.py."""

    def test_get_user_region_with_explicit_region_in_sso(self):
        """Test region detection using explicit region from SSO extra_data."""
        user = User.objects.create(username='testuser', email='test@example.com')

        with patch(
            'channel_integrations.integrated_channel.services.region_service.UserSocialAuth'
        ) as mock_social_auth:
            mock_social = MagicMock()
            mock_social.extra_data = {'region': 'US'}
            mock_social_auth.objects.filter.return_value.first.return_value = mock_social

            region = get_user_region(user)

            assert region == 'US'
            mock_social_auth.objects.filter.assert_called_once_with(user=user)

    def test_get_user_region_with_enterprise_country(self):
        """Test region detection using enterprise customer country."""
        user = User.objects.create(username='testuser', email='test@example.com')

        with patch(
            'channel_integrations.integrated_channel.services.region_service.UserSocialAuth'
        ) as mock_social_auth:
            with patch(
                'channel_integrations.integrated_channel.services.region_service.EnterpriseCustomerUser'
            ) as mock_ecu:
                mock_social_auth.objects.filter.return_value.first.return_value = None

                # Mock enterprise customer with country
                mock_enterprise = MagicMock()
                mock_enterprise.country = 'DE'
                mock_ecu_instance = MagicMock()
                mock_ecu_instance.enterprise_customer = mock_enterprise
                mock_ecu.objects.filter.return_value.first.return_value = mock_ecu_instance

                region = get_user_region(user)

                assert region == 'EU'

    def test_get_user_region_default_fallback(self):
        """Test region detection falls back to OTHER when no metadata found."""
        user = User.objects.create(username='testuser', email='test@example.com')

        with patch(
            'channel_integrations.integrated_channel.services.region_service.UserSocialAuth'
        ) as mock_social_auth:
            mock_social_auth.objects.filter.return_value.first.return_value = None

            region = get_user_region(user)

            assert region == 'OTHER'

    def test_get_user_region_exception_handling(self, caplog):
        """Test region detection handles exceptions gracefully."""
        caplog.set_level(logging.WARNING)
        user = User.objects.create(username='testuser', email='test@example.com')

        with patch(
            'channel_integrations.integrated_channel.services.region_service.UserSocialAuth'
        ) as mock_social_auth:
            mock_social_auth.objects.filter.side_effect = RuntimeError("Database error")

            region = get_user_region(user)

            assert region == 'OTHER'
            assert any('Error detecting region' in record.message for record in caplog.records)

    def test_map_country_to_region_us(self):
        """Test mapping US country code to US region."""
        user = User.objects.create(username='testuser', email='test@example.com')

        with patch(
            'channel_integrations.integrated_channel.services.region_service.UserSocialAuth'
        ) as mock_social_auth:
            with patch(
                'channel_integrations.integrated_channel.services.region_service.EnterpriseCustomerUser'
            ) as mock_ecu:
                mock_social_auth.objects.filter.return_value.first.return_value = None

                mock_enterprise = MagicMock()
                mock_enterprise.country = 'US'
                mock_ecu_instance = MagicMock()
                mock_ecu_instance.enterprise_customer = mock_enterprise
                mock_ecu.objects.filter.return_value.first.return_value = mock_ecu_instance

                region = get_user_region(user)
                assert region == 'US'

    def test_map_country_to_region_eu(self):
        """Test mapping EU country codes to EU region."""
        user = User.objects.create(username='testuser', email='test@example.com')

        with patch(
            'channel_integrations.integrated_channel.services.region_service.UserSocialAuth'
        ) as mock_social_auth:
            with patch(
                'channel_integrations.integrated_channel.services.region_service.EnterpriseCustomerUser'
            ) as mock_ecu:
                mock_social_auth.objects.filter.return_value.first.return_value = None

                mock_enterprise = MagicMock()
                mock_enterprise.country = 'DE'
                mock_ecu_instance = MagicMock()
                mock_ecu_instance.enterprise_customer = mock_enterprise
                mock_ecu.objects.filter.return_value.first.return_value = mock_ecu_instance

                region = get_user_region(user)
                assert region == 'EU'

    def test_map_country_to_region_other(self):
        """Test mapping non-US/EU country codes to OTHER region."""
        user = User.objects.create(username='testuser', email='test@example.com')

        with patch(
            'channel_integrations.integrated_channel.services.region_service.UserSocialAuth'
        ) as mock_social_auth:
            with patch(
                'channel_integrations.integrated_channel.services.region_service.EnterpriseCustomerUser'
            ) as mock_ecu:
                mock_social_auth.objects.filter.return_value.first.return_value = None

                mock_enterprise = MagicMock()
                mock_enterprise.country = 'CA'
                mock_ecu_instance = MagicMock()
                mock_ecu_instance.enterprise_customer = mock_enterprise
                mock_ecu.objects.filter.return_value.first.return_value = mock_ecu_instance

                region = get_user_region(user)
                assert region == 'OTHER'

    def test_get_user_region_no_enterprise_country_attribute(self):
        """Test region detection when enterprise customer has no country attribute."""
        user = User.objects.create(username='testuser', email='test@example.com')

        with patch(
            'channel_integrations.integrated_channel.services.region_service.UserSocialAuth'
        ) as mock_social_auth:
            with patch(
                'channel_integrations.integrated_channel.services.region_service.EnterpriseCustomerUser'
            ) as mock_ecu:
                mock_social_auth.objects.filter.return_value.first.return_value = None

                # Mock enterprise customer without country attribute
                mock_enterprise = MagicMock(spec=[])  # Empty spec means no attributes
                mock_ecu_instance = MagicMock()
                mock_ecu_instance.enterprise_customer = mock_enterprise
                mock_ecu.objects.filter.return_value.first.return_value = mock_ecu_instance

                region = get_user_region(user)

                # Should fall back to OTHER since no country attribute
                assert region == 'OTHER'

    def test_get_user_region_with_eu_countries(self):
        """Test various EU country codes map correctly."""
        eu_countries = ['FR', 'IT', 'ES', 'NL', 'PL']

        for idx, country_code in enumerate(eu_countries):
            user = User.objects.create(username=f'testuser_{idx}', email=f'test_{idx}@example.com')

            with patch(
                'channel_integrations.integrated_channel.services.region_service.UserSocialAuth'
            ) as mock_social_auth:
                with patch(
                    'channel_integrations.integrated_channel.services.region_service.EnterpriseCustomerUser'
                ) as mock_ecu:
                    mock_social_auth.objects.filter.return_value.first.return_value = None

                    mock_enterprise = MagicMock()
                    mock_enterprise.country = country_code
                    mock_ecu_instance = MagicMock()
                    mock_ecu_instance.enterprise_customer = mock_enterprise
                    mock_ecu.objects.filter.return_value.first.return_value = mock_ecu_instance

                    region = get_user_region(user)
                    assert region == 'EU', f"Country {country_code} should map to EU"

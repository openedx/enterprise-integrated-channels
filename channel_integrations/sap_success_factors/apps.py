"""
Enterprise Integrated Channel SAP SuccessFactors Django application initialization.
"""

from django.apps import AppConfig


class SAPSuccessFactorsConfig(AppConfig):
    """
    Configuration for the Enterprise Integrated Channel SAP SuccessFactors Django application.
    """
    name = 'channel_integrations.sap_success_factors'
    verbose_name = "Enterprise SAP SuccessFactors Integration"
    label = 'sap_success_factors_channel'

"""
Serializer for TPA Org Allowlist.
"""
from rest_framework import serializers
from channel_integrations.integrated_channel.models import TpaOrgAllowlist


class TpaOrgAllowlistSerializer(serializers.ModelSerializer):

    class Meta:
        model = TpaOrgAllowlist
        fields = (
            'id',
            'enterprise_customer',
            'tpa_org_id',
            'demo_account',
            'created',
            'modified',
        )
        read_only_fields = ('id', 'created', 'modified')

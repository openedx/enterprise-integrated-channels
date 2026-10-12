"""
Serializer for TPA Org Allowlist.
"""
from rest_framework import serializers

from enterprise.constants import GROUP_TYPE_BUDGET
from enterprise.models import EnterpriseGroup

from channel_integrations.integrated_channel.models import TpaOrgAllowlist


class TpaOrgAllowlistSerializer(serializers.ModelSerializer):

    class Meta:
        model = TpaOrgAllowlist
        fields = (
            'id',
            'enterprise_customer',
            'tpa_org_id',
            'demo_account',
            'enterprise_group_uuid',
            'created',
            'modified',
        )
        read_only_fields = ('id', 'created', 'modified')

    def __init__(self, *args, **kwargs):
        """
        `enterprise_customer` and `tpa_org_id` identify which row this is - once a row exists,
        updates may only change `enterprise_group_uuid`/`demo_account`, never reassign the row to
        a different org or enterprise. This makes it safe to expose PATCH for setting the
        budget group mapping without also opening up a tenant-reassignment vector.
        """
        super().__init__(*args, **kwargs)
        if self.instance is not None:
            self.fields['enterprise_customer'].read_only = True
            self.fields['tpa_org_id'].read_only = True

    def validate(self, attrs):
        """
        When `enterprise_group_uuid` is set, make sure it points at a real, budget-type
        EnterpriseGroup belonging to the same enterprise_customer as this row. Without this, a
        fat-fingered or malicious UUID could silently mis-scope a learner into another
        customer's budget once the login-time sync starts acting on this mapping.
        """
        enterprise_group_uuid = attrs.get('enterprise_group_uuid')
        if not enterprise_group_uuid:
            return attrs

        enterprise_customer = attrs.get('enterprise_customer') or getattr(
            self.instance, 'enterprise_customer', None
        )
        try:
            group = EnterpriseGroup.available_objects.get(uuid=enterprise_group_uuid)
        except EnterpriseGroup.DoesNotExist as exc:
            raise serializers.ValidationError({
                'enterprise_group_uuid': f'No EnterpriseGroup found with uuid {enterprise_group_uuid}.',
            }) from exc

        if group.enterprise_customer_id != enterprise_customer.pk:
            raise serializers.ValidationError({
                'enterprise_group_uuid': 'This group does not belong to the given enterprise_customer.',
            })
        if group.group_type != GROUP_TYPE_BUDGET:
            raise serializers.ValidationError({
                'enterprise_group_uuid': f'Group must be of type "{GROUP_TYPE_BUDGET}".',
            })

        return attrs

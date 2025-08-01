"""
Serializer for Degreed2 configuration.
"""
from rest_framework import serializers

from enterprise.constants import HTTP_STATUS_STRINGS
from channel_integrations.blackboard.models import BlackboardLearnerDataTransmissionAudit
from channel_integrations.canvas.models import CanvasLearnerDataTransmissionAudit
from channel_integrations.cornerstone.models import CornerstoneLearnerDataTransmissionAudit
from channel_integrations.degreed2.models import Degreed2LearnerDataTransmissionAudit
from channel_integrations.integrated_channel.models import (
    ContentMetadataItemTransmission,
    GenericLearnerDataTransmissionAudit,
    LearnerDataTransmissionAudit,
)
from channel_integrations.moodle.models import MoodleLearnerDataTransmissionAudit
from channel_integrations.sap_success_factors.models import SapSuccessFactorsLearnerDataTransmissionAudit
from channel_integrations.utils import channel_code_to_app_label


class ContentSyncStatusSerializer(serializers.ModelSerializer):

    class Meta:
        model = ContentMetadataItemTransmission
        fields = (
            'content_title',
            'content_id',
            'sync_status',
            'sync_last_attempted_at',
            'friendly_status_message',
        )

    sync_status = serializers.SerializerMethodField()
    sync_last_attempted_at = serializers.SerializerMethodField()
    friendly_status_message = serializers.SerializerMethodField()

    def get_sync_status(self, obj):
        """
        Return a string representation of the sync status.
        """
        sync_status = 'unknown'
        if obj.api_response_status_code is None:
            sync_status = 'pending'
        elif obj.api_response_status_code < 400:
            sync_status = 'okay'
        elif obj.api_response_status_code >= 400:
            sync_status = 'error'
        return sync_status

    def get_sync_last_attempted_at(self, obj):
        """
        Return the most recent/youngest sync attempt date.
        """
        date_list = [obj.remote_created_at, obj.remote_updated_at, obj.remote_deleted_at]
        res = [i for i in date_list if i is not None]
        if not res:
            return None
        else:
            return max(res)

    def get_friendly_status_message(self, obj):
        """
        Return a human readable status string.
        """
        if obj.api_response_status_code is not None and HTTP_STATUS_STRINGS.get(obj.api_response_status_code):
            return HTTP_STATUS_STRINGS.get(obj.api_response_status_code)
        return None


class LearnerSyncStatusSerializer(serializers.ModelSerializer):
    """
    A base sync-status serializer class for LearnerDataTransmissionAudit implementations.
    """

    class Meta:
        model = LearnerDataTransmissionAudit
        fields = (
            'user_email',
            'content_title',
            'progress_status',
            'sync_status',
            'sync_last_attempted_at',
            'friendly_status_message',
        )

    sync_status = serializers.SerializerMethodField()
    sync_last_attempted_at = serializers.SerializerMethodField()
    friendly_status_message = serializers.SerializerMethodField()

    def get_sync_status(self, obj):
        """
        Return a string representation of the sync status.
        """
        sync_status = 'unknown'
        if obj.status is None:
            sync_status = 'pending'
        elif not obj.status.isdigit() or int(obj.status) >= 400:
            sync_status = 'error'
        elif int(obj.status) < 300:
            sync_status = 'okay'

        return sync_status

    def get_sync_last_attempted_at(self, obj):
        """
        Return the most recent/youngest sync attempt date.
        """
        return obj.modified or obj.created

    def get_friendly_status_message(self, obj):
        """
        Return a human readable status string.
        """
        if obj.status is not None and obj.status.isdigit() and HTTP_STATUS_STRINGS.get(int(obj.status)):
            return HTTP_STATUS_STRINGS.get(int(obj.status))
        return None

    @classmethod
    def get_completion_class_by_channel_code(this_cls, channel_code):  # pylint: disable=bad-classmethod-argument
        """
        return the `LearnerDataTransmissionAudit` completion related sync-status
        serializer for a particular channel_code
        """
        app_label = channel_code_to_app_label(channel_code)
        for a_cls in this_cls.__subclasses__():
            if a_cls.Meta().model._meta.app_label == app_label:
                return a_cls
        return None


class GenericLearnerSyncStatusSerializer(LearnerSyncStatusSerializer):
    """
    `GenericLearnerDataTransmissionAudit` sync-status serializer
    """

    class Meta:
        model = GenericLearnerDataTransmissionAudit
        fields = LearnerSyncStatusSerializer.Meta.fields


class BlackboardLearnerSyncStatusSerializer(LearnerSyncStatusSerializer):
    """
    `BlackboardLearnerDataTransmissionAudit` sync-status serializer
    """

    class Meta:
        model = BlackboardLearnerDataTransmissionAudit
        fields = LearnerSyncStatusSerializer.Meta.fields


class CanvasLearnerSyncStatusSerializer(LearnerSyncStatusSerializer):
    """
    `CanvasLearnerDataTransmissionAudit` sync-status serializer
    """

    class Meta:
        model = CanvasLearnerDataTransmissionAudit
        fields = LearnerSyncStatusSerializer.Meta.fields


class CornerstoneLearnerSyncStatusSerializer(LearnerSyncStatusSerializer):
    """
    `CornerstoneLearnerDataTransmissionAudit` sync-status serializer
    """

    class Meta:
        model = CornerstoneLearnerDataTransmissionAudit
        fields = LearnerSyncStatusSerializer.Meta.fields


class Degreed2LearnerSyncStatusSerializer(LearnerSyncStatusSerializer):
    """
    `Degreed2LearnerDataTransmissionAudit` sync-status serializer
    """

    class Meta:
        model = Degreed2LearnerDataTransmissionAudit
        fields = LearnerSyncStatusSerializer.Meta.fields


class MoodleLearnerSyncStatusSerializer(LearnerSyncStatusSerializer):
    """
    `MoodleLearnerDataTransmissionAudit` sync-status serializer
    """

    class Meta:
        model = MoodleLearnerDataTransmissionAudit
        fields = LearnerSyncStatusSerializer.Meta.fields


class SapLearnerSyncStatusSerializer(LearnerSyncStatusSerializer):
    """
    `SapSuccessFactorsLearnerDataTransmissionAudit` sync-status serializer
    """

    class Meta:
        model = SapSuccessFactorsLearnerDataTransmissionAudit
        fields = LearnerSyncStatusSerializer.Meta.fields

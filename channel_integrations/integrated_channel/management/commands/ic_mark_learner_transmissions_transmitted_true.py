
"""
Mark already transmitted LearnerDataTransmission as is_trasmitted=True for all integrated channels
"""

from logging import getLogger

from django.apps import apps
from django.core.management.base import BaseCommand

from channel_integrations.integrated_channel.management.commands import IntegratedChannelCommandMixin

LOGGER = getLogger(__name__)


class Command(IntegratedChannelCommandMixin, BaseCommand):
    """
    Mark already transmitted LearnerDataTransmission as is_trasmitted=True for all integrated channels
    """

    def handle(self, *args, **options):
        """
        Mark already transmitted LearnerDataTransmission as is_trasmitted=True
        """
        channel_learner_audit_models = [
            ('moodle_channel', 'MoodleLearnerDataTransmissionAudit'),
            ('blackboard_channel', 'BlackboardLearnerDataTransmissionAudit'),
            ('blackboard_channel', 'BlackboardLearnerAssessmentDataTransmissionAudit'),
            ('canvas_channel', 'CanvasLearnerDataTransmissionAudit'),
            ('degreed2_channel', 'Degreed2LearnerDataTransmissionAudit'),
            ('sap_success_factors_channel', 'SapSuccessFactorsLearnerDataTransmissionAudit'),
            ('cornerstone_channel', 'CornerstoneLearnerDataTransmissionAudit'),
            ('canvas_channel', 'CanvasLearnerAssessmentDataTransmissionAudit'),
        ]
        for app_label, model_name in channel_learner_audit_models:
            model_class = apps.get_model(app_label=app_label, model_name=model_name)
            LOGGER.info(
                f'Started: setting {model_name}.is_transmitted set to True'
            )
            model_class.objects.filter(
                error_message='',
                status__lt=400,
            ).update(is_transmitted=True)

            LOGGER.info(
                f'Finished: setting {model_name}.is_transmitted set to True'
            )

"""
Transmits consenting enterprise learner data to the integrated channels.
"""

from django.contrib import auth
from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import gettext as _
from enterprise.models import EnterpriseCourseEnrollment

from channel_integrations.integrated_channel.management.commands import IntegratedChannelCommandMixin
from channel_integrations.integrated_channel.tasks import transmit_learner_data

User = auth.get_user_model()


class Command(IntegratedChannelCommandMixin, BaseCommand):
    """
    Management command which transmits learner course completion data to the IntegratedChannel(s) configured for the
    given EnterpriseCustomer.

    Collect the enterprise learner data for enrollments with data sharing consent, and transmit each to the
    EnterpriseCustomer's configured IntegratedChannel(s).
    """
    help = _('''
    Transmit Enterprise learner course completion data for the given EnterpriseCustomer.
    ''')
    stealth_options = ('enterprise_customer_slug', 'user1', 'user2')

    def add_arguments(self, parser):
        """
        Add required --api_user argument to the parser.
        """
        parser.add_argument(
            '--api_user',
            dest='api_user',
            required=True,
            metavar='LMS_API_USERNAME',
            help=_('Username of a user authorized to fetch grades from the LMS API.'),
        )
        parser.add_argument(
            '--enterprise_enrollment_id',
            dest='enterprise_enrollment_id',
            type=int,
            default=None,
            metavar='ENTERPRISE_COURSE_ENROLLMENT_ID',
            help=_('Transmit learner data for only this EnterpriseCourseEnrollment id.'),
        )
        parser.add_argument(
            '--force',
            dest='force_transmit',
            action='store_true',
            default=False,
            help=_('Force transmit learner data for the targeted enrollment even if it was already transmitted.'),
        )
        super().add_arguments(parser)

    def handle(self, *args, **options):
        """
        Transmit the learner data for the EnterpriseCustomer(s) to the active integration channels.
        """
        # Ensure that we were given an api_user name, and that User exists.
        api_username = options['api_user']
        enterprise_enrollment_id = options.get('enterprise_enrollment_id')
        force_transmit = options.get('force_transmit', False)

        try:
            User.objects.get(username=api_username)
        except User.DoesNotExist as no_user_error:
            raise CommandError(
                _('A user with the username {username} was not found.').format(username=api_username)
            ) from no_user_error

        if force_transmit and not enterprise_enrollment_id:
            raise CommandError(_('The --force flag requires --enterprise_enrollment_id.'))

        if enterprise_enrollment_id and not EnterpriseCourseEnrollment.objects.filter(id=enterprise_enrollment_id).exists():
            raise CommandError(
                _('Enterprise course enrollment id {enrollment_id} was not found.').format(
                    enrollment_id=enterprise_enrollment_id
                )
            )

        # Transmit the learner data to each integrated channel
        for integrated_channel in self.get_integrated_channels(options):
            # NOTE pass arguments as named kwargs for use in lock key
            task_kwargs = {
                'username': api_username,
                'channel_code': integrated_channel.channel_code(),
                'channel_pk': integrated_channel.pk,
            }

            if enterprise_enrollment_id is not None:
                task_kwargs['enterprise_enrollment_id'] = enterprise_enrollment_id
            if force_transmit:
                task_kwargs['force_transmit'] = True

            transmit_learner_data.delay(**task_kwargs)

"""
Third-party-auth pipeline steps.
"""
import logging

import waffle  # pylint: disable=invalid-django-waffle-import

from channel_integrations.integrated_channel.services.org_group_sync_service import sync_learner_budget_group

log = logging.getLogger(__name__)

ENABLE_TPA_ORG_GROUP_LOGIN_SYNC_SWITCH = 'enable_tpa_org_group_login_sync'

PIPELINE_STEP_PATH = 'channel_integrations.integrated_channel.pipeline.sync_tpa_budget_group'
PLATFORM_PIPELINE_ANCHOR_STEP_PATH = 'common.djangoapps.third_party_auth.pipeline.ensure_redirect_url_is_safe'


def sync_tpa_budget_group(backend, user, **kwargs):
    """
    Pipeline entry point: sync the logging-in learner's EnterpriseGroup membership to the
    Learner Credit budget group mapped to the org they logged in under.

    Args:
        backend: The class handling the SSO interaction (SAML, OAuth, etc)
        user: The user object in the process of being logged in with
        **kwargs: Any remaining pipeline variables

    Never raises - a bug here must never be able to block a login for any customer.
    """
    if not waffle.switch_is_active(ENABLE_TPA_ORG_GROUP_LOGIN_SYNC_SWITCH):
        return

    try:
        from enterprise.tpa_pipeline import get_enterprise_customer_for_running_pipeline  # pylint: disable=import-outside-toplevel

        request = backend.strategy.request
        pipeline = {'backend': backend.name, 'kwargs': kwargs}
        enterprise_customer = get_enterprise_customer_for_running_pipeline(request, pipeline)
        if enterprise_customer is None:
            return

        sync_learner_budget_group(user, enterprise_customer)
    except Exception as e:  # pylint: disable=broad-exception-caught
        log.warning(
            f'[OrgGroupSync] Error resolving enterprise customer for user {getattr(user, "id", None)} '
            f'while syncing budget group: {e}',
            exc_info=True,
        )


def register_pipeline_steps():
    """
    Register all `channel_integrations` pipeline steps.
    """
    try:
        from django.conf import settings  # pylint: disable=import-outside-toplevel

        pipeline = getattr(settings, 'SOCIAL_AUTH_PIPELINE', None)
        if pipeline is None:
            return
        if PIPELINE_STEP_PATH in pipeline:
            return
        if PLATFORM_PIPELINE_ANCHOR_STEP_PATH in pipeline:
            pipeline.insert(pipeline.index(PLATFORM_PIPELINE_ANCHOR_STEP_PATH) + 1, PIPELINE_STEP_PATH)
        else:
            pipeline.append(PIPELINE_STEP_PATH)
        log.info(f'[OrgGroupSync] Registered {PIPELINE_STEP_PATH} in SOCIAL_AUTH_PIPELINE')
    except Exception as e:  # pylint: disable=broad-exception-caught
        log.error(f'[OrgGroupSync] Error registering pipeline step: {e}', exc_info=True)

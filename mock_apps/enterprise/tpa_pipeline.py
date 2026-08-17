class SocialAuth:
    email = ''


def get_user_from_social_auth(providers, sap_student_id, enterprise_customer):
    return SocialAuth()


def get_sso_provider(request, pipeline):  # pylint: disable=unused-argument
    """
    Minimal stand-in for edx-enterprise's real tpa_pipeline.get_sso_provider, which resolves the
    provider id via edx-platform's third_party_auth Registry (not available in this repo's test
    environment). Falls back directly to the `tpa_hint` query param that the real function also
    falls back to when no pipeline is running.
    """
    return request.GET.get('tpa_hint')


def get_enterprise_customer_for_sso(sso_provider_id):
    """
    Minimal stand-in for edx-enterprise's real tpa_pipeline.get_enterprise_customer_for_sso.
    """
    from enterprise.models import EnterpriseCustomer

    try:
        return EnterpriseCustomer.objects.get(
            enterprise_customer_identity_providers__provider_id=sso_provider_id
        )
    except EnterpriseCustomer.DoesNotExist:
        return None


def get_enterprise_customer_for_running_pipeline(request, pipeline):
    """
    Minimal stand-in for edx-enterprise's real tpa_pipeline.get_enterprise_customer_for_running_pipeline.
    """
    return get_enterprise_customer_for_sso(get_sso_provider(request, pipeline))


def get_user_social_auth(user, enterprise_customer):
    """
    Minimal stand-in for edx-enterprise's real tpa_pipeline.get_user_social_auth, which relies on
    edx-platform's third_party_auth Registry (not available in this repo's test environment).

    Approximates the same intent - disambiguate between multiple UserSocialAuth rows for a user by
    preferring one whose `uid` is prefixed with one of the enterprise customer's configured IdP
    provider_ids (mirroring the `provider_slug:external_id` uid convention used by tpa-saml), and
    falling back to the first UserSocialAuth row for the user otherwise.
    """
    from social_django.models import UserSocialAuth

    provider_ids = list(
        enterprise_customer.enterprise_customer_identity_providers.values_list('provider_id', flat=True)
    )
    for provider_id in provider_ids:
        social_auth = UserSocialAuth.objects.filter(user=user, uid__startswith=f'{provider_id}:').first()
        if social_auth:
            return social_auth

    return UserSocialAuth.objects.filter(user=user).first()

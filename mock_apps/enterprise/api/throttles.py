from rest_framework.throttling import UserRateThrottle

SERVICE_USER_SCOPE = 'service_user'


class ServiceUserThrottle(UserRateThrottle):
    """
    A throttle allowing the service user to override rate limiting.
    """

    def get_scope(self):
        """
        Get the scope of the throttle.

        Returns:
            str: The scope of the throttle.
        """
        return SERVICE_USER_SCOPE

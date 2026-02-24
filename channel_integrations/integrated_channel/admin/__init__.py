"""
Admin site configurations for integrated channel's Content Metadata Transmission table.
"""

from django.contrib import admin

from channel_integrations.integrated_channel.models import (
    ApiResponseRecord,
    ContentMetadataItemTransmission,
    EnterpriseWebhookConfiguration,
    IntegratedChannelAPIRequestLogs,
    WebhookTransmissionQueue,
)
from channel_integrations.utils import get_enterprise_customer_from_enterprise_enrollment


class BaseLearnerDataTransmissionAuditAdmin(admin.ModelAdmin):
    """
    Base admin class to hold commonly used methods across integrated channel admin views
    """
    def enterprise_customer_name(self, obj):
        """
        Returns: the name for the attached EnterpriseCustomer or None if customer object does not exist.
        Args:
            obj: The instance of Django model being rendered with this admin form.
        """
        ent_customer = get_enterprise_customer_from_enterprise_enrollment(obj.enterprise_course_enrollment_id)
        return ent_customer.name if ent_customer else None


@admin.action(description='Clear remote_deleted_at on ContentMetadataItemTransmission item(s)')
def clear_remote_deleted_at(modeladmin, request, queryset):  # pylint: disable=unused-argument
    queryset.update(remote_deleted_at=None)


@admin.register(ContentMetadataItemTransmission)
class ContentMetadataItemTransmissionAdmin(admin.ModelAdmin):
    """
    Admin for the ContentMetadataItemTransmission audit table
    """
    list_display = (
        'enterprise_customer',
        'integrated_channel_code',
        'content_id',
        'remote_deleted_at',
        'modified'
    )

    search_fields = (
        'enterprise_customer__name',
        'enterprise_customer__uuid',
        'integrated_channel_code',
        'content_id'
    )

    raw_id_fields = (
        'enterprise_customer',
    )

    readonly_fields = [
        'api_record',
        'api_response_status_code',
        'friendly_status_message',
    ]

    actions = [
        clear_remote_deleted_at,
    ]

    list_per_page = 1000


@admin.register(ApiResponseRecord)
class ApiResponseRecordAdmin(admin.ModelAdmin):
    """
    Admin for the ApiResponseRecord table
    """
    list_display = (
        'id',
        'status_code'
    )

    search_fields = (
        'id',
        'status_code'
    )

    readonly_fields = (
        'status_code',
        'body'
    )

    list_per_page = 1000


@admin.register(IntegratedChannelAPIRequestLogs)
class IntegratedChannelAPIRequestLogAdmin(admin.ModelAdmin):
    """
    Django admin model for IntegratedChannelAPIRequestLogs.
    """

    list_display = [
        "endpoint",
        "enterprise_customer_id",
        "time_taken",
        "status_code",
    ]
    search_fields = [
        "enterprise_customer__name__icontains",
        "enterprise_customer__uuid__iexact",
        "enterprise_customer_configuration_id__iexact",
        "endpoint__icontains",
    ]
    readonly_fields = [
        "status_code",
        "enterprise_customer",
        "enterprise_customer_configuration_id",
        "endpoint",
        "time_taken",
        "response_body",
        "payload",
    ]
    list_filter = ('status_code',)

    list_per_page = 20

    def get_queryset(self, request):
        """
        Optimize queryset by selecting related 'enterprise_customer' and limiting fields.
        """
        queryset = super().get_queryset(request)
        return queryset.select_related('enterprise_customer').only(
            'id',
            'endpoint',
            'enterprise_customer_id',
            'time_taken',
            'status_code',
            'enterprise_customer__name',
            'enterprise_customer__uuid',
            'enterprise_customer_configuration_id'
        )

    class Meta:
        model = IntegratedChannelAPIRequestLogs


@admin.register(EnterpriseWebhookConfiguration)
class EnterpriseWebhookConfigurationAdmin(admin.ModelAdmin):
    """
    Django admin for EnterpriseWebhookConfiguration.
    """
    list_display = (
        'enterprise_customer',
        'region',
        'webhook_url',
        'active',
        'created',
        'modified',
    )

    search_fields = (
        'enterprise_customer__name',
        'enterprise_customer__uuid',
        'region',
        'webhook_url',
    )

    list_filter = (
        'active',
        'region',
    )

    raw_id_fields = (
        'enterprise_customer',
    )

    readonly_fields = (
        'created',
        'modified',
    )

    fieldsets = (
        ('Enterprise Customer', {
            'fields': ('enterprise_customer', 'region', 'active')
        }),
        ('Webhook Configuration', {
            'fields': ('webhook_url', 'webhook_timeout_seconds', 'webhook_retry_attempts', 'max_requests_per_minute')
        }),
        ('OAuth2 Authentication (Recommended)', {
            'fields': (
                'token_api_url', 'decrypted_client_id', 'decrypted_client_secret', 'provider_name'
            ),
            'description': (
                'Configure OAuth2 client credentials to dynamically fetch bearer tokens '
                '(e.g., for Skillsoft).'
            )
        }),
        ('Legacy Authentication', {
            'fields': ('webhook_auth_token',),
            'classes': ('collapse',),
            'description': 'Deprecated: Use OAuth2 authentication instead of static tokens.'
        }),
        ('Event Processing', {
            'fields': ('enrollment_events_processing',)
        }),
        ('Timestamps', {
            'fields': ('created', 'modified'),
            'classes': ('collapse',)
        }),
    )

    list_per_page = 50


@admin.register(WebhookTransmissionQueue)
class WebhookTransmissionQueueAdmin(admin.ModelAdmin):
    """
    Django admin for WebhookTransmissionQueue.
    """
    list_display = (
        'id',
        'enterprise_customer',
        'user_id',
        'user_region',
        'status',
        'attempt_count',
        'created',
        'last_attempt_at',
    )

    search_fields = (
        'enterprise_customer__name',
        'enterprise_customer__uuid',
        'user_id',
        'user_region',
    )

    list_filter = (
        'status',
        'user_region',
        'created',
    )

    raw_id_fields = (
        'enterprise_customer',
    )

    readonly_fields = (
        'created',
        'modified',
        'last_attempt_at',
    )

    list_per_page = 100

    def has_add_permission(self, request):
        """
        Disable manual creation of queue items via admin.
        Queue items should be created automatically by signal handlers.
        """
        return False

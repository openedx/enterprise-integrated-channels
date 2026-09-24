# Generated migration for TpaOrgAllowlist model

import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "channel_integration",
            "0009_remove_enterprisewebhookconfiguration_webhook_auth_token_and_more",
        ),
        ("enterprise", "__first__"),
    ]

    operations = [
        migrations.CreateModel(
            name="TpaOrgAllowlist",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "tpa_org_id",
                    models.CharField(
                        help_text="Org UUID as asserted by the IdP in the SAML attribute",
                        max_length=255,
                    ),
                ),
                (
                    "demo_account",
                    models.BooleanField(
                        default=False,
                        help_text="Whether this is a demo/trial organisation",
                    ),
                ),
                (
                    "enterprise_customer",
                    models.ForeignKey(
                        help_text="Enterprise customer this org is permitted to access",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tpa_org_allowlist",
                        to="enterprise.enterprisecustomer",
                    ),
                ),
            ],
            options={
                "verbose_name": "TPA Org Allowlist Entry",
                "verbose_name_plural": "TPA Org Allowlist Entries",
                "app_label": "channel_integration",
            },
        ),
        migrations.AddConstraint(
            model_name="tpaorgallowlist",
            constraint=models.UniqueConstraint(
                fields=["enterprise_customer", "tpa_org_id"],
                name="unique_tpa_org_per_enterprise",
            ),
        ),
    ]

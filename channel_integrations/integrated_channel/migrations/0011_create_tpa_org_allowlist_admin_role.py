"""
Data migration to ensure the tpa_org_allowlist_admin SystemWideEnterpriseRole exists.
"""
from django.db import migrations


def create_tpa_org_allowlist_admin_role(apps, schema_editor):
    """Create the tpa_org_allowlist_admin role if it does not already exist."""
    SystemWideEnterpriseRole = apps.get_model('enterprise', 'SystemWideEnterpriseRole')
    SystemWideEnterpriseRole.objects.get_or_create(name='tpa_org_allowlist_admin')


def delete_tpa_org_allowlist_admin_role(apps, schema_editor):
    """Remove the tpa_org_allowlist_admin role (reverse migration)."""
    SystemWideEnterpriseRole = apps.get_model('enterprise', 'SystemWideEnterpriseRole')
    SystemWideEnterpriseRole.objects.filter(name='tpa_org_allowlist_admin').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('channel_integration', '0010_tpaorgallowlist'),
        ('enterprise', '__first__'),
    ]

    operations = [
        migrations.RunPython(
            create_tpa_org_allowlist_admin_role,
            reverse_code=delete_tpa_org_allowlist_admin_role,
        ),
    ]

"""
Migration to add grade_assignment_cmid to MoodleEnterpriseCustomerConfiguration.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('moodle_channel', '0003_alter_moodleenterprisecustomerconfiguration_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='moodleenterprisecustomerconfiguration',
            name='grade_assignment_cmid',
            field=models.IntegerField(
                blank=True,
                null=True,
                verbose_name='Grade Assignment Course Module ID',
                help_text=(
                    'The Moodle course module ID (cmid) for the grade assignment activity. '
                    'When set, this takes precedence over grade_assignment_name, making grade sync '
                    'immune to activity renames. Find the cmid via Moodle Admin → Course → Activities '
                    'or the core_course_get_contents web service. Strongly recommended for production.'
                ),
            ),
        ),
    ]

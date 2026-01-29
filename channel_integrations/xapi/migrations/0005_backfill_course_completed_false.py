# Authored manually on 2026-02-03

from django.db import migrations


def backfill_course_completed_false(apps, schema_editor):
    """
    Backfill course_completed=False for existing XAPILearnerDataTransmissionAudit records
    that have course_completed=True AND completed_timestamp=None.

    This data migration complements the schema change in 0004 which set the default
    value of course_completed to False for new records going forward.
    """
    XAPILearnerDataTransmissionAudit = apps.get_model('xapi_channel', 'XAPILearnerDataTransmissionAudit')

    # Find records that incorrectly have course_completed=True but no completion timestamp
    affected_records = XAPILearnerDataTransmissionAudit.objects.filter(
        course_completed=True,
        completed_timestamp__isnull=True,
    )

    count = affected_records.count()
    if count > 0:
        # Update these records to have course_completed=False
        affected_records.update(course_completed=False)
        print(f"Updated {count} XAPILearnerDataTransmissionAudit record(s) to set course_completed=False")
    else:
        print("No XAPILearnerDataTransmissionAudit records needed updating")


class Migration(migrations.Migration):

    dependencies = [
        ('xapi_channel', '0004_alter_xapilearnerdatatransmissionaudit_course_completed'),
    ]

    operations = [
        # A reverse migration would not be possible since the forward migration destroys any
        # information needed to determine if the record was fixed by this data migration or created
        # correctly the first time.
        migrations.RunPython(backfill_course_completed_false),
    ]

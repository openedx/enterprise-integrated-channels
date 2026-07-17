# Generated migration for MariaDB UUID field conversion (Django 5.2)
"""
Migration to convert UUIDField from char(32) to uuid type for MariaDB compatibility.
"""

from django.db import migrations


def apply_mariadb_migration(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'mysql':
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
        if 'mariadb' not in version.lower():
            return
    with connection.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        cursor.execute("ALTER TABLE blackboard_channel_blackboardenterprisecustomerconfiguration MODIFY uuid uuid NOT NULL")
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")


def reverse_mariadb_migration(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'mysql':
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
        if 'mariadb' not in version.lower():
            return
    with connection.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        cursor.execute("ALTER TABLE blackboard_channel_blackboardenterprisecustomerconfiguration MODIFY uuid char(32) NOT NULL")
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")


class Migration(migrations.Migration):
    dependencies = [
        ('blackboard_channel', '0003_alter_blackboardenterprisecustomerconfiguration_id_and_more'),
    ]
    operations = [
        migrations.RunPython(
            code=apply_mariadb_migration,
            reverse_code=reverse_mariadb_migration,
        ),
    ]

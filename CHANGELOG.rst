Change Log
##########

..
   All enhancements and patches to channel_integrations will be documented
   in this file.  It adheres to the structure of https://keepachangelog.com/ ,
   but in reStructuredText instead of Markdown (for ease of incorporation into
   Sphinx documentation and the PyPI description).

   This project adheres to Semantic Versioning (https://semver.org/).

.. There should always be an "Unreleased" section for changes pending release.

Unreleased
**********

0.1.45 – 2026-02-26
*******************

* chore: upgrade python requirements

0.1.44 – 2026-02-25
*******************

* fix: renaming token field in EnterpriseWebhookConfiguration to be URL

0.1.43 – 2026-02-24
*******************

* build: upgrade pip-tools to version 7.5.3


0.1.42 – 2026-02-24
*******************

* fix: altering migration file to keep in sync

0.1.41 – 2026-02-24
*******************

* fix: setup changes for region specific Percipio integration

0.1.40 – 2026-02-17
*******************

* fix: alerting payload structure to match Skillsoft customer request

0.1.39 – 2026-02-11
*******************

* fix: changing payload structure to match Percipio documentation

0.1.38 – 2026-02-03
*******************

* chore: relax snowflake connector constraint

0.1.37 – 2026-02-03
*******************

Changed
=======

* Set course_completion=False and completed_timestamp=None for xAPI enrollment audit

0.1.36 – 2026-01-30
*******************

Changed
=======

* Optional features for webhook integration

0.1.35 – 2026-01-28
*******************

Changed
=======

* Add missing app_label to models


0.1.34 – 2026-01-27
*******************

Changed
=======

* Switched from consuming events via the event bus to listening to in process Django signals directly.

0.1.33 – 2026-01-20
*******************

Changed
=======

* chore: upgrade python requirements

0.1.32 – 2026-01-19
*******************

Changed
=======

* chore: Add Django>=4.2 constraint to support both Django 4.2 and 5.x
* fix: Constrain social-auth-app-django<5.5 for Django 4.2 compatibility

0.1.31 – 2026-01-19
*******************

Changed
=======

* chore: Update snowflake-connector-python from 3.7.0 to >=3.18.0,<4.0.0 for compatibility with edx-platform

0.1.30 – 2026-01-19
*******************

Added
=====

* feat: Add webhook learning time enrichment from Snowflake with dedicated Celery queue
* test: Add comprehensive test coverage for webhook task routing and branch conditions

0.1.29 – 2026-01-17
*******************

Added
=====

* chore: add logging to track sending course completion xAPI statements

0.1.28 – 2026-01-13
*******************

Fixed
=====

* fix: change webhook model id fields to AutoField for edx-platform compatibility

0.1.27 – 2026-01-12
*******************

Added
=====

* feat: Region-aware webhook system for enterprise course completion
* chore: add logging for track sending course completion xAPI statements

Fixed
=====

* fix: update pip-tools to 7.5.2
* See issue https://github.com/openedx/public-engineering/issues/440 for details.

[0.1.26] - 2026-01-08
*********************

Added
=====

0.1.25 – 2025-11-28
*******************

Added
=====

* feat: fetch SAP userid by remote_id_field_name

0.1.24 – 2025-11-24
*******************

Added
=====

*  Feat: Update Moodle serialiser to accomodates changes made in edx-enterprise

0.1.23 – 2025-10-30
*******************

Added
=====

*  Upgrade Python Requirements

0.1.22 – 2025-10-23
*******************

Added
=====

*  feat: Optimize data migration command by implementing bulk inserts for improved performance.
*  feat: Add management command to truncate non-empty destination tables before data migration.

0.1.21 – 2025-10-22
*******************

Added
=====

*  Upgrade Python Requirements
*  fix: Convert UUIDField columns to uuid type for MariaDB

0.1.20 – 2025-10-19
*******************

Added
=====

*  Upgrade Python Requirements

0.1.19 – 2025-10-09
*******************

Added
=====

*  Upgrade Python Requirements


0.1.18 – 2025-10-03
*******************

Added
=====

*  Upgrade Python Requirements


0.1.17 – 2025-09-26
*******************

Added
=====

*  Upgrade Python Requirements


0.1.16 – 2025-09-15
*******************

Added
=====

*  Enhances the migration command with customer-specific functionality to support targeted data migration during the integrated channels transition.


0.1.15 – 2025-09-01
*******************

Added
=====

*  Add explicit index naming for SAP SuccessFactors audit table and corresponding database migration.


0.1.14 – 2025-08-13
*******************

Added
=====

*  Upgrade Python Requirements


0.1.13 – 2025-07-23
*******************

Added
=====

*  Add ``__init__.py`` to ``api/v1/`` directory to ensure it is recognized as a package.


0.1.12 – 2025-07-22
*******************

Added
=====

*  Upgrade Python Requirements

0.1.11 – 2025-07-15
*******************

Added
=====

*  Update CHANGELOG and README


0.1.10 – 2025-07-15
*******************

Added
=====

*  Fix admin redirects for various channel integrations to use the correct app namespace.
*  Upgrade Python Requirements


0.1.9 – 2025-07-04
******************

Added
=====

*  Upgrade Python Requirements


0.1.8 – 2025-06-26
******************

Added
=====

*  fix ``test_migrations_are_in_sync`` test on edx-platform


0.1.7 – 2025-06-25
******************

Added
=====

*  add migrations for various channel integrations


0.1.6 – 2025-06-25
******************

Added
=====

*  Upgrade Python Requirements


0.1.5 – 2025-06-16
******************

Added
=====

*  Rename xAPI management commands to avoid conflicts with existing commands in edx-enterprise.


0.1.4 – 2025-06-11
******************

Added
=====

*  Added django52 support.


0.1.3 – 2025-06-10
******************

Added
=====

*  Add DB migrations against ``index_together`` changes.


0.1.2 – 2025-05-30
******************

Added
=====

* Added management command to copy data from legacy tables to new tables.
* Added ``(Experimental)`` tag to app name in the admin interface.

0.1.1 – 2025-05-20
******************

Added
=====

* Renamed jobs to avoid conflicts with existing jobs in edx-enterprise.


0.1.0 – 2025-01-16
******************

Added
=====

* First release on PyPI.
* Created ``mock_apps`` for testing purposes.
* Updated requirements in ``base.in`` and run ``make requirements``.
* Migrated ``integrated_channel`` app from edx-enterprise.

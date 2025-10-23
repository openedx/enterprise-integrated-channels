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

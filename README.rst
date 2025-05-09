enterprise-integrated-channels
##############################

|pypi-badge| |ci-badge| |codecov-badge| |doc-badge| |pyversions-badge|
|license-badge| |status-badge|

Purpose
*******

An integrated channel is an abstraction meant to represent a third-party system which provides an API that can be used to transmit EdX data to the third-party system. The most common example of such a third-party system is an enterprise-level learning management system (LMS). LMS users are able to discover content made available by many different content providers and manage the learning outcomes that are produced by interaction with the content providers. In such a scenario, EdX would be the content provider while a system like SAP SuccessFactors would be the integrated channel.


Getting Started with Development
********************************

Please see the Open edX documentation for `guidance on Python development`_ in this repo.

.. _guidance on Python development: https://docs.openedx.org/en/latest/developers/how-tos/get-ready-for-python-dev.html


Getting Help
************

Documentation
=============

Start by going through `the documentation`_.  If you need more help see below.

.. _the documentation: https://github.com/openedx/enterprise-integrated-channels/blob/main/channel_integrations/README.md

(TODO: `Set up documentation <https://openedx.atlassian.net/wiki/spaces/DOC/pages/21627535/Publish+Documentation+on+Read+the+Docs>`_)

More Help
=========

If you're having trouble, we have discussion forums at
https://discuss.openedx.org where you can connect with others in the
community.

Our real-time conversations are on Slack. You can request a `Slack
invitation`_, then join our `community Slack workspace`_.

For anything non-trivial, the best path is to open an issue in this
repository with as many details about the issue you are facing as you
can provide.

https://github.com/openedx/enterprise-integrated-channels/issues

For more information about these options, see the `Getting Help <https://openedx.org/getting-help>`__ page.

.. _Slack invitation: https://openedx.org/slack
.. _community Slack workspace: https://openedx.slack.com/

License
*******

The code in this repository is licensed under the AGPL 3.0 unless
otherwise noted.

Please see `LICENSE.txt <LICENSE.txt>`_ for details.

Contributing
************

Contributions are very welcome.
Please read `How To Contribute <https://openedx.org/r/how-to-contribute>`_ for details.

This project is currently accepting all types of contributions, bug fixes,
security fixes, maintenance work, or new features.  However, please make sure
to discuss your new feature idea with the maintainers before beginning development
to maximize the chances of your change being accepted.
You can start a conversation by creating a new issue on this repo summarizing
your idea.

The Open edX Code of Conduct
****************************

All community members are expected to follow the `Open edX Code of Conduct`_.

.. _Open edX Code of Conduct: https://openedx.org/code-of-conduct/

People
******

The assigned maintainers for this component and other project details may be
found in `Backstage`_. Backstage pulls this data from the ``catalog-info.yaml``
file in this repo.

.. _Backstage: https://backstage.openedx.org/catalog/default/component/enterprise-integrated-channels

Reporting Security Issues
*************************

Please do not report security issues in public. Please email security@openedx.org.

.. |pypi-badge| image:: https://img.shields.io/pypi/v/enterprise-integrated-channels.svg
    :target: https://pypi.python.org/pypi/enterprise-integrated-channels/
    :alt: PyPI

.. |ci-badge| image:: https://github.com/openedx/enterprise-integrated-channels/workflows/Python%20CI/badge.svg?branch=main
    :target: https://github.com/openedx/enterprise-integrated-channels/actions
    :alt: CI

.. |codecov-badge| image:: https://codecov.io/github/openedx/enterprise-integrated-channels/coverage.svg?branch=main
    :target: https://codecov.io/github/openedx/enterprise-integrated-channels?branch=main
    :alt: Codecov

.. |doc-badge| image:: https://readthedocs.org/projects/enterprise-integrated-channels/badge/?version=latest
    :target: https://docs.openedx.org/projects/enterprise-integrated-channels
    :alt: Documentation

.. |pyversions-badge| image:: https://img.shields.io/pypi/pyversions/enterprise-integrated-channels.svg
    :target: https://pypi.python.org/pypi/enterprise-integrated-channels/
    :alt: Supported Python versions

.. |license-badge| image:: https://img.shields.io/github/license/openedx/enterprise-integrated-channels.svg
    :target: https://github.com/openedx/enterprise-integrated-channels/blob/main/LICENSE.txt
    :alt: License

.. TODO: Choose one of the statuses below and remove the other status-badge lines.
.. |status-badge| image:: https://img.shields.io/badge/Status-Experimental-yellow
.. .. |status-badge| image:: https://img.shields.io/badge/Status-Maintained-brightgreen
.. .. |status-badge| image:: https://img.shields.io/badge/Status-Deprecated-orange
.. .. |status-badge| image:: https://img.shields.io/badge/Status-Unsupported-red

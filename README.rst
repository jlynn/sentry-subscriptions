sentry-subscriptions
====================

A plugin for Sentry which allows email notifications to be routed based upon the source of an exception.

Install
-------

Install the package via ``pip``::

    pip install sentry-subscriptions

Project Configuration
---------------------

sentry-subscriptions is configured on per-project basis. A subscription is in the format of:

::

    <module_pattern> <email_list>

Example configuration:

::

    app.views.* front-end@company.com
    app.models.* john@company.com,chris@company.com

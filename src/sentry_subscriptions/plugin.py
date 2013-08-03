from django import forms
from django.core.mail import EmailMultiAlternatives
from django.core.urlresolvers import reverse
from django.core.validators import email_re
from django.core.validators import ValidationError
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from sentry.plugins import Plugin
from sentry.plugins.sentry_mail.models import UnicodeSafePynliner
from sentry.utils.http import absolute_uri

import fnmatch
import sentry_subscriptions


class SubscriptionField(forms.CharField):
    '''Custom field for converting stored dictionary value to TextArea string'''

    def prepare_value(self, value):
        '''Convert dict to string'''

        if isinstance(value, dict):
            value = self.to_text(value)

        return value

    def to_text(self, value):

        subscription_lines = []
        for pattern, emails in value.iteritems():
            subscription_lines.append('%s %s' % (pattern, ','.join(emails)))

        return '\n'.join(subscription_lines)


class SubscriptionOptionsForm(forms.Form):
    subscriptions = SubscriptionField(label=_('Subscriptions'),
        widget=forms.Textarea(attrs={'class': 'span6', 'placeholder': 'module.submodule.* example@domain.com,foo@bar.com'}),
        help_text=_('Enter one subscription per line in the format of <module patter> <notification emails>.'))

    def clean_subscriptions(self):

        value = self.cleaned_data['subscriptions']
        subscription_lines = value.strip().splitlines()
        subscriptions = {}

        for subscription_line in subscription_lines:
            tokens = subscription_line.split(' ')
            if len(tokens) != 2:
                raise ValidationError('Invalid subscription specification: %s. Must specify a module pattern and list of emails' % subscription_line)

            pattern = self.clean_pattern(tokens[0])
            emails = self.clean_emails(tokens[1])

            if pattern in subscriptions:
                raise ValidationError('Duplicate subscription: %s' % subscription_line)

            subscriptions[pattern] = emails

        return subscriptions

    def clean_pattern(self, pattern):
        return pattern

    def clean_emails(self, emails):
        email_values = emails.split(',')

        for email in email_values:
            if not email_re.match(email):
                raise ValidationError('%s is not a valid email address' % email)

        return email_values


class SubscriptionsPlugin(Plugin):

    author = 'John Lynn'
    author_url = 'https://github.com/jlynn/sentry-subscriptions'
    version = sentry_subscriptions.VERSION
    description = 'Enable email subscriptions to exceptions'

    slug = 'subscriptions'
    title = _('Subscriptions')
    conf_title = title
    conf_key = 'subscriptions'
    project_conf_form = SubscriptionOptionsForm

    def is_configured(self, project, **kwargs):
        return bool(self.get_option('subscriptions', project))

    def _send_mail(self, send_to, subject, body, html_body=None, project=None, fail_silently=False, headers=None):

        msg = EmailMultiAlternatives(
            '[Sentry Subscription] %s' % subject,
            body,
            settings.SERVER_EMAIL,
            send_to,
            headers=headers)
        if html_body:
            msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=fail_silently)

    def get_notification_settings_url(self):
        return absolute_uri(reverse('sentry-account-settings-notifications'))

    def send_notification(self, emails, group, event, fail_silently=False):
        '''Shamelessly adapted from sentry.plugins.sentry_mail.models.MailProcessor'''

        project = group.project

        interface_list = []
        for interface in event.interfaces.itervalues():
            body = interface.to_string(event)
            if not body:
                continue
            interface_list.append((interface.get_title(), body))

        subject = '[%s] %s %s: %s' % (project.name.encode('utf-8'), event.get_level_display().upper().encode('utf-8'),
            event.culprit.encode('utf-8'), event.error().encode('utf-8').splitlines()[0])

        link = group.get_absolute_url()

        body = render_to_string('sentry/emails/error.txt', {
            'group': group,
            'event': event,
            'link': link,
            'interfaces': interface_list,
        })
        html_body = UnicodeSafePynliner().from_string(render_to_string('sentry/emails/error.html', {
            'group': group,
            'event': event,
            'link': link,
            'interfaces': interface_list,
            'settings_link': self.get_notification_settings_url(),
        })).run()
        headers = {
            'X-Sentry-Logger': event.logger,
            'X-Sentry-Logger-Level': event.get_level_display(),
            'X-Sentry-Project': project.name,
            'X-Sentry-Server': event.server_name,
        }

        self._send_mail(
            send_to=emails,
            subject=subject,
            body=body,
            html_body=html_body,
            project=project,
            fail_silently=fail_silently,
            headers=headers,
        )

    def should_notify(self, event, is_new):

        if is_new:
            return True

        if event.group:
            count = event.group.times_seen
            if count <= 100 and count % 10 == 0:
                return True
            if count <= 1000 and count % 100 == 0:
                return True
            elif count % 1000 == 0:
                return True

        return False

    def get_matches(self, event):
        subscriptions = self.get_option('subscriptions', event.project)

        notifications = []

        for pattern, emails in subscriptions.iteritems():
            if fnmatch.fnmatch(event.culprit, pattern):
                    notifications += emails

        return notifications

    def post_process(self, group, event, is_new, is_sample, **kwargs):

        if not event.culprit:
            return

        if not self.is_configured(group.project):
            return

        if self.should_notify(event, is_new):
            emails_to_notify = self.get_matches(event)
            self.send_notification(emails_to_notify, group, event)

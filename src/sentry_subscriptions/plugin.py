from django import forms
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _
from sentry.conf import settings
from sentry.plugins import Plugin

from pynliner import Pynliner

import fnmatch
import sentry_subscriptions


class UnicodeSafePynliner(Pynliner):
    def _get_output(self):
        """
        Generate Unicode string of `self.soup` and set it to `self.output`

        Returns self.output
        """
        self.output = unicode(self.soup)
        return self.output


class SubscriptionOptionsForm(forms.Form):
    subscriptions = forms.CharField(label=_('Subscriptions'),
        widget=forms.Textarea(attrs={'class': 'span6', 'placeholder': 'module.submodule.* example@email.com,foo@bar.com'}),
        help_text=_('Enter one subscription per line in the format of <module patter> <notification emails>.'))


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

    def send_notification(self, emails, group, event, fail_silently=False):
        project = group.project

        interface_list = []
        for interface in event.interfaces.itervalues():
            body = interface.to_string(event)
            if not body:
                continue
            interface_list.append((interface.get_title(), body))

        subject = '[%s] %s: %s' % (project.name.encode('utf-8'), event.get_level_display().upper().encode('utf-8'),
            event.error().encode('utf-8').splitlines()[0])

        link = '%s/%s/group/%d/' % (settings.URL_PREFIX, group.project.slug, group.id)

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
        subscriptions = self.get_option('subscriptions', event.project).strip().splitlines()

        notifications = []

        for subscription in subscriptions:
            pattern, emails = subscription.split(' ')
            if fnmatch.fnmatch(event.culprit, pattern):
                notifications += emails.split(',')
        
        return notifications

    def post_process(self, group, event, is_new, is_sample, **kwargs):

        if not event.culprit:
            return

        if not self.is_configured(group.project):
            return

        if self.should_notify(event, is_new):
            emails_to_notify = self.get_matches(event)
            self.send_notification(emails_to_notify, group, event)

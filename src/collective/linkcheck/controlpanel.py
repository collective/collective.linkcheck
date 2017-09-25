# -*- coding: utf-8 -*-
from Products.CMFCore.utils import getToolByName
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.statusmessages.interfaces import IStatusMessage
from ZPublisher.HTTPResponse import status_reasons
from collective.linkcheck import MessageFactory as _
from collective.linkcheck.interfaces import ISettings
from plone import api
from plone.app.registry.browser import controlpanel
from plone.keyring.interfaces import IKeyManager
from plone.memoize.instance import memoize
from plone.registry.interfaces import IRegistry
from plone.z3cform import layout
from z3c.form import button
from z3c.form import field
from z3c.form import group
from z3c.form import widget
from zExceptions import Redirect
from zope.component import getUtility
from zope.schema import Field

import datetime
import hashlib
import logging
import time
import transaction
import urllib


logger = logging.getLogger("linkcheck.controlpanel")


def triage(status):
    """Categorize HTTP status codes in severities."""

    if status is None:
        return 4

    if status == 200:
        return 0

    if status >= 500 or status == 0:
        return 3

    if status >= 400:
        return 2

    return 1


class ReportWidget(widget.Widget):
    render = ViewPageTemplateFile("templates/report.pt")

    @property
    def count(self):
        registry = getUtility(IRegistry, context=self.form.context)
        try:
            settings = registry.forInterface(ISettings)
            return settings.report_urls_count
        except KeyError:
            logger.warn("settings not available; please reinstall.")
            return 20

    @classmethod
    def factory(cls, field, request):
        return widget.FieldWidget(field, cls(request))

    @property
    @memoize
    def action_url(self):
        return self.request.getURL()

    @property
    @memoize
    def portal_url(self):
        return self.form.context.portal_url()

    @property
    def auth(self):
        return self.form.__parent__.get_auth_token()

    @property
    def data(self):
        return self.form.__parent__.list_entries(self.count)

    @property
    def updated(self):
        return self.form.__parent__.get_modified_date()

    def crawling_data(self):
        return self.form.__parent__.crawling_data()


class ReportGroup(group.Group):
    label = _(u"Report")
    fields = field.Fields(
        field.Field(
            Field(
                __name__="table",
                title=_(u"Problems"),
                description=_(
                    u"This table lists the top URLs with a "
                    u"bad status. To retry a URL immediately, select "
                    u"\"Enqueue\". Each entry expands to display the "
                    u"pages that the link appeared on and the location in "
                    u"the HTML markup."
                    ),
                required=False
                ),
            mode="display", ignoreContext=True),
        )

    fields["table"].widgetFactory = ReportWidget.factory


class SettingsGroup(group.Group):
    label = _(u"Settings")
    fields = field.Fields(ISettings)


class ControlPanelEditForm(controlpanel.RegistryEditForm):
    schema = ISettings
    fields = field.Fields()
    groups = (ReportGroup, SettingsGroup, )

    label = _(u"Link validity")
    description = _(u"View report and configure operation.")

    buttons = button.Buttons()
    buttons += controlpanel.RegistryEditForm.buttons
    handlers = controlpanel.RegistryEditForm.handlers.copy()

    rss_template = ViewPageTemplateFile("templates/rss.pt")

    @property
    def tool(self):
        return getToolByName(self.context, 'portal_linkcheck')

    def update(self):
        url = self.request.get('enqueue')
        if url is not None:
            url = urllib.unquote_plus(url)
            self.tool.enqueue(url)
            transaction.commit()
            location = self.request.getURL()
            raise Redirect(location)

        url = self.request.get('remove')
        if url is not None:
            url = urllib.unquote_plus(url)
            self.tool.remove(url)
            transaction.commit()
            location = self.request.getURL()
            raise Redirect(location)

        super(ControlPanelEditForm, self).update()

    def get_auth_token(self):
        manager = getUtility(IKeyManager)
        secret = manager.secret()
        sha = hashlib.sha1(self.context.absolute_url())
        sha.update(secret)
        sha.update("RSS")
        return sha.hexdigest()

    def get_modified_date(self):
        return datetime.date.fromtimestamp(min(
            self.tool.index._p_mtime,
            self.tool.links._p_mtime,
            self.tool.checked._p_mtime,
            ))

    def list_entries(self, count=100):
        rows = []

        now = datetime.datetime.now()
        timestamp = int(time.mktime(now.timetuple()))

        entries = list(self.tool.checked.items())
        entries.sort(
            key=lambda (i, entry): (
                triage(None if i in self.tool.queue else entry[1]),
                entry[0]),
            reverse=True,
            )

        settings = self.getContent()

        for i, entry in entries:
            status = entry[1]

            # Skip entries with unknown status.
            if not status:
                continue

            # Break out of iteration when we reach a good status.
            if entry[1] == 200:
                break

            # Or hit the maximum row count.
            if len(rows) == count:
                break

            url = self.tool.links[i]
            age = timestamp - (entry[0] or timestamp)

            referers = filter(None, map(self.tool.links.get, entry[2]))[:settings.referers]  # noqa

            try:
                quoted_url = urllib.quote_plus(url)
            except KeyError:
                quoted_url = None

            rows.append({
                'url': url,
                'quoted_url': quoted_url,
                'age': age,
                'date': datetime.datetime.fromtimestamp(entry[0] or timestamp),
                'status': "%d %s" % (status, status_reasons.get(status, '')),
                'referers': referers,
                'queued': url in self.tool.queue,
                })

        return rows

    @button.buttonAndHandler(_(u"Clear and crawl"), name='crawl')
    def handleCrawl(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return

        self.tool.crawl()

        logger.info("crawled the site.")

        IStatusMessage(self.request).addStatusMessage(
            _(u"All site crawled."), "info")

    @button.buttonAndHandler(_(u"Clear"), name='clear')
    def handleClear(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return

        self.tool.clear()

        logger.info("database cleared.")

        IStatusMessage(self.request).addStatusMessage(
            _(u"All data cleared."), "info")

    @button.buttonAndHandler(_(u"Export as csv"), name='export_csv')
    def handleExportCSV(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return
        portal = api.portal.get()
        return self.request.response.redirect(
            portal.absolute_url() + '/@@linkcheck-export?export_type=csv')

    def RSS(self):
        body = self.rss_template()

        self.request.response.setHeader('Content-Type', 'application/rss+xml')
        self.request.response.setHeader(
            'Content-Disposition',
            'attachment; filename="linkcheck.rss"'
            )

        return body

    def crawling_data(self):
        uids = self.tool.crawl_queue._data
        catalog = api.portal.get_tool('portal_catalog')
        brains = catalog(UID=uids)
        return brains


ControlPanel = layout.wrap_form(
    ControlPanelEditForm,
    controlpanel.ControlPanelFormWrapper
    )

import time
import logging
import datetime
import transaction

from Products.CMFCore.utils import getToolByName
from Products.statusmessages.interfaces import IStatusMessage
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zExceptions import Redirect
from ZPublisher.HTTPResponse import status_reasons

from zope.schema import Field

from plone.memoize.instance import memoize
from plone.z3cform import layout
from plone.app.registry.browser import controlpanel

from collective.linkcheck.interfaces import ISettings
from collective.linkcheck import MessageFactory as _

from z3c.form import button
from z3c.form import field
from z3c.form import group
from z3c.form import widget


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

    count = 20

    @classmethod
    def factory(cls, field, request):
        return widget.FieldWidget(field, cls(request))

    @property
    @memoize
    def enqueue_url(self):
        return self.request.getURL()

    @property
    @memoize
    def portal_url(self):
        return self.form.context.portal_url()

    @property
    def data(self):
        tool = getToolByName(self.form.context, 'portal_linkcheck')

        count = self.count
        rows = []

        now = datetime.datetime.now()
        timestamp = int(time.mktime(now.timetuple()))

        entries = list(tool.checked.items())
        entries.sort(
            key=lambda (url, entry): (
                triage(None if url in tool.queue else entry[1]),
                entry[0]),
            reverse=True,
            )

        for url, entry in entries:
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

            age = timestamp - (entry[0] or timestamp)
            rows.append({
                'url': url,
                'age': age,
                'status': "%d %s" % (status, status_reasons.get(status, '')),
                'paths': entry[2],
                'referers': entry[3],
                'queued': url in tool.queue,
                })

        return rows


class ReportGroup(group.Group):
    label = _(u"Report")
    fields = field.Fields(
        field.Field(
            Field(
                __name__="table",
                title=_(u"Problems"),
                description=_(
                    u"This table lists the top ${count} URLs with a "
                    u"bad status. To retry a URL immediately, select "
                    u"\"Enqueue\". Each entry expands to display the "
                    u"pages that the link appeared on and the location in "
                    u"the HTML markup.",
                    mapping={'count': ReportWidget.count},
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

    @property
    def tool(self):
        return getToolByName(self.context, 'portal_linkcheck')

    def update(self):
        url = self.request.get('enqueue')
        if url is not None:
            self.tool.enqueue(url)
            transaction.commit()
            location = self.request.getURL()
            raise Redirect(location)

        super(ControlPanelEditForm, self).update()

    @button.buttonAndHandler(_(u"Clear"), name='clear')
    def handleSchedule(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return

        self.tool.clear()

        logger.info("database cleared.")

        IStatusMessage(self.request).addStatusMessage(
            _(u"All data cleared."), "info")


ControlPanel = layout.wrap_form(
    ControlPanelEditForm,
    controlpanel.ControlPanelFormWrapper
    )

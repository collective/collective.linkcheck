# -*- coding: utf-8 -*-
from Products.Five import BrowserView
from ZODB.POSException import ConflictError
from collective.linkcheck.parse import iter_links
from plone import api
from plone.app.layout.viewlets.common import ViewletBase

import datetime
import logging
import time
import transaction

logger = logging.getLogger("linkcheck.controlpanel")


class StatsViewlet(ViewletBase):
    available = True

    def __init__(self, *args):
        super(StatsViewlet, self).__init__(*args)

        try:
            self.tool = api.portal.get_tool('portal_linkcheck')
        except AttributeError:
            self.available = False

    @property
    def active_count(self):
        return len(self.tool.checked)

    @property
    def average_entropy(self):
        timestamps = set(
            entry[0] for entry in self.tool.checked.values()
            if entry[1] is not None
            )

        if not timestamps:
            return 0

        return round(float(len(self.tool.checked)) / len(timestamps))

    @property
    def queue_ratio(self):
        if not self.active_count:
            return 0

        ratio = round(100 * float(len(self.tool.queue)) / self.active_count)
        return int(ratio)


class CheckLinks(BrowserView):
    """Helper view to trigger link checks from the object context"""

    def __call__(self):
        """Based on collective.linkcheck.events.end_request"""
        context = self.context
        request = self.request

        tool = api.portal.get_tool('portal_linkcheck')
        response = request.response

        # Update the status of the present request.
        status = response.getStatus()

        # Compute path given the actual URL, relative to the site root.
        base_url = api.portal.get().absolute_url()

        # old way
        """
        actual_url = request.get('ACTUAL_URL', '')
        if not actual_url.startswith(base_url):
            return

        path = actual_url[len(base_url):]
        """
        path = '/' + '/'.join(context.getPhysicalPath()[2:])
        actual_url = context.absolute_url()
        tool.update(path, status)

        # for now we generate body by calling the object
        try:
            body = context()
        except Exception:
            logger.error(u'Problem when checking the page: {0}'.format(path))
            return

        hrefs = set()
        for href in iter_links(body):

            # Ignore anchors and javascript.
            if href.startswith('#') or href.startswith('javascript:'):
                continue

            # Ignore mailto links
            if href.startswith('mailto:'):
                continue

            # handle relative urls
            if href.startswith('.') or (
                    not href.startswith('/') and
                    '://' not in href):
                href = '/'.join((base_url, href))

            # Internal URLs are stored site-relative.
            if href.startswith(base_url):
                href = "/" + href[len(base_url) + 1:].rstrip("/")

            # Add trailing slash to bare domain.
            if href.startswith('http://') or href.startswith('https://'):
                if href.count('/') == 2:
                    href = href.rstrip('/') + '/'

            hrefs.add(href)

        # We want all the hyperlinks in the document to be checked unless
        # it's already in the queue or it has been checked recently.
        date = datetime.datetime.now() - datetime.timedelta(days=1)
        yesterday = int(time.mktime(date.timetuple()))

        # referer is nothing else than the actual_url. HTTP_HOST and PATH_INFO
        # give wrong URLs in VirtualHosting

        # Update link database
        tool.register(hrefs, actual_url, yesterday)

        # We always commit the transaction; if no changes were made, this
        # is a NOOP. Note that conflict errors are possible with
        # concurrent requests. We ignore them.
        try:
            transaction.commit()
        except ConflictError:
            transaction.abort()

    def render(self):
        return "OK"

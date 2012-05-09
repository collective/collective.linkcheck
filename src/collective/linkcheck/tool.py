import time
import datetime
import logging

from zc.queue import Queue
from zope.component import getUtility
from plone.registry.interfaces import IRegistry

from BTrees.OOBTree import OOBTree
from AccessControl.SecurityInfo import ClassSecurityInfo
from App.class_init import InitializeClass
from OFS.SimpleItem import SimpleItem
from Products.CMFCore.utils import registerToolInterface

from .interfaces import ILinkCheckTool
from .interfaces import ISettings

logger = logging.getLogger("linkcheck.events")


class LinkCheckTool(SimpleItem):
    security = ClassSecurityInfo()

    def __init__(self, id=None):
        super(LinkCheckTool, self).__init__(id)

        # This is the work queue; items in this queue are scheduled
        # for link validity check.
        self.queue = Queue()

        # This is the link database. It maps a hyperlink (string) to a
        # tuple (timestamp, status, paths, referers).
        self.checked = OOBTree()

    security.declarePrivate("clear")
    def clear(self):
        while True:
            try:
                self.queue.pull()
            except IndexError:
                break

        self.checked.clear()

    security.declarePrivate("enqueue")
    def enqueue(self, url):
        self.queue.put(url)
        entry = self.checked.get(url)
        if entry is not None:
            entry = None, entry[1], entry[2], entry[3]
            self.checked[url] = entry

    security.declarePrivate("register")
    def register(self, links, referer, timestamp):
        """Add or update link presence information.

        If a link has not been checked since the provided timestamp,
        it will be added to the queue (or if it is not in the
        database).
        """

        referers = set((referer, ))

        registry = getUtility(IRegistry, context=self.aq_parent)
        settings = registry.forInterface(ISettings)

        for href, paths in links:
            # If the hyperlink is not already in the work queue,
            # compare the provided timestamp to our database to see if
            # we need to check its validity. Note that internal links
            # are excempt if we're not using the publisher.
            entry = self.checked.get(href)
            if href not in self.queue:
                if entry is None or entry[0] < timestamp:
                    if settings.use_publisher or not href.startswith('/'):
                        self.queue.put(href)

            if entry is None:
                entry = None, None, paths, referers
            else:
                # If the provided paths are a subset of the already
                # seen paths, and if there is no new referer, we don't
                # issue an update.
                if paths <= entry[2] and referer in entry[3]:
                    continue

                entry = entry[0], entry[1], \
                        entry[2] | paths, entry[3] | referers

            self.checked[href] = entry

    security.declarePrivate("update")
    def update(self, href, status):
        """Update link status."""

        now = datetime.datetime.now()
        timestamp = int(time.mktime(now.timetuple()))

        entry = self.checked.get(href)
        if entry is None:
            self.checked[href] = timestamp, status, set(), set()
            return

        # If the status changed, we update the entry.
        if status != entry[1] or not entry[0]:

            # If the status was previously good, then we clear the
            # status. What this means is that we'll wait for the next
            # check to declare a bad status (it might be temporary).
            if entry[1] == 200:
                status = None

            self.checked[href] = timestamp, status, entry[2], entry[3]
            return


InitializeClass(LinkCheckTool)
registerToolInterface('portal_linkcheck', ILinkCheckTool)

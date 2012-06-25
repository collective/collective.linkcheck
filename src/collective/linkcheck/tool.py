import re
import time
import datetime
import logging

from zope.component import getUtility
from plone.registry.interfaces import IRegistry
from plone.memoize.volatile import cache

from BTrees.IOBTree import IOBTree
from BTrees.OIBTree import OIBTree
from BTrees.IIBTree import IISet

from AccessControl.SecurityInfo import ClassSecurityInfo
from App.class_init import InitializeClass
from OFS.SimpleItem import SimpleItem
from Products.CMFCore.utils import registerToolInterface

from .interfaces import ILinkCheckTool
from .interfaces import ISettings
from .queue import CompositeQueue

logger = logging.getLogger("linkcheck.events")


class LinkCheckTool(SimpleItem):
    security = ClassSecurityInfo()

    def __init__(self, id=None):
        super(LinkCheckTool, self).__init__(id)

        # This is the work queue; items in this queue are scheduled
        # for link validity check.
        self.queue = CompositeQueue()

        # This is the link database. It maps a hyperlink index to a
        # tuple (timestamp, status, paths, referers).
        self.checked = IOBTree()

        # Indexes
        self.index = OIBTree()
        self.links = IOBTree()

        # This is a counter that allows us to add new hyperlinks and
        # provide an indexc quickly.
        self.counter = 0

    security.declarePrivate("is_available")
    def is_available(self):
        return hasattr(self, 'index') and \
               hasattr(self, 'checked') and \
               hasattr(self, 'queue') and \
               hasattr(self, 'counter')

    security.declarePrivate("clear")
    def clear(self):
        while True:
            try:
                self.queue.pull()
            except IndexError:
                break

        self.checked.clear()
        self.index.clear()
        self.counter = 0

    security.declarePrivate("enqueue")
    def enqueue(self, url):
        index = self.index.get(url)

        if index is None:
            index = self.store(url)
        else:
            entry = self.checked.get(-1 if index is None else index)
            entry = None, entry[1], entry[2], entry[3]
            self.checked[index] = entry

        self.queue.put(index)
        return index

    security.declarePrivate("register")
    def register(self, links, referer, timestamp):
        """Add or update link presence information.

        If a link has not been checked since the provided timestamp,
        it will be added to the queue (or if it is not in the
        database).
        """

        referers = IISet()

        referer = self.index.get(referer)
        if referer is not None:
            referers.add(referer)

        registry = getUtility(IRegistry, context=self.aq_parent)
        try:
            settings = registry.forInterface(ISettings)
        except KeyError as exc:
            logger.warn(exc)
            return

        for href, paths in links:
            paths = IISet(
                filter(None, map(self.index.get, paths))
                )

            if self.should_ignore(href, settings.ignore_list):
                continue

            # If the hyperlink is not already in the work queue,
            # compare the provided timestamp to our database to see if
            # we need to check its validity. Note that internal links
            # are excempt if we're not using the publisher.
            index = self.index.get(href)
            entry = self.checked.get(-1 if index is None else index)

            if index not in self.queue:
                if entry is None or entry[0] < timestamp:
                    if settings.use_publisher or not href.startswith('/'):
                        index = self.enqueue(href)
                    elif href not in self.index:
                        index = self.store(href)

            assert index is not None

            if entry is None:
                self.checked[index] = None, None, paths, referers
            else:
                # If the provided paths are a subset of the already
                # seen paths, and if there is no new referer, we don't
                # issue an update.
                if paths <= entry[2] and referer is not None and \
                       referer in entry[3]:
                    continue

                entry[2].update(paths)
                entry[3].update(referers)

    security.declarePrivate("store")
    def store(self, url):
        index = self.index[url] = self.counter
        self.links[index] = url
        self.counter += 1
        return index

    security.declarePrivate("update")
    def update(self, href, status):
        """Update link status."""

        now = datetime.datetime.now()
        timestamp = int(time.mktime(now.timetuple()))

        index = self.index.get(href)
        if index is None:
            return

        entry = self.checked.get(-1 if index is None else index)
        if entry is None:
            self.checked[index] = timestamp, status, IISet(), IISet()

        # If the status changed, we update the entry.
        elif status != entry[1] or not entry[0]:

            # If the status was previously good, then we clear the
            # status. What this means is that we'll wait for the next
            # check to declare a bad status (it might be temporary).
            if entry[1] == 200:
                status = None

            self.checked[index] = timestamp, status, entry[2], entry[3]

    @cache(lambda method, self, ignore_list: ignore_list)
    def get_matchers(self, ignore_list):
        matchers = []
        for expression in ignore_list:
            try:
                matcher = re.compile(expression).search
            except re.error:
                pass
            else:
                matchers.append(matcher)

        return matchers

    def should_ignore(self, href, ignore_list):
        for matcher in self.get_matchers(ignore_list):
            if matcher(href):
                return True

        return False


InitializeClass(LinkCheckTool)
registerToolInterface('portal_linkcheck', ILinkCheckTool)

# -*- coding: utf-8 -*-
from AccessControl.SecurityInfo import ClassSecurityInfo
from App.class_init import InitializeClass
from BTrees.IIBTree import IISet
from BTrees.IOBTree import IOBTree
from BTrees.OIBTree import OIBTree
from OFS.SimpleItem import SimpleItem
from Products.CMFCore.utils import registerToolInterface
from collective.linkcheck.interfaces import ILinkCheckTool
from collective.linkcheck.interfaces import ISettings
from collective.linkcheck.queue import CompositeQueue
from plone import api
from plone.memoize.volatile import cache
from plone.registry.interfaces import IRegistry
from zope.component import getUtility

import datetime
import logging
import re
import time

logger = logging.getLogger("linkcheck.events")


class LinkCheckTool(SimpleItem):
    security = ClassSecurityInfo()

    def __init__(self, id=None):
        super(LinkCheckTool, self).__init__(id)

        # This is the work queue; items in this queue are scheduled
        # for link validity check.
        self.queue = CompositeQueue()

        # Additional queue for internal crawler to revalidate the site
        self.crawl_queue = CompositeQueue()

        # This is the link database. It maps a hyperlink index to a
        # tuple (timestamp, status, referers).
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
        while True:
            try:
                self.crawl_queue.pull()
            except IndexError:
                break

        self.checked.clear()
        self.index.clear()
        self.links.clear()
        self.counter = 0

    security.declarePrivate("crawl")
    def crawl(self):
        self.clear()
        query = {}
        registry = getUtility(IRegistry)
        settings = registry.forInterface(ISettings)
        if settings.content_types:
            query['portal_type'] = settings.content_types

        if settings.workflow_states:
            query['review_state'] = settings.workflow_states

        catalog = api.portal.get_tool('portal_catalog')
        brains = catalog(query)
        for brain in brains:
            # asyncronous crawling not working yet
            # self.crawl_enqueue(brain.UID)

            obj = brain.getObject()
            obj.restrictedTraverse('@@linkcheck')()
            logger.info('Crawling: checked {0}'.format(brain.getURL()))

    security.declarePrivate("enqueue")
    def enqueue(self, url):
        index = self.index.get(url)
        if index is None:
            # a really new url
            index = self.store(url)
        else:
            entry = self.checked.get(index)
            if entry is not None and entry:
                entry = None, entry[1], entry[2]
                self.checked[index] = entry
            else:
                # reset empty entry
                self.remove(url)
                index = self.store(url)
        self.queue.put(index)
        return index

    security.declarePrivate("register")
    def register(self, hrefs, referer, timestamp):
        """Add or update link presence information.

        If a link has not been checked since the provided timestamp,
        it will be added to the queue (or if it is not in the
        database).
        """

        referer = self.index.get(referer) or self.store(referer)

        registry = getUtility(IRegistry, context=self.aq_parent)
        try:
            settings = registry.forInterface(ISettings)
        except KeyError as exc:
            logger.warn(exc)
            return

        limit = settings.referers

        for href in hrefs:
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
                self.checked[index] = None, None, IISet((referer,))
            else:
                # If the provided paths are a subset of the already
                # seen paths, and if there is no new referer, we don't
                # issue an update.
                referers = entry[2]
                if referer not in referers and len(referers) <= limit:
                    referers.add(referer)

    security.declarePrivate("store")
    def store(self, url):
        index = self.index[url] = self.counter
        self.links[index] = url
        self.counter += 1
        return index

    security.declarePrivate("remove")
    def remove(self, url):
        index = self.index.get(url)
        if url in self.index:
            del self.index[url]
        if index and index in self.checked:
            del self.checked[index]

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
            self.checked[index] = timestamp, status, IISet()

        # If the status changed, we update the entry.
        elif status != entry[1] or not entry[0]:

            # If the status was previously good, then we clear the
            # status. What this means is that we'll wait for the next
            # check to declare a bad status (it might be temporary).
            if entry[1] == 200:
                status = None

            self.checked[index] = timestamp, status, entry[2]

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

    def crawl_enqueue(self, obj):
        if not isinstance(obj, basestring):
            obj = obj.UID()
        self.crawl_queue.put(obj)

    def crawl_dequeue(self):
        if self.crawl_queue._data:
            return self.crawl_queue.pull()


InitializeClass(LinkCheckTool)
registerToolInterface('portal_linkcheck', ILinkCheckTool)

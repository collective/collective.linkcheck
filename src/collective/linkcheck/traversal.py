# -*- coding: utf-8 -*-
from Acquisition import Implicit
from Products.CMFCore.interfaces import ISiteRoot
from collective.linkcheck.controlpanel import ControlPanelEditForm
from collective.linkcheck.interfaces import ILayer
from zExceptions import Unauthorized
from zope.component import adapts
from zope.interface import implements
from zope.security import checkPermission
from zope.traversing.interfaces import ITraversable


class Feed(Implicit):
    __allow_access_to_unprotected_subobjects__ = 1

    def HEAD(self, auth=None):
        """Return empty string."""

        response = self.index_html(auth)
        self.REQUEST.response.setHeader('Content-Length', len(response))

        # Actually return an empty string
        return u""

    def index_html(self, auth=None):
        """Publish feed."""

        view = ControlPanelEditForm(self, self.REQUEST)

        if auth is None:
            if checkPermission('cmf.ManagePortal', self.aq_parent):
                return view.RSS()

        if auth != view.get_auth_token():
            raise Unauthorized('Invalid token')

        return view.RSS()


class FeedTraverser(object):
    implements(ITraversable)
    adapts(ISiteRoot, ILayer)

    def __init__(self, context, request=None):
        self.context = context
        self.request = request

    def traverse(self, name, ignore):
        if name.endswith('.rss'):
            return Feed().__of__(self.context)

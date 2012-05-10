from zope.interface import implements
from zope.traversing.interfaces import ITraversable
from zope.component import adapts

from Products.CMFCore.interfaces import ISiteRoot
from Acquisition import Implicit

from zope.security import checkPermission
from zExceptions import Unauthorized

from .interfaces import ILayer
from .controlpanel import ControlPanelEditForm


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

        view = ControlPanelEditForm(self.aq_parent, self.REQUEST)

        if auth is None:
            if not checkPermission('cmf.ManagePortal', self.context):
                raise Unauthorized(self.__name__)

        if auth != view.get_auth_token():
            raise Unauthorized(self.__name__)

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

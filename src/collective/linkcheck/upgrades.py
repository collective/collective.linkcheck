from Products.CMFCore.utils import getToolByName
from BTrees.IIBTree import IISet

from zope.component import getUtility
from plone.registry.interfaces import IRegistry

from .interfaces import ISettings


def upgrade_tool(tool):
    site = tool.aq_parent
    tool = getToolByName(site, 'portal_linkcheck')

    queue = tool.queue
    checked = tool.checked

    # Initialize datastructures.
    tool.__init__(tool.id)

    # Migrate checked items.
    i = -1

    def t(paths):
        return IISet(
            filter(None, map(tool.index.get, paths))
            )

    for i, href in enumerate(checked):
        entry = checked[href]
        tool.checked[i] = entry[0], entry[1], t(entry[3])
        tool.index[href] = i
        tool.links[i] = href

    tool.counter = i + 1

    # Migrate queue.
    for href in queue:
        tool.enqueue(href)

    registry = getUtility(IRegistry)
    registry.registerInterface(ISettings)

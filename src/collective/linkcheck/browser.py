from plone.app.layout.viewlets.common import ViewletBase

from Products.CMFCore.utils import getToolByName


class StatsViewlet(ViewletBase):
    available = True

    def __init__(self, *args):
        super(StatsViewlet, self).__init__(*args)

        try:
            self.tool = getToolByName(self.context, 'portal_linkcheck')
        except AttributeError:
            self.available = False

    @property
    def active_count(self):
        return len(self.tool.checked)

    @property
    def average_entropy(self):
        timestamps = set(entry[0] for entry in self.tool.checked.values())
        if not timestamps:
            return 0

        return round(float(len(self.tool.checked)) / len(timestamps))

    @property
    def queue_ratio(self):
        if not self.active_count:
            return 0

        ratio = round(100 * float(len(self.tool.queue)) / self.active_count)
        return int(ratio)

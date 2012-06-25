from zope.interface import Interface
from zope import schema

from collective.linkcheck import MessageFactory as _


class ILayer(Interface):
    """Add-on browser layer."""


class ILinkCheckTool(Interface):
    """Tool that performs link validity checking and reporting."""


class ISettings(Interface):
    concurrency = schema.Int(
        title=_(u'Concurrency'),
        description=_(u'This decides the number of simultaneous downloads.'),
        required=True,
        default=5,
        )

    interval = schema.Int(
        title=_(u'Update interval'),
        description=_(u'The minimum number of hours between checking '
                      u'the same link to update its link validity status.'),
        required=True,
        default=24,
        )

    expiration = schema.Int(
        title=_(u'Expiration'),
        description=_(u'This decides the link expiration threshold. Enter '
                      u'the number of days that a link should be valid '
                      u'after an appearance in the page output.'),
        required=True,
        default=7,
        )

    transaction_size = schema.Int(
        title=_(u'Transaction size'),
        description=_(u'The number of items pulled out of the worker queue '
                      u'for every transaction.'),
        required=True,
        default=100,
        )

    use_publisher = schema.Bool(
        title=_(u'Use publisher'),
        description=_(u"Select this option to publish internal links "
                      u"that have not been requested, and thus have no "
                      u"recorded response status."),
        required=False,
        default=False,
        )

    referers = schema.Int(
        title=_(u'Referer limit'),
        description=_(u"The database will store up to this number "
                      u"of referring links for each entry."),
        required=False,
        default=5,
        )

    ignore_list = schema.Tuple(
        title=_(u'Ignore list'),
        description=_(u'Use regular expressions to prevent links '
                      u'from appearing in the list. One expression per '
                      u'line (e.g. "^http://bit.ly").'),
        required=False,
        value_type=schema.TextLine(),
        default=(
            u"^http://bit.ly",
            u"^http://t.co",
            ),
        )

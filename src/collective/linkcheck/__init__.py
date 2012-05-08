import zope.i18nmessageid

MessageFactory = zope.i18nmessageid.MessageFactory('collective.linkcheck')

from .processor import run as processor

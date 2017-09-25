# -*- coding: utf-8 -*-
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.interfaces import IPloneSiteRoot
from ZODB.POSException import ConflictError
from cStringIO import StringIO
from collective.linkcheck.interfaces import ILayer
from collective.linkcheck.interfaces import ISettings
from collective.linkcheck.parse import iter_links
from plone import api
from plone.registry.interfaces import IRegistry
from zope.annotation.interfaces import IAnnotations
from zope.component import getUtility

import datetime
import gzip
import logging
import time
import transaction


logger = logging.getLogger("linkcheck.events")

TRAVERSAL_KEY = "collective.linkcheck:traversal"


def before_traverse(event):
    if IPloneSiteRoot.providedBy(event.object):
        IAnnotations(event.request)[TRAVERSAL_KEY] = event.object


def end_request(event):

    # Skip control panel view.
    if '@@linkcheck-controlpanel' in event.request['PATH_INFO']:
        return

    # Ignore internal requests.
    if event.request.get('HTTP_USER_AGENT') == 'Bobo':
        return

    # Must have add-on browser layer.
    if not ILayer.providedBy(event.request):
        return

    try:
        site = IAnnotations(event.request)[TRAVERSAL_KEY]
    except KeyError:
        return

    try:
        tool = getToolByName(site, 'portal_linkcheck')
    except AttributeError as exc:
        logger.warn("Did not find tool: %s." % exc)
        return

    # No processing if 'check_on_request' setting is false
    registry = getUtility(IRegistry, context=site)
    settings = registry.forInterface(ISettings)
    if not settings.check_on_request:
        return

    # Must be HTML.
    response = event.request.response
    content_type = response.getHeader('Content-Type')
    if content_type and not content_type.startswith('text/html'):
        return

    # Update the status of the present request.
    status = response.getStatus()

    if not tool.is_available():
        logger.warn("Tool not available; please run update step.")
        return

    # Compute path given the actual URL, relative to the site root.
    base_url = site.absolute_url()
    actual_url = event.request.get('ACTUAL_URL', '')
    if not actual_url.startswith(base_url):
        return

    path = actual_url[len(base_url):]

    tool.update(path, status)

    # Must be good response.
    if status != 200:
        return

    try:
        encoding = response.headers['content-type'].split('charset=')[-1]
    except:
        encoding = "latin-1"

    body = response.body
    if not body:
        return

    if response.headers.get('content-encoding') == 'gzip':
        try:
            body = gzip.GzipFile(fileobj=StringIO(body)).read()
        except BaseException as exc:
            logger.warn(exc)
            return

    try:
        document = body.decode(encoding, 'ignore')
    except UnicodeDecodeError as exc:
        logger.warn(exc)
        return

    hrefs = set()

    for href in iter_links(document):

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
            href = '/'.join((actual_url, href))

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
    now = datetime.datetime.now()
    date = now - datetime.timedelta(days=1)
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


def modified_object(obj, event):
    if not ILayer.providedBy(obj.REQUEST):
        return
    registry = getUtility(IRegistry)
    settings = registry.forInterface(ISettings)
    types_to_check = settings.content_types
    if types_to_check and obj.portal_type not in types_to_check:
        return
    states_to_check = settings.workflow_states
    if states_to_check and api.content.get_state(obj) not in states_to_check:
        return

    # I may find a way to process crawling asynchronously.
    # Right now there is a problem with traversal in a worker
    # tool = api.portal.get_tool('portal_linkcheck')
    # tool.crawl_enqueue(obj.UID())
    # return
    check_links_view = obj.restrictedTraverse('@@linkcheck')
    check_links_view()
    logger.info(
        'Checked links for modified {0}'.format(obj.absolute_url()))

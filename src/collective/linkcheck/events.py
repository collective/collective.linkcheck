import time
import datetime
import logging
import gzip
import transaction

from zope.annotation.interfaces import IAnnotations
from cStringIO import StringIO

from Products.CMFPlone.interfaces import IPloneSiteRoot
from Products.CMFCore.utils import getToolByName
from ZODB.POSException import ConflictError

from .interfaces import ILayer
from .parse import iter_links

logger = logging.getLogger("linkcheck.events")

TRAVERSAL_KEY = "collective.linkcheck:traversal"


def before_traverse(event):
    if IPloneSiteRoot.providedBy(event.object):
        IAnnotations(event.request)[TRAVERSAL_KEY] = event.object


def end_request(event):
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

    # Must be HTML.
    response = event.request.response
    content_type = response.getHeader('Content-Type')
    if content_type and not content_type.startswith('text/html'):
        return

    # Update the status of the present request.
    status = response.getStatus()
    tool.update(event.request['PATH_INFO'], status)

    # Must be good response.
    if status != 200:
        return

    # Skip control panel view.
    if '@@linkcheck-controlpanel' in event.request['PATH_INFO']:
        return

    try:
        encoding = response.headers['content-type'].split('charset=')[-1]
    except:
        encoding = "latin-1"

    body = response.body
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

    base_url = site.absolute_url()

    hrefs = {}
    for href, path in iter_links(document):
        # Ignore anchors and javascript.
        if href.startswith('#') or href.startswith('javascript:'):
            continue

        # Internal URLs are stored site-relative.
        if href.startswith(base_url):
            href = "/" + href[len(base_url) + 1:].rstrip("/")

        # Add trailing slash to bare domain.
        if href.startswith('http://') or href.startswith('https://'):
            if href.count('/') == 2:
                href = href.rstrip('/') + '/'

        hrefs.setdefault(href, set()).add(path)

    # We want all the hyperlinks in the document to be checked unless
    # it's already in the queue or it has been checked recently.
    now = datetime.datetime.now()
    date = now - datetime.timedelta(days=1)
    yesterday = int(time.mktime(date.timetuple()))

    # Determine referer URL
    referer = event.request['SERVER_PROTOCOL'].split('/', 1)[0].lower() + \
              '://' + event.request['HTTP_HOST'] + event.request['PATH_INFO']

    # Update link database
    tool.register(hrefs.items(), referer, yesterday)

    # We always commit the transaction; if no changes were made, this
    # is a NOOP. Note that conflict errors are possible with
    # concurrent requests. We ignore them.
    try:
        transaction.commit()
    except ConflictError:
        transaction.abort()

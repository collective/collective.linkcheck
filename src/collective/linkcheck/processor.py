import time
import logging
import datetime
import threading
import transaction
import requests

from itertools import ifilterfalse, tee, ifilter
from cStringIO import StringIO
from Queue import Queue

from App.config import getConfiguration
from Products.CMFPlone.interfaces import IPloneSiteRoot
from Products.CMFCore.utils import getToolByName
from ZPublisher.Test import publish_module
from ZODB.POSException import ConflictError

from zope.component import getUtility
from plone.registry.interfaces import IRegistry

from .interfaces import ISettings


def partition(pred, iterable):
    """Use a predicate to partition entries into false entries and
    true entries.

    See: http://docs.python.org/dev/library/itertools.html#itertools-recipes.
    """

    t1, t2 = tee(iterable)
    return ifilter(pred, t1), ifilterfalse(pred, t2)


def run(app, args):
    # Adjust root logging handler levels
    level = getConfiguration().eventlog.getLowestHandlerLevel()
    root = logging.getLogger()
    for handler in root.handlers:
        handler.setLevel(level)

    logger = logging.getLogger("linkcheck.events")
    logger.setLevel(level)
    logger.info("looking for sites...")

    session = requests.Session(timeout=5)

    tasks = []
    for name, item in app.objectItems():
        if IPloneSiteRoot.providedBy(item):
            try:
                tool = getToolByName(item, 'portal_linkcheck')
            except AttributeError:
                continue

            logger.info("found site '%s'." % name)

            registry = getUtility(IRegistry, context=item)

            try:
                settings = registry.forInterface(ISettings)
            except KeyError:
                logger.warn("settings not available; please reinstall.")
                continue

            responses = []

            def worker():
                while True:
                    url = q.get()

                    try:
                        r = session.get(url)
                    except requests.Timeout:
                        r = requests.Response()
                        r.status_code = 504
                        r.url = url
                    except requests.RequestException as exc:
                        logger.warn(exc)
                        r = requests.Response()
                        r.status_code = 503
                        r.url = url

                    responses.append(r)
                    q.task_done()

            q = Queue()
            for i in range(settings.concurrency):
                t = threading.Thread(target=worker)
                t.daemon = True
                t.start()

            logger.info("%d worker threads started." % settings.concurrency)
            tasks.append((tool, settings, q, responses))

    if not tasks:
        return

    # Enter runloop
    counter = 0
    while True:
        errors = set()

        for tool, settings, queue, responses in tasks:
            # Synchronize database
            tool._p_jar.sync()

            if not counter % 3600:
                now = datetime.datetime.now()

                # This timestamp is the threshold for items that need an
                # update.
                needs_update = int(time.mktime(
                    (now - datetime.timedelta(hours=settings.interval)).\
                    timetuple()
                    ))

                # This timestamp is the threshold for items that are no
                # longer active.
                expired = int(time.mktime(
                    (now - datetime.timedelta(days=settings.expiration)).\
                    timetuple()
                    ))

                discard = set()
                for url, entry in tool.checked.items():
                    if url in tool.queue:
                        continue

                    # Discard items that are expired
                    if entry[0] and entry[0] < expired:
                        discard.add(url)

                    # Enqueue items with an out of date timestamp.
                    elif entry[0] and entry[0] < needs_update:
                        tool.queue.put(url)

                for url in discard:
                    del tool.checked[url]

            # Fetch set of URLs to check (up to transaction size).
            urls = tool.queue[:settings.transaction_size]
            if not urls:
                continue

            # This keeps track of status updates, which we'll apply at
            # the end.
            updates = []

            # Distinguish between internal and external requests.
            internal, external = partition(
                lambda url: url.startswith('/'),
                urls
                )

            # Must be HTTP or HTTPS
            external, invalid = partition(
                lambda url: url.startswith('http://') or \
                            url.startswith('https://'),
                external
                )

            for url in external:
                queue.put(url)

            # Wait for responses
            queue.join()

            while responses:
                response = responses.pop()
                status = response.status_code

                # This may be a redirect.
                if response.history:
                    url = response.history[0].url
                    if response.history[0].status_code == 301:
                        status = 301
                else:
                    url = response.url

                updates.append((url, status))

            for url in internal:
                # For now, we simply ignore internal links if we're
                # not publishing.
                if not settings.use_publisher:
                    continue

                stdout = StringIO()
                stderr = StringIO()

                env = {
                    'GATEWAY_INTERFACE': 'CGI/1.1 ',
                    'HTTP_ACCEPT': '*/*',
                    'HTTP_HOST': '127.0.0.1',
                    'HTTP_USER_AGENT': 'Bobo',
                    'REQUEST_METHOD': 'GET',
                    'SCRIPT_NAME': '',
                    'SERVER_HOSTNAME': 'bobo.server.host',
                    'SERVER_NAME': 'bobo.server',
                    'SERVER_PORT': '80',
                    'SERVER_PROTOCOL': 'HTTP/1.0 ',
                    }

                env['PATH_INFO'] = "/" + tool.aq_parent.absolute_url() + url

                try:
                    status = publish_module(
                        'Zope2', environ=env, stdout=stdout, stderr=stderr
                        )
                except ConflictError:
                    status = 503
                else:
                    # This is assumed to be a good response.
                    if status == 302:
                        status = 200

                updates.append((url, status))

            # Pull URLs out of queue, actually removing them.
            unchanged = []
            urls = set(urls)

            while urls:
                try:
                    url = tool.queue.pull()
                except IndexError:
                    transaction.abort()
                    continue

                try:
                    urls.remove(url)
                except KeyError:
                    unchanged.append(url)

            # This shouldn't happen to frequently.
            for url in unchanged:
                tool.queue.put(url)
                logger.warn("putting back unprocessed url: %s." % url)

            for url in invalid:
                tool.update(url, 0)
                errors.add(url)

            # Apply status updates
            for url, status in updates:
                tool.update(url, status)

            transaction.get().note('updated link validity')
            try:
                transaction.commit()
            except ConflictError:
                transaction.abort()

        for url in errors:
            logger.warn("error checking: %s." % url)

        time.sleep(1)
        counter += 1

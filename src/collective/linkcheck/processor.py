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
from ZODB.POSException import ConflictError
from zExceptions import Unauthorized

from zope.component import getUtility
from plone.registry.interfaces import IRegistry

from .interfaces import ISettings
import sys
import os

#from ZPublisher.Test import publish_module


def publish_module(module_name,
                   stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
                   environ=os.environ, debug=0, request=None, response=None,
                   extra={}):
    """ Adapted from from ZPublisher.Test.publish_module:
    but we handle the response status like given from response.getStatus(),
    otherwise plone internal links will return status=200 for status=404 links,
    which will not throw an error.
    """
    must_die = 0
    status = 200
    after_list = [None]
    from ZPublisher.Response import Response
    from ZPublisher.Request import Request
    from ZPublisher.Publish import publish
    from zope.publisher.interfaces import ISkinnable
    from zope.publisher.skinnable import setDefaultSkin
    try:
        try:
            if response is None:
                response = Response(stdout=stdout, stderr=stderr)
            else:
                stdout = response.stdout

            # debug is just used by tests (has nothing to do with debug_mode!)
            response.handle_errors = not debug

            if request is None:
                request = Request(stdin, environ, response)

            # make sure that the request we hand over has the
            # default layer/skin set on it; subsequent code that
            # wants to look up views will likely depend on it
            if ISkinnable.providedBy(request):
                setDefaultSkin(request)

            for k, v in extra.items():
                request[k] = v
            response = publish(request, module_name, after_list, debug=debug)
        except (SystemExit, ImportError):
            # XXX: Rendered ImportErrors were never caught here because they
            # were re-raised as string exceptions. Maybe we should handle
            # ImportErrors like all other exceptions. Currently they are not
            # re-raised at all, so they don't show up here.
            must_die = sys.exc_info()
            request.response.exception(1)
        except Unauthorized:
            # Handle Unauthorized separately, otherwise it will be displayed as
            # a redirect to the login form
            status = 200
            response = None
        except:
            # debug is just used by tests (has nothing to do with debug_mode!)
            if debug:
                raise
            request.response.exception()
            status = response.getStatus()

        if response:
            ## this is our change: otherwise 404 will return 200
            ## but we only want "real" 404 - otherwise the list will get full
            ## of internal links with edit-links stuff that will return 5xx
            ## codes.
            if response.getStatus() in (301, 302, 404):
                status = response.getStatus()

            outputBody = getattr(response, 'outputBody', None)
            if outputBody is not None:
                outputBody()
            else:
                response = str(response)
                if response:
                    stdout.write(response)

        # The module defined a post-access function, call it
        if after_list[0] is not None:
            after_list[0]()

    finally:
        if request is not None:
            request.close()

    if must_die:
        # Try to turn exception value into an exit code.
        try:
            if hasattr(must_die[1], 'code'):
                code = must_die[1].code
            else:
                code = int(must_die[1])
        except:
            code = must_die[1] and 1 or 0
        if hasattr(request.response, '_requestShutdown'):
            request.response._requestShutdown(code)

        try:
            raise must_die[0], must_die[1], must_die[2]
        finally:
            must_die = None

    return status, response


def partition(pred, iterable):
    """Use a predicate to partition entries into false entries and
    true entries.

    See: http://docs.python.org/dev/library/itertools.html#itertools-recipes.
    """

    t1, t2 = tee(iterable)
    return ifilter(pred, t1), ifilterfalse(pred, t2)


def run(app, args, rate=5):
    # Adjust root logging handler levels
    level = getConfiguration().eventlog.getLowestHandlerLevel()
    root = logging.getLogger()
    for handler in root.handlers:
        handler.setLevel(level)

    logger = logging.getLogger("linkcheck.processor")
    logger.setLevel(level)
    logger.info("looking for sites...")

    session = requests.Session(timeout=5)

    counter = 0
    sites = {}

    # Enter runloop
    while True:
        to_enqueue = []
        errors = set()

        for name, item in app.objectItems():
            if name in sites:
                continue

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
                        r = None

                        try:
                            r = session.get(url)
                        except requests.Timeout:
                            status_code = 504
                        except requests.RequestException as exc:
                            logger.warn(exc)
                            status_code = 503
                        except UnicodeError as exc:
                            logger.warn("Unable to decode string: %r (%s)." % (
                                url, exc))
                            status_code = 502

                        if r is None:
                            r = requests.Response()
                            r.status_code = status_code
                            r.url = url

                        responses.append(r)
                        q.task_done()

                q = Queue()
                for i in range(settings.concurrency):
                    t = threading.Thread(target=worker)
                    t.daemon = True
                    t.start()

                logger.info(
                    "%d worker threads started." % settings.concurrency
                    )

                sites[name] = (tool, settings, q, responses)

        if not sites and not counter:
            logger.info(
                "no sites found; polling every %d second(s) ..." % rate
                )

        for tool, settings, queue, responses in sites.values():
            # Synchronize database
            tool._p_jar.sync()

            if not tool.is_available():
                logger.warn("Tool not available; please run update step.")
                logger.info("Sleeping for 10 seconds...")
                time.sleep(10)
                break

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
            queued = tool.queue[:settings.transaction_size]
            if not queued:
                continue

            urls = filter(None, map(tool.links.get, queued))

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
                    status, response = publish_module(
                        'Zope2', environ=env, stdout=stdout, stderr=stderr
                        )
                except ConflictError:
                    status = 503
                else:
                    if status in (301, 302):
                        #enqueue the redirect target
                        target = response.headers.get('location')
                        # for internal redirects host will be the one from env,
                        # remove it
                        prefix = 'http://%s' % env['HTTP_HOST']
                        if target.startswith(prefix):
                            target = target.replace(prefix, '', 1)
                        now = datetime.datetime.now()
                        date = now - datetime.timedelta(days=1)
                        yesterday = int(time.mktime(date.timetuple()))
                        to_enqueue.append(([target], env['PATH_INFO'],
                                           yesterday))

                        status = 200

                updates.append((url, status))

            # Pull URLs out of queue, actually removing them.
            unchanged = []
            urls = set(urls)

            while urls:
                try:
                    i = tool.queue.pull()
                except IndexError:
                    transaction.abort()
                    continue

                try:
                    url = tool.links[i]
                    urls.remove(url)
                except KeyError:
                    unchanged.append(i)

            # This shouldn't happen to frequently.
            for i in unchanged:
                tool.queue.put(i)
                url = tool.links[i]
                logger.warn("putting back unprocessed url: %s." % url)

            for url in invalid:
                tool.update(url, 0)
                errors.add(url)

            # Apply status updates
            for url, status in updates:
                tool.update(url, status)

            for arguments in to_enqueue:
                tool.register(*arguments)

            transaction.get().note('updated link validity')
            try:
                transaction.commit()
            except ConflictError:
                transaction.abort()

        for url in errors:
            logger.warn("error checking: %s." % url)

        time.sleep(rate)
        app._p_jar.sync()
        counter += 1

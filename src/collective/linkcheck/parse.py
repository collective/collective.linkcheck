import logging

import lxml.html
import lxml.etree

logger = logging.getLogger("linkcheck.parse")


def iter_links(body):
    try:
        html = lxml.html.fromstring(body)
    except lxml.etree.ParserError as exc:
        logger.warn(exc)
        return

    tree = html.getroottree()

    for link in html.iterfind('.//a'):
        path = tree.getpath(link)
        href = link.attrib.get('href')
        if href is not None:
            yield href, path

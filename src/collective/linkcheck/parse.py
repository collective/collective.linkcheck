import logging

import lxml.html
import lxml.etree

logger = logging.getLogger("linkcheck.parse")


def iter_links(body):
    try:
        html = lxml.html.fromstring(body)
    except (lxml.etree.ParseError, lxml.etree.ParserError) as exc:
        logger.warn(exc)
        return

    for link in html.iterfind('.//a'):
        base = None
        href = link.attrib.get('href')

        if not href:
            continue

        while '../' in href:
            if '://' not in href:
                if base is None:
                    try:
                        base = html.find('.//base').attrib['href']
                    except BaseException:
                        base = ""
                    else:
                        base = base.rstrip('/') + '/'

                if base:
                    href = base + href.lstrip('/')
                    href = '/' + href.split('://', 1)[1].split('/', 1)[-1]

            i = href.find('../')
            assert i > -1

            if i == 0:
                continue

            previous = href.rfind('/', 0, i - 1)
            after = href[i + 3:]

            if previous == -1:
                href = after
            else:
                href = href[:previous] + "/" + after

        href = href.split('#', 1)[0]
        href = href.split('?', 1)[0]

        if href:
            yield href

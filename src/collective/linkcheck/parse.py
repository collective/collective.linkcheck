import lxml.html
import lxml.etree

def iter_links(body):
    html = lxml.html.fromstring(body)
    tree = html.getroottree()

    for link in html.iterfind('.//a'):
        path = tree.getpath(link)
        href = link.attrib.get('href')
        if href is not None:
            yield href, path

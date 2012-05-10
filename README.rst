The system is an integrated solution, with a headless instance
processing items in the background.

ZEO or other shared storage is required.

Compatibility: Plone 4+.


Setup
=====

Add the package to your buildout, then install the add-on from inside
Plone.

Next, set up an instance to run the link checking processor. This can
be an existing instance, or a separate one::

  $ bin/instance linkcheck

This process should always be running, but may be stopped and started
at any time without data loss.


Control panel
=============

Once the system is up and running, interaction happens through the
"Link validity" control panel::

  http://localhost:8080/site/@@linkcheck-controlpanel

It's available from Plone's control panel overview.

*Reporting*

    The report tab lists current problems.

*Notification*

    An alert system is provided in the form of an RSS-feed::

      http://localhost:8080/site/@@linkcheck-feed

    Note that this view requires the "Manage portal" permission. To allow
    integration with other services, a self-authenticating link is
    available from the report screen:

       RSS-feed available. Click the orange icon |rss|

    To set up e-mail notification, configure an RSS-driven newsletter
    with this feed and adjust the frequency to match the update
    interval (i.e. every morning). There's probably a lot of choice
    here. `MailChimp <http://www.mailchimp.com>`_ makes it very easy.

*Settings*

    The settings tab on the control panel provides configuration for
    concurrency level, checking interval and link expiration, as well as
    statistics about the number of links that are currently active and the
    queue size.

    There is also a setting available that lets the processor use the
    publisher to test internal link validity (at the cost of
    additional system resources). If this mode is enabled, the
    processor will attempt to publish the internal link and check that
    the response is good.


.. |RSS| image:: http://plone.org/rss.png


How does it work?
=================

When the add-on is installed, Plone will pass each HTML response
through a collection step that keeps track of:

1. The status code of outgoing HTML responses;
2. The hyperlinks which appear in the response body, if available.

This happens very quickly. The `lxml
<http://pypi.python.org/pypi/lxml>`_ library is used to parse and
search the response document for links.

The benefit of the approach is that we don't need to spend additional
resources to check the validity of pages that we've already rendered.

There's an assumption here that the site is visited regularly and
exhaustively by a search robot or other crawling service. This is
typically true for a public site.


Link status
-----------

A good status is either ``200 OK`` or ``302 Moved Temporarily``; a
neutral status is a good link which has turned bad, or not been
checked; a bad status is everything else, including ``301 Moved
Permanently``.

In any case, the status of an external link is updated only once per
the configured interval (24 hours by default).


History
-------

Link validity checking has previously been a core functionality in
Plone, but starting from the 4.x-series, there is no such
capability. It's been proposed to bring it back into the core (see
`PLIP #10987 <https://dev.plone.org/ticket/10987>`_), but the idea has
since been retired.

There's a 3rd party product available, `gocept.linkchecker
<https://intra.gocept.com/projects/projects/cmflinkchecker>`_ which
relies on a separate process written in the `Grok
<http://grok.zope.org>`_ framework to perform external
link-checking. It communicates with Plone via XML-RPC. There's a Plone
4 `compatibility branch
<https://code.gocept.com/hg/public/gocept.linkchecker/>`_
available. This product demands significantly more resources (both CPU
and memory) because it publishes all internal links at a regular
interval.


Performance
===========

In the default configuration, the system should not incur significant
overhead.

That said, we've put the data into a Zope 2 tool to allow easily
mounting it into a separate database.


Keeping a separate database for updates
---------------------------------------

Using the ``plone.recipe.zope2instance`` recipe for buildout, this is
how you would configure a mount point for a Plone site located at
``/site``::

  zope-conf-additional =
      <zodb_db linkcheck>
         mount-point /site/portal_linkcheck
         container-class collective.linkcheck.tool.LinkCheckTool
         <zeoclient>
           server ${zeo:zeo-address}
           storage linkcheck
         </zeoclient>
      </zodb_db>

This should match a ``plone.recipe.zeoserver`` part::

  zeo-conf-additional =
      <filestorage linkcheck>
        path ${buildout:directory}/var/filestorage/linkcheck.fs
      </filestorage>

Note that you must add the mount point using the ZMI before installing
the add-on for it to work.


License
=======

GPLv3 (http://www.gnu.org/licenses/gpl.html).


Author
======

Malthe Borch <mborch@gmail.com>


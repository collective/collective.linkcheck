The system is an integrated solution, with a headless instance
processing items in the background.

Note that ZEO or other shared storage is required. Meanwhile, this
requirement provides for a simple implementation where the processor
connects directly to the transactional storage.

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
control panel.

The "Link validity" screen shows a report that lists links with a bad
status. It's accessible from Plone's control panel::

  http://localhost:8080/site/@@linkcheck-controlpanel

This screen also contains a settings tab that provides configuration
for concurrency level, checking interval and link expiration, as well
as statistics about the number of links that are currently active and
the queue size.

To subscribe to alerts, there's an RSS-representation available::

  http://localhost:8080/site/@@linkcheck-feed

Note that this view requires the "Manage portal" permission. To allow
integration with other services, a self-authenticating link is
available from the report screen.


Additional reading
==================

The material in this section is not required to use the add-on.


Request lifecycle
-----------------

The system hooks into the request lifecycle and keeps track of the
status of outgoing HTML responses as well as the links present in
those responses.

In the default configuration, it's assumed that the site is visited
regularly and exhaustively by a search robot or other crawling
service. This is typically true for a public site. There is a also a
mode available where the processor uses Zope's own publisher to test
internal link validity (at the cost of additional system resources).


Link status
-----------

In terms of link validity, a good status is either ``200 OK`` or ``302
Moved Temporarily``, a neutral status is a good link which has turned
bad, or not been checked, and a bad status is everything else,
including ``301 Moved Permanently``.

In any case, the status of an external link is updated only once per
the configured interval which is 24 hours by default.


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
<https://code.gocept.com/hg/public/gocept.linkchecker/>`_ available.


Setting up tool in a ZODB mount point
-------------------------------------

The package installs a Zope 2 utility in the site root. The tool
updates rather frequently and the system administrator might consider
setting up the tool on a separate mount point.

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


The system is an integrated solution and runs as a headless instance
with no configuration required. Note that ZEO or other non-exclusive
storage is required.

Compatibility: Plone 4+.


Setup
=====

Add the package to your buildout eggs section, then install the add-on
inside Plone.

Next, run the checking processor on an existing instance executable::

  $ bin/instance linkcheck

This process should always be running, but may be stopped and started
at any time without data loss.


Reporting
---------

Visit the control panel to see the report or configure the system.


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


Setting up a separate ZODB mount point
--------------------------------------

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
-------

GPLv3 (http://www.gnu.org/licenses/gpl.html).


Author
------

Malthe Borch <mborch@gmail.com>


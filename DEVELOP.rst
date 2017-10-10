Using the development buildout
------------------------------

Create a virtualenv in the package::

    $ virtualenv --clear .

Install requirements with pip::

    $ ./bin/pip install -r requirements.txt

Run buildout::

    $ ./bin/buildout

Start Zeoserver:

    $ ./bin/zeoserver start

Start Plone in foreground:

    $ ./bin/instance fg

Start Linkchecker in foreground:

    $ ./bin/instance_linkcheck linkcheck

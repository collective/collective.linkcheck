Changes
=======

1.1 (2012-06-25)
----------------

- Don't store path (location in document) information; it's useless
  and it takes up too much disk space.

- Added option to limit number of referers to store (default: 5).

- Datastructure optimization.

  Use bucket-based data types when possible, and avoid copying strings
  (instead using an integer-based lookup table).

  Note: Migration required. Please run the upgrade step.

1.0.2 (2012-06-15)
------------------

- Add whitelist (ignore) option. This is a list of regular expressions
  that match on links to prevent them from being recorded by the tool.

- Make report sortable.

1.0.1 (2012-05-10)
------------------

- Quote URLs passed to the "Enqueue" action.

- Added support for HEAD request.

- Use ``gzip`` library to correctly read and decompress
  zlib-compressed responses.

1.0 (2012-05-10)
----------------

- Initial public release.

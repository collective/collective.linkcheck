# -*- coding: utf-8 -*-
from Products.Five import BrowserView
from ZPublisher.HTTPResponse import status_reasons
from collective.linkcheck.controlpanel import triage
from collective.linkcheck.interfaces import ISettings
from plone import api
from plone.registry.interfaces import IRegistry
from tempfile import NamedTemporaryFile
from zope.component import getUtility

import json
import tablib


class Export(BrowserView):
    """Dump a report. This uses tablib to allow various formats.
    Supported are csv, xlsx, xls, tsv, yaml, html and json
    The default is csv.
    Call /@@linkcheck-export?export_type=json  for example.
    """

    def __call__(self):
        export_type = self.request.get('export_type', 'csv')
        return self.get_export_data(export_type)

    def get_export_data(self, export_type):
        data = []
        tool = api.portal.get_tool('portal_linkcheck')
        entries = list(tool.checked.items())
        entries.sort(
            key=lambda (i, entry): (
                triage(None if i in tool.queue else entry[1]),
                entry[0]),
            reverse=True,
            )

        registry = getUtility(IRegistry)
        settings = registry.forInterface(ISettings)

        for i, entry in entries:
            status = entry[1]

            # Skip entries with unknown status.
            if not status:
                continue

            # Break out of iteration when we reach a good status.
            if entry[1] == 200:
                break

            url = tool.links[i]
            referers = filter(None, map(tool.links.get, entry[2]))[:settings.referers]  # noqa

            data.append({
                'url': url,
                'status': "%d %s" % (status, status_reasons.get(status, '')),
                'referers': referers,
                })

        dataset = tablib.Dataset()
        dataset.dict = data

        if export_type == 'xlsx':
            result = dataset.xlsx
            return self.export_file(
                result,
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # noqa
                'xlsx')

        if export_type == 'xls':
            result = dataset.xls
            return self.export_file(
                result, 'application/vnd.ms-excel', 'xls')

        if export_type == 'tsv':
            result = dataset.tsv
            return self.export_file(
                result, 'text/tab-separated-values', 'tsv')

        if export_type == 'yaml':
            result = dataset.yaml
            return self.export_file(result, 'text/yaml', 'yaml')

        if export_type == 'html':
            return dataset.html

        if export_type == 'json':
            pretty = json.dumps(data, sort_keys=True, indent=4)
            self.request.response.setHeader('Content-type', 'application/json')
            return pretty

        else:
            result = dataset.csv
            return self.export_file(result, 'text/csv', 'csv')

    def export_file(self, result, mimetype, extension):
        filename = "collective_linkchecker_export.{}".format(extension)
        with NamedTemporaryFile(mode='wb') as tmpfile:
            tmpfile.write(result)
            tmpfile.seek(0)
            self.request.response.setHeader('Content-Type', mimetype)
            self.request.response.setHeader(
                'Content-Disposition',
                'attachment; filename="%s"' % filename)
            return file(tmpfile.name).read()

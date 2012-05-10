import os
import sys

reload(sys).setdefaultencoding("UTF-8")

from setuptools import setup, find_packages


def read(*pathnames):
    return open(os.path.join(os.path.dirname(__file__), *pathnames)).read().\
           decode('utf-8')

version = '1.0'

setup(name='collective.linkcheck',
      version=version,
      description="Add-on for Plone that provides link "
                  "validity checking and reporting.",
      long_description='\n'.join([
          read('README.rst'),
          read('CHANGES.rst'),
          ]),
      classifiers=[
        "Framework :: Plone",
        "Framework :: Zope2",
        "Development Status :: 5 - Production/Stable",
        "Programming Language :: Python",
        ],
      keywords='plone link-checking',
      author='Malthe Borch',
      author_email='mborch@gmail.com',
      license="GPLv2+",
      packages=find_packages('src'),
      package_dir={'': 'src'},
      namespace_packages=['collective'],
      include_package_data=True,
      zip_safe=False,

      # If the dependency to z3c.form gives you trouble within a Zope
      # 2 environment, try the `fakezope2eggs` recipe
      install_requires=[
          'setuptools',
          'zc.queue',
          'requests',
          'plone.z3cform',
      ],
      entry_points="""
      [z3c.autoinclude.plugin]
      target = plone

      [zopectl.command]
      linkcheck = collective.linkcheck:processor
      """,
      )

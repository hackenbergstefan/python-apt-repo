import datetime
import hashlib
import logging
import os
import urllib.request
from . import BinaryPackageDependency


def mkdirs_if_not_exist(filename):
    if not os.path.exists(os.path.dirname(filename)):
        os.makedirs(os.path.dirname(filename))

def sha1file(filename):
    sha1 = hashlib.sha1()
    with open(filename, 'rb') as fp:
        block = fp.read(2**16)
        while len(block) != 0:
            sha1.update(block)
            block = fp.read(2**16)
    return sha1.hexdigest()


apt_release_file_template = """Origin: local
Label: {label}
Suite: {dist}
Codename: {dist}
Date: {date}
Architectures: {architectures}
Components: {components}
Description:
"""


class APTDependencyMirror:

    def __init__(self, sources):
        self.sources = sources
        self.packages_to_mirror = set()

    def add_package(self, package, mirror_recommends=False):
        if isinstance(package, list):
            [self.add_package(p) for p in package]
        else:
            package = BinaryPackageDependency(package)
            self._add_dependencies(package)
            if mirror_recommends:
                self._add_recommends(package)

    def _add_recommends(self, package):
        for pack in self.sources.get(package.package_name):
            for dependency in map(BinaryPackageDependency, pack.recommends):
                self.packages_to_mirror |= self.sources.packages_fulfilling(dependency)

    def _add_dependencies(self, package: BinaryPackageDependency):
        package_name = package.package_name

        logging.getLogger(__name__).info('Adding top level package "{}"'.format(package))

        for pack in self.sources.get(package_name):
            self.packages_to_mirror |= pack.dependencies(self.sources)

    def create(self, location, dist, component):
        self._create_packages_file(location, dist, component)
        for package in self.packages_to_mirror:
            self._download_package(location, package)

    def _create_packages_file(self, location, dist, component):
        packages_files = []
        for arch in self.sources.architectures:
            packfile = os.path.join(location, 'dists', dist, component, 'binary-' + arch, 'Packages')
            packages_files.append(packfile)
            mkdirs_if_not_exist(packfile)
            with open(packfile, 'w') as fp:
                for pack in [p for p in self.packages_to_mirror if p.architecture == arch]:
                    fp.write(pack.content + '\n\n')

        release_file = os.path.join(location, 'dists', dist, 'Release')
        with open(release_file, 'w') as fp:
            fp.write(apt_release_file_template.format(
                label='',
                dist=dist,
                date=datetime.datetime.strftime(datetime.datetime.now(), '%a, %d %b %Y %H:%M:%S %z'),
                architectures=' '.join(self.sources.architectures),
                components=component
            ) + '\n')
            fp.write('SHA1:\n')
            for packfile in packages_files:
                fp.write(' {} {} {}\n'.format(
                    sha1file(packfile),
                    os.stat(packfile).st_size,
                    os.path.relpath(packfile, os.path.dirname(release_file)).replace(os.path.sep, '/')
                ))

    def _download_package(self, location, package):
        download_url = package.repository.url + '/' + package.filename
        filename = os.path.join(location, *package.filename.split('/'))

        logging.getLogger(__name__).info('Download {} from "{}" to "{}"'.format(package, download_url, filename))

        mkdirs_if_not_exist(filename)

        if not os.path.exists(filename):
            download_content = urllib.request.urlopen(download_url).read()
            with open(filename, 'wb') as fp:
                fp.write(download_content)

        assert sha1file(filename) == package.sha1, 'Corrupt file: {}'.format(filename)

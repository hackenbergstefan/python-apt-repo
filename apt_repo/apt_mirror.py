import datetime
import gzip
import re
import hashlib
import logging
import os
import urllib.request
from . import BinaryPackageDependency, __download_raw


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


def download(remote, local):
    logging.getLogger(__name__).debug('Download "{}" -> "{}"'.format(remote, local))
    mkdirs_if_not_exist(local)
    download_content = urllib.request.urlopen(remote).read()
    with open(local, 'wb') as fp:
        fp.write(download_content)


def _topath(url):
    return re.sub(r'https?://', '', url)


class APTDependencyMirror:

    def __init__(self, sources, location):
        self.sources = sources
        self.location = location
        self.packages_to_mirror = set()

    def create(self):
        self._mirror_metafiles()
        for pack in self.packages_to_mirror:
            self._mirror_package(pack)

    def _mirror_metafiles(self):
        for repo in self.sources.repositories:
            for fil in ['Release', 'Release.gpg', 'InRelease']:
                download(
                    '/'.join([repo.url, 'dists', repo.dist, fil]),
                    os.path.join(self.location, _topath(repo.url), 'dists', repo.dist, fil)
                )
            for component in repo.components:
                for architecture in repo.architectures:
                    for fil in ['Packages', 'Packages.gz', 'Release']:
                        try:
                            url = '/'.join([repo.url, 'dists', repo.dist, component, 'binary-' + architecture, fil])
                            download(
                                url,
                                os.path.join(self.location, _topath(repo.url), 'dists', repo.dist, component, 'binary-' + architecture, fil)
                            )
                        except urllib.error.HTTPError:
                            logging.getLogger(__name__).warning('URL not found: "{}"'.format(url))

    def add_package(self, package):
        if isinstance(package, list):
            [self.add_package(p) for p in package]
        else:
            package = BinaryPackageDependency(package)
            self._add_dependencies(package)

    def _add_recommends(self, package):
        for pack in self.sources.get(package.package_name):
            for dependency in map(BinaryPackageDependency, pack.recommends):
                self.packages_to_mirror |= self.sources.packages_fulfilling(dependency)

    def _add_dependencies(self, package: BinaryPackageDependency):
        package_name = package.package_name

        logging.getLogger(__name__).info('Adding top level package "{}"'.format(package))

        for pack in self.sources.get(package_name):
            self.packages_to_mirror |= pack.dependencies(self.sources)

    def _mirror_package(self, package):
        download_url = package.repository.url + '/' + package.filename
        filename = os.path.join(self.location, _topath(package.repository.url), *package.filename.split('/'))

        logging.getLogger(__name__).info('Download {} from "{}" to "{}"'.format(package, download_url, filename))

        if not os.path.exists(filename):
            download(download_url, filename)

        assert sha1file(filename) == package.sha1, 'Corrupt file: {}'.format(filename)

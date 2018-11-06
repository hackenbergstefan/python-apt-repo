import re
import hashlib
import logging
import os
import requests
import multiprocessing

from . import BinaryPackageDependency


def mkdirs_if_not_exist(filename):
    if not os.path.exists(os.path.dirname(filename)):
        os.makedirs(os.path.dirname(filename))


def shafile(filename, alg='sha1'):
    sha = getattr(hashlib, alg)()
    with open(filename, 'rb') as fp:
        block = fp.read(2**16)
        while len(block) != 0:
            sha.update(block)
            block = fp.read(2**16)
    return sha.hexdigest()


def download(remote, local):
    logging.getLogger(__name__).info('Download "{}" -> "{}"'.format(remote, local))
    mkdirs_if_not_exist(local)
    content = requests.get(remote, stream=True)
    if content.status_code != requests.codes['ok']:
        raise requests.HTTPError(response=content)
    with open(local, 'wb') as fp:
        for chunk in content.iter_content(chunk_size=1024):
            fp.write(chunk)


def _topath(url):
    return re.sub(r'https?://', '', url)


class APTDependencyMirror:

    def __init__(self, sources, location):
        self.sources = sources
        self.location = location
        self.packages_to_mirror = set()
        self.filters = []

    def add_filter(self, thefilter):
        logging.getLogger(__name__).info('Add Filter {}.'.format(thefilter))
        self.filters.append(thefilter)

    def _resolve(self):
        """Resolve all add_dependency and add_filter declarations."""
        for filter in self.filters:
            self.packages_to_mirror |= set(filter.addfrom(self))

    def create(self, processes=4, dry_run=False):
        self._resolve()
        logging.getLogger(__name__).info('Download {} packages of approx {:,}kb size.'.format(
            len(self.packages_to_mirror),
            sum((p.size for p in self.packages_to_mirror)) // 1024,
        ))
        if not dry_run:
            self._mirror_metafiles()
            with multiprocessing.Pool(processes) as pool:
                pool.map(self._mirror_package, self.packages_to_mirror)

    def _mirror_metafiles(self):
        for repo in self.sources.repositories:
            for hash, fil in repo.release_file.metafiles:
                url = '/'.join([repo.url, 'dists', repo.dist, fil])
                filename = os.path.join(self.location, _topath(repo.url), 'dists', repo.dist, fil)
                try:
                    download(url, filename)
                    if shafile(filename, 'sha256') != hash:
                        logging.getLogger(__name__).critical('Corrupt file "{}"'.format(filename))
                except requests.HTTPError:
                    logging.getLogger(__name__).warning('URL not found: "{}"'.format(url))
            for component in repo.components:
                for architecture in repo.architectures:
                    for fil in ['Packages', 'Packages.gz', 'Release']:
                        try:
                            url = '/'.join([repo.url, 'dists', repo.dist, component, 'binary-' + architecture, fil])
                            download(
                                url,
                                os.path.join(self.location, _topath(repo.url), 'dists', repo.dist, component, 'binary-' + architecture, fil)
                            )
                        except requests.HTTPError:
                            logging.getLogger(__name__).warning('URL not found: "{}"'.format(url))

    def _mirror_package(self, package, retry_count=1):
        download_url = package.repository.url + '/' + package.filename
        filename = os.path.join(self.location, _topath(package.repository.url), *package.filename.split('/'))

        logging.getLogger(__name__).info('Download {} from "{}" to "{}"'.format(package, download_url, filename))

        if not os.path.exists(filename):
            download(download_url, filename)

        if shafile(filename) != package.sha1:
            if retry_count > 0:
                os.remove(filename)
                self._mirror_package(package, retry_count - 1)
            else:
                logging.getLogger(__name__).critical('Corrupt file "{}"'.format(filename))


class FilterAddArchitectureFromUrl:
    """
    Filter adding all packages of given architecture and url.
    """

    def __init__(self, url, arch):
        self.arch = arch
        self.url = url

    def addfrom(self, mirror: APTDependencyMirror):
        for rep in mirror.sources.repositories:
            if rep.url != self.url:
                continue
            for packs in rep.packages.values():
                for pack in packs:
                    if pack.architecture == self.arch:
                        logging.getLogger(__name__).debug('Adding package "{}"'.format(pack))
                        yield pack

    def __str__(self):
        return '<FilterAddArchitectureFromUrl {} {}>'.format(self.url, self.arch)

    def __repr__(self):
        return str(self)


class FilterAddDependency:
    """
    Filter adding all packages fulfilling given dependency and recursively all of their dependencies.
    This gives the minimal set of packages needed for installing this package.
    """

    def __init__(self, dependency):
        self.dependency = BinaryPackageDependency(dependency)

    def addfrom(self, mirror):
        packs = set()
        for pack in mirror.sources.packages_fulfilling(self.dependency):
            pack.dependencies(mirror.sources, packs)
        for pack in packs:
            logging.getLogger(__name__).debug('Adding package "{}" as dependency of {}'.format(pack, self.dependency))
        return packs

    def __str__(self):
        return '<FilterAddDependency {}>'.format(self.dependency)

    def __repr__(self):
        return str(self)

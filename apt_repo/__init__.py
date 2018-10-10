import bz2
import logging
import gzip
import lzma
import os
import re
import urllib.error
import urllib.request as request
import pydpkg


def __download_raw(url):
    """
    Downloads a binary file

    # Arguments
    url (str): URL to file
    """
    return request.urlopen(url).read()


def _download(url):
    """
    Downloads a UTF-8 encoded file

    # Arguments
    url (str): URL to file
    """
    return __download_raw(url).decode('utf-8')


def _download_compressed(base_url):
    """
    Downloads a compressed file

    It tries out multiple compression algorithms by iterating through the according file suffixes.

    # Arguments
    url (str): URL to file
    """
    decompress = {
        '': lambda c: c,
        '.xz': lambda c: lzma.decompress(c),
        '.gz': lambda c: gzip.decompress(c),
        '.bzip2': lambda c: bz2.decompress(c)
    }

    for suffix, method in decompress.items():
        url = base_url + suffix

        try:
            req = request.urlopen(url)
        except urllib.error.URLError:
            continue
        logging.getLogger(__name__).debug('Download "{}"'.format(url))

        return method(req.read()).decode('utf-8')


def _get_value(content, key):
    match = re.search(r'^' + key + ': (.*)$', content, flags=re.MULTILINE)
    try:
        return match.group(1)
    except AttributeError:
        raise KeyError(content, key)



class ReleaseFile:
    """
    Class that represents a Release file

    # Arguments
    content (str): the content of the Release file
    """
    def __init__(self, content):
        self.content = content.strip()

    @property
    def origin(self):
        return _get_value(self.content, 'Origin')

    @property
    def label(self):
        return _get_value(self.content, 'Label')

    @property
    def suite(self):
        return _get_value(self.content, 'Suite')

    @property
    def version(self):
        return _get_value(self.content, 'Version')

    @property
    def codename(self):
        return _get_value(self.content, 'Codename')

    @property
    def date(self):
        return _get_value(self.content, 'Date')

    @property
    def architectures(self):
        return _get_value(self.content, 'Architectures').split()

    @property
    def components(self):
        return _get_value(self.content, 'Components').split()

    @property
    def description(self):
        return _get_value(self.content, 'Description')


class PackagesFile:
    """
    Class that represents a Packages file

    # Arguments
    content (str): the content of the Packages file
    """
    def __init__(self, content, repository):
        self.content = content.strip()
        self.repository = repository

    @property
    def packages(self):
        """Returns all binary packages in this Packages files"""
        packages = []
        for package_content in self.content.split('\n\n'):
            if not package_content:
                continue

            packages.append(BinaryPackage(package_content, self.repository))

        return packages


class BinaryPackageDependency():
    re_dependency = re.compile(r'^(?P<package_name>\S+?)(?::(?P<architecture>\S+))?(?: \((?P<constraint>>>|<<|>=|=) (?P<version>\S+)\))?$')

    def __init__(self, content):
        if '|' in content:
            self.or_dependencies = [BinaryPackageDependency(d) for d in content.split(' | ')]
            self.package_name = [d.package_name for d in self.or_dependencies]
        else:
            for k, v in self.re_dependency.match(content.strip()).groupdict().items():
                setattr(self, k, v)

    def fulfilled(self, package):
        """Checks if package fulfills this Dependency."""
        if hasattr(self, 'or_dependencies'):
            return any([d.fulfilled(package) for d in self.or_dependencies])
        if self.package_name != package.package and self.package_name not in package.provides:
            return False
        if self.constraint is None:
            return True
        if self.constraint == '>=':
            return pydpkg.Dpkg.compare_versions(package.version, self.version) >= 0
        elif self.constraint == '=':
            return pydpkg.Dpkg.compare_versions(package.version, self.version) == 0
        elif self.constraint == '<<':
            return pydpkg.Dpkg.compare_versions(package.version, self.version) < 0
        elif self.constraint == '>>':
            return pydpkg.Dpkg.compare_versions(package.version, self.version) > 0
        return False

    def __str__(self):
        if hasattr(self, 'or_dependencies'):
            return ' | '.join([str(d) for d in self.or_dependencies])
        return '{} ({} {})'.format(self.package_name, self.constraint, self.version)

    def __repr__(self):
        return str(self)


class BinaryPackage:
    """
    Class that represents a binary Debian package


    # Arguments
    content (str): the section of the Packages file for this specific package
    """
    def __init__(self, content, repository):
        self.content = content.strip()
        self.repository = repository

    @property
    def package(self):
        return _get_value(self.content, 'Package')

    @property
    def version(self):
        return _get_value(self.content, 'Version')

    @property
    def filename(self):
        return _get_value(self.content, 'Filename')

    @property
    def provides(self):
        if hasattr(self, '_cache_provides'):
            return self._cache_provides
        try:
            self._cache_provides = [p.strip() for p in _get_value(self.content, 'Provides').split(',')]
        except KeyError:
            self._cache_provides = []
        return self._cache_provides

    @property
    def recommends(self):
        try:
            return _get_value(self.content, 'Recommends')
        except KeyError:
            return []

    @property
    def sha1(self):
        return _get_value(self.content, 'SHA1')

    @property
    def depends(self):
        if hasattr(self, '_cache_depends'):
            return self._cache_depends
        try:
            self._cache_depends = [BinaryPackageDependency(s) for s in _get_value(self.content, 'Depends').split(',')]
        except KeyError:
            self._cache_depends = []
        return self._cache_depends

    @property
    def predepends(self):
        if hasattr(self, '_cache_predepends'):
            return self._cache_predepends
        try:
            self._cache_predepends = [BinaryPackageDependency(s) for s in _get_value(self.content, 'Pre-Depends').split(',')]
        except KeyError:
            self._cache_predepends = []
        return self._cache_predepends

    @property
    def architecture(self):
        return _get_value(self.content, 'Architecture')

    @property
    def size(self):
        return int(_get_value(self.content, 'Size'))

    def dependencies(self, sources, summed_deps=None):
        if summed_deps is None:
            summed_deps = set()
        summed_deps.add(self)
        logging.getLogger(__name__).debug('Check dependencies of {}'.format(self.package))
        for dep in self.depends + self.predepends:
            if len([p for p in summed_deps if dep.fulfilled(p)]) > 0:
                continue
            packs_fulfilling = []
            for pack in sources.packages_fulfilling(dep):
                packs_fulfilling.append(pack)
                pack.dependencies(sources, summed_deps)
            if len(packs_fulfilling) == 0:
                logging.getLogger(__name__).warning('No package found matching "{}"'.format(dep))
                # raise Exception('No package found matching "{}"'.format(dep))
        return summed_deps

    def __str__(self):
        return '{} {} {}'.format(self.package, self.architecture, self.version)

    def __repr__(self):
        return str(self)


class APTRepository:
    """
    Class that represents a single APT repository

    # Arguments
    url (str): the base URL of the repository
    dist (str): the target distribution
    components (list): the target components

    # Examples
    ```python
    APTRepository('http://archive.ubuntu.com/ubuntu', 'bionic', 'main')
    ```
    """
    def __init__(self, url, dist, components, architectures=['amd64', 'i386']):
        self.url = url
        self.dist = dist
        self.components = components
        self.architectures = architectures

    def get(self, item):
        return self.packages.get(item, [])

    def get_provided(self, item):
        if not hasattr(self, '_cache_provided_packages'):
            packs = self.packages
        return self._cache_provided_packages.get(item, [])

    @staticmethod
    def from_sources_list_entry(entry):
        """
        Instantiates a new APTRepository object out of a sources.list file entry

        # Examples
        ```python
        APTRepository.from_sources_list_entry('deb http://archive.ubuntu.com/ubuntu bionic main')
        ```
        """
        split_entry = entry.split()

        url = split_entry[1]
        dist = split_entry[2]
        components = split_entry[3:]

        return APTRepository(url, dist, components)

    @property
    def all_components(self):
        """Returns the all components of this repository"""
        return self.release_file.components

    @property
    def release_file(self):
        """Returns the Release file of this repository"""
        url = '/'.join([
            self.url,
            'dists',
            self.dist,
            'Release'
        ])

        release_content = _download(url)

        if release_content is None:
            raise urllib.error.URLError('No release file found under "{}"'.format(url))

        return ReleaseFile(release_content)

    @property
    def packages(self):
        if hasattr(self, '_cache_packages'):
            return self._cache_packages
        self._cache_packages = {}
        for arch in self.architectures:
            for component in self.components:
                packs = self.get_binary_packages_by_component(component, arch)
                for pack in packs:
                    if pack.package in self._cache_packages:
                        self._cache_packages[pack.package].append(pack)
                    else:
                        self._cache_packages[pack.package] = [pack]

        self._cache_provided_packages = {}
        for name, packs in self._cache_packages.items():
            for pack in packs:
                for provides in [name] + pack.provides:
                    if provides in self._cache_provided_packages:
                        self._cache_provided_packages[provides].add(pack)
                    else:
                        self._cache_provided_packages[provides] = {pack}

        return self._cache_packages

    def get_binary_packages_by_component(self, component, arch='amd64'):
        """
        Returns all binary packages of this repository for a given component

        # Arguments
        component (str): the component to return packages for
        arch (str): the architecture to return packages for, default: 'amd64'
        """
        url = '/'.join([
            self.url,
            'dists',
            self.dist,
            component,
            'binary-' + arch,
            'Packages'
        ])

        packages_file = _download_compressed(url)

        if packages_file is None:
            raise urllib.error.URLError('No release file found under "{}"'.format(url))

        return PackagesFile(packages_file, self).packages

    def get_binary_packages(self, name, version=None):
        return [p for p in self.packages.get(name, []) if ((version and p.version.startswith(version)) or version is None)]

    def packages_fulfilling(self, dependency):
        names = dependency.package_name
        if isinstance(names, str):
            names = [names]
        for name in names:
            for pack in self.get_provided(name):
                if dependency.fulfilled(pack):
                    yield pack


class APTSources:
    """
    Class that represents a collection of APT repositories

    # Arguments
    repositories (list): list of APTRepository objects
    """
    def __init__(self, repositories):
        self.repositories = repositories

    def get(self, name):
        return set(sum([rep.get(name) for rep in self.repositories], []))

    @property
    def architectures(self):
        return set(sum([rep.architectures for rep in self.repositories], []))

    def packages_fulfilling(self, dependency):
        for rep in self.repositories:
            yield from rep.packages_fulfilling(dependency)

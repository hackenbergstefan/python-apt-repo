import bz2
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
    def __init__(self, content):
        try:
            self.package_name, constraint_version = content.strip().split(' ', maxsplit=1)
            self.constraint, self.version = constraint_version[1:-1].split(' ')
        except ValueError:
            self.package_name = content.strip()
            self.constraint = self.version = None

    def fulfilled(self, package):
        """Checks if package fulfills this Dependency."""
        if self.package_name != package.package:
            return False
        if self.constraint is None:
            return True
        if self.constraint == '>=':
            return pydpkg.Dpkg.compare_versions(package.version, self.version) >= 0
        elif self.constraint == '=':
            return pydpkg.Dpkg.compare_versions(package.version, self.version) == 0
        return False

    def __str__(self):
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
    def sha1(self):
        return _get_value(self.content, 'SHA1')

    @property
    def depends(self):
        try:
            return [BinaryPackageDependency(s) for s in _get_value(self.content, 'Depends').split(',')]
        except KeyError:
            return []

    @property
    def architecture(self):
        return _get_value(self.content, 'Architecture')

    @property
    def size(self):
        return int(_get_value(self.content, 'Size'))

    def dependencies(self, repos, summed_deps=None):
        if summed_deps is None:
            summed_deps = set()
        summed_deps.add(self)
        for dep in self.depends:
            for rep in repos:
                for pack in rep.get_binary_packages(dep.package_name):
                    if pack not in summed_deps and dep.fulfilled(pack):
                        pack.dependencies(repos, summed_deps)
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

    def __getitem__(self, item):
        return self.get_packages_by_name(item)

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
        if hasattr(self, '_packages'):
            return self._packages
        self._packages = []
        for arch in self.architectures:
            for component in self.components:
                self._packages.extend(self.get_binary_packages_by_component(component, arch))

        return self._packages

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

    def get_package(self, name, version):
        """
        Returns a single binary package

        # Arguments
        name (str): name of the package
        version (str): version of the package
        """
        for package in self.packages:
            if package.package == name and package.version == version:
                return package

        raise KeyError(name, version)

    def get_package_url(self, name, version):
        """
        Returns the URL for a single binary package

        # Arguments
        name (str): name of the package
        version (str): version of the package
        """
        package = self.get_package(name, version)

        return os.path.join(self.url, package.filename)

    def get_packages_by_name(self, name):
        """
        Returns the list of available packages (and it's available versions) for a specific package name

        # Arguments
        name (str): name of the package
        """

        packages = []

        for package in self.packages:
            if package.package == name:
                packages.append(package)

        return packages

    def get_binary_packages(self, name, version=None):
        return [p for p in self.packages if p.package == name and ((version and p.version.startswith(version)) or version is None)]


class APTSources:
    """
    Class that represents a collection of APT repositories

    # Arguments
    repositories (list): list of APTRepository objects
    """
    def __init__(self, repositories):
        self.repositories = repositories

    def __getitem__(self, item):
        return self.get_packages_by_name(item)

    @property
    def packages(self):
        """Returns all binary packages of all APT repositories"""
        packages = []

        for repo in self.repositories:
            packages.extend(repo.packages)

        return packages

    def get_package(self, name, version):
        """
        Returns a single binary package

        # Arguments
        name (str): the name of the package
        version (str): the version of the package
        """
        for repo in self.repositories:
            try:
                return repo.get_package(name, version)
            except KeyError:
                pass

        raise KeyError(name, version)

    def get_package_url(self, name, version):
        """
        Returns the URL of a single binary package

        # Arguments
        name (str): the name of the package
        version (str): the version of the package
        """
        for repo in self.repositories:
            try:
                return repo.get_package_url(name, version)
            except KeyError:
                pass

        raise KeyError(name, version)

    def get_packages_by_name(self, name):
        """
        Returns the list of available packages (and it's available versions) for a specific package name

        # Arguments
        name (str): name of the package
        """

        packages = []

        for repo in self.repositories:
            packages.extend(repo.get_packages_by_name(name))

        return packages

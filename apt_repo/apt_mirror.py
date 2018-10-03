from . import BinaryPackageDependency


class APTDependencyMirror:

    def __init__(self, repositories):
        self.repositories = repositories
        self.packages_to_mirror = set()

    def add_package(self, package):
        if isinstance(package, list):
            [self.add_package(p) for p in package]
        else:
            self._add_dependencies(package)

    def _add_dependencies(self, package):
        if isinstance(package, str):
            package_name = package
        elif isinstance(package, BinaryPackageDependency):
            package_name = package.package_name

        for rep in self.repositories:
            for pack in rep.get_binary_packages(package_name):
                if isinstance(package, BinaryPackageDependency) and package.fulfilled(pack):
                    self.packages_to_mirror |= pack.dependencies(self.repositories)

    def create(self, location, dist, component):
        raise NotImplementedError

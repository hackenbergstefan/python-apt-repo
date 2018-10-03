#!/usr/bin/env python

import sys
from apt_repo import APTRepository, BinaryPackageDependency
from apt_repo.apt_mirror import APTDependencyMirror


def main():
    rep = APTRepository('https://dl.winehq.org/wine-builds/ubuntu', 'xenial', ['main'])
    for pack in [pack for pack in rep.get_binary_packages_by_component('main', 'i386') + rep.get_binary_packages_by_component('main', 'amd64') if pack.package == sys.argv[1]]:
        print(pack.package, pack.version, pack.depends)
        # print(pack._BinaryPackage__content)


def main2():
    rep = apt_repo.APTRepository('https://dl.winehq.org/wine-builds/ubuntu', 'xenial', ['main'])
    dependency = rep.get_packages_by_name('wine-stable')[-1].depends[1]
    print(dependency.fulfilled(rep.get_packages_by_name('wine-stable-amd64')[-2]))


def main3():
    reps = [
        APTRepository('http://de.archive.ubuntu.com/ubuntu', 'xenial-updates', ['main']),
        APTRepository('http://de.archive.ubuntu.com/ubuntu', 'xenial', ['main']),
        APTRepository('https://dl.winehq.org/wine-builds/ubuntu', 'xenial', ['main']),
    ]
    # rep = apt_repo.APTRepository('http://security.ubuntu.com/ubuntu', 'xenial', ['main'])
    for rep in reps:
        for pack in rep.get_binary_packages(sys.argv[1], sys.argv[2] if len(sys.argv) >= 3 else None):
            print(pack, pack.depends)
            for p in sorted(pack.dependencies(reps), key=lambda p: str(p)):
                print(p, p.filename)


def main4():
    reps = [
        APTRepository('http://de.archive.ubuntu.com/ubuntu', 'xenial-updates', ['main'], ['i386']),
        APTRepository('http://de.archive.ubuntu.com/ubuntu', 'xenial', ['main'], ['i386']),
        APTRepository('https://dl.winehq.org/wine-builds/ubuntu', 'xenial', ['main']),
    ]

    mirror = APTDependencyMirror(reps)
    mirror.add_package(BinaryPackageDependency('wine-stable (>= 3.0.3)'))
    print(mirror.packages_to_mirror)


if __name__ == '__main__':
    main4()

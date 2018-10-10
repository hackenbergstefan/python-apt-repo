#!/usr/bin/env python

import logging
import sys
from apt_repo import APTRepository, BinaryPackageDependency, APTSources
from apt_repo.apt_mirror import APTDependencyMirror

sources = APTSources([
    APTRepository('http://de.archive.ubuntu.com/ubuntu', 'bionic', ['main', 'restricted', 'universe'], ['i386']),
    APTRepository('http://de.archive.ubuntu.com/ubuntu', 'bionic-updates', ['main', 'restricted', 'universe'], ['amd64', 'i386']),
    APTRepository('http://de.archive.ubuntu.com/ubuntu', 'bionic-security', ['main', 'restricted', 'universe'], ['i386', 'amd64']),
    APTRepository('https://dl.winehq.org/wine-builds/ubuntu', 'bionic', ['main']),
    APTRepository('https://download.mono-project.com/repo/ubuntu', 'vs-bionic', ['main'], ['amd64']),
])


def main2():
    rep = APTRepository('https://dl.winehq.org/wine-builds/ubuntu', 'xenial', ['main'])
    dependency = rep.get_packages_by_name('wine-stable')[-1].depends[1]
    print(dependency.fulfilled(rep.get_packages_by_name('wine-stable-amd64')[-2]))


def main3():
    for rep in reps:
        for pack in rep.get_binary_packages(sys.argv[1], sys.argv[2] if len(sys.argv) >= 3 else None):
            print(pack, pack.depends)
            for p in sorted(pack.dependencies(reps), key=lambda p: str(p)):
                print(p, p.filename)


def main4():
    logging.basicConfig(level=logging.DEBUG)
    mirror = APTDependencyMirror(sources)
    # mirror.add_package('winehq-stable (>= 3.0.3)')
    mirror.add_package('monodevelop')
    print(mirror.packages_to_mirror)
    mirror.create('E:/mymirror', 'local-bionic', 'main')

def main5():
    # rep = sources.repositories[-1]
    # pack = rep.get('monodevelop')[0]
    # deps = pack.dependencies(rep)

    mirror = APTDependencyMirror(sources, 'E:\mymirror2')
    mirror.add_package('winehq-stable (>= 3.0.3)')
    mirror.add_package('winetricks')
    mirror.add_package('monodevelop')
    mirror._mirror_metafiles()


if __name__ == '__main__':
    for handler in logging.root.handlers:
        logging.root.removeHandler(handler)
    logging.basicConfig(level=logging.INFO)
    main5()

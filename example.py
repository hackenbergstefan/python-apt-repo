#!/usr/bin/env python

import logging

from apt_repo import APTRepository, APTSources
from apt_repo.apt_mirror import APTDependencyMirror, FilterAddArchitectureFromUrl, FilterAddDependency


"""
Example to show usage of APTDependencyMirror

This example mirrors all amd64 packages from repositories with url 'http://de.archive.ubuntu.com/ubuntu'
and all packages which are needed to install 'winehq-stable (>= 3.0.3)'.
"""

sources = APTSources([
    APTRepository('http://de.archive.ubuntu.com/ubuntu', 'bionic', ['main', 'restricted', 'universe']),
    APTRepository('http://de.archive.ubuntu.com/ubuntu', 'bionic-updates', ['main', 'restricted', 'universe'], ['amd64', 'i386']),
    APTRepository('http://de.archive.ubuntu.com/ubuntu', 'bionic-security', ['main', 'restricted', 'universe'], ['i386', 'amd64']),
    APTRepository('https://dl.winehq.org/wine-builds/ubuntu', 'bionic', ['main']),
    APTRepository('https://download.mono-project.com/repo/ubuntu', 'vs-bionic', ['main'], ['amd64']),
])


def main():
    mirror = APTDependencyMirror(sources, './mymirror')
    mirror.add_filter(FilterAddArchitectureFromUrl('http://de.archive.ubuntu.com/ubuntu', 'amd64'))
    mirror.add_filter(FilterAddDependency('winehq-stable (>= 3.0.3)'))
    mirror.create(dry_run=False)


if __name__ == '__main__':
    for handler in logging.root.handlers:
        logging.root.removeHandler(handler)
    logging.basicConfig(level=logging.INFO)
    main()

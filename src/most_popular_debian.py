#!/usr/bin/env python3

# Copyright 2026 - Armijn Hemel
# Licensed under the terms of the Apache 2.0 license
# SPDX-License-Identifier: Apache-2.0

import collections
import datetime
import graphlib
import hashlib
import json
import lzma
import pathlib
import sys

# external dependencies
import click
import packageurl
import requests

DEBIAN_BASE_URLS = ['https://ftp.debian.org/debian/',
                    #'https://ftp.nluug.nl/pub/os/Linux/distr/debian',
                   ]

UBUNTU_BASE_URLS = ['https://ftp.nluug.nl/pub/os/Linux/distr/ubuntu',
                    'https://nl.archive.ubuntu.com/ubuntu']

# https://en.wikipedia.org/wiki/Debian_release_version_history
DEBIAN_VERSIONS = {'11.11': 'bullseye',
                   '12.14': 'bookworm',
                   '13.5': 'trixie',
                  }

# https://en.wikipedia.org/wiki/Ubuntu_version_history
# versions tend to disappear from the Ubuntu mirrors every now and then.
UBUNTU_VERSIONS = {'14.04': 'trusty',
                   '16.04': 'xenial',
                   '18.04': 'bionic',
                   '20.04': 'focal',
                   '22.04': 'jammy',
                   '24.04': 'noble',
                   '25.04': 'plucky',
                   '25.10': 'questing',
                   '26.04': 'resolute',
                   '26.10': 'stonking',
                  }


@click.command(short_help='Crawl metadata for a version of Debian (derivative)')
@click.option('--name', '-n', required=True, help='Debian (derivative) name',
              type=click.Choice(['debian', 'ubuntu'], case_sensitive=False))
@click.option('--distro', '-d', required=True, help='version (codename or number)')
@click.option('--out-directory', '-o', required=True, help='Output directory',
              type=click.Path(exists=True, path_type=pathlib.Path))
@click.option('--component', 'filter_component', help='Distro component')
@click.option('--verbose', '-v', is_flag=True)
def crawl_debian_metadata(name, distro, out_directory, filter_component, verbose):
    '''Download all source packages for a version of Ubuntu'''
    if name == 'debian':
        if not (distro in DEBIAN_VERSIONS or distro in DEBIAN_VERSIONS.values()):
            print(f'Invalid Debian \'{distro}\', exiting', file=sys.stderr)
            sys.exit(1)
        if distro in DEBIAN_VERSIONS:
            distro = DEBIAN_VERSIONS[distro]
    elif name == 'ubuntu':
        if not (distro in UBUNTU_VERSIONS or distro in UBUNTU_VERSIONS.values()):
            print(f'Invalid Ubuntu \'{distro}\', exiting', file=sys.stderr)
            sys.exit(1)
        if distro in UBUNTU_VERSIONS:
            distro = UBUNTU_VERSIONS[distro]

    # set the User Agent and Authorization header for each user request
    # (optional, some FTP servers don't like this)
    user_agent_string = "CodeSupply-crawler/0.1"
    headers = {'user-agent': user_agent_string}

    # grab the 'InRelease' file from the FTP server and process
    if name == 'debian':
        base_url = f'{DEBIAN_BASE_URLS[0]}/dists/{distro}'
        request_url = f'{DEBIAN_BASE_URLS[0]}/dists/{distro}/InRelease'
    elif name == 'ubuntu':
        base_url = f'{UBUNTU_BASE_URLS[0]}/dists/{distro}'

    request_url = f'{base_url}/InRelease'
    request = requests.get(request_url)

    # now first check the headers to see if it is OK to do more requests
    if request.status_code != 200:
        print("Cannot download 'InRelease' file, exiting", file=sys.stderr)
        sys.exit(2)

    architectures = []
    components = []
    sha256 = {}

    inrelease = request.text
    in_sha256 = False
    for line in inrelease.splitlines():
        if line.startswith('-----BEGIN PGP SIGNATURE-----'):
            break
        if not line.startswith(' '):
            in_sha256 = False

        if in_sha256:
            checksum, size, path = line.strip().split()
            # ignore debian-installer for now
            if 'debian-installer' in path:
                continue

            if not ('Packages.xz' in path or 'Sources.xz' in path):
                continue

            component = path.split('/')[0]
            if 'Packages.xz' in path:
                architecture = path.split('/')[1].split('-')[1]
            elif 'Sources.xz' in path:
                architecture = 'source'

            if not component in sha256:
                sha256[component] = {}

            sha256[component][architecture] = (checksum, int(size), path)

        if line.startswith('Architectures:'):
            architectures = line.strip().split()[1:]
        elif line.startswith('Components:'):
            components = line.strip().split()[1:]
        elif line.startswith('SHA256:'):
            in_sha256 = True

    if not architectures or not components:
        print("Invalid 'InRelease' file, architectures or components missing, exiting",
              file=sys.stderr)
        sys.exit(2)

    if filter_component and filter_component not in components:
        print(f"Invalid 'component' value, not in {components}, exiting",
              file=sys.stderr)
        sys.exit(2)

    # Process source archives to extract all the metadata
    source_to_binaries = {}
    binaries_to_source = {}

    # Store how often build dependencies are used in the Sources.xz files.
    # The dependencies are the names of *binary* packages, that eventually need
    # to be mapped back to source code. The dependencies could be from a different
    # component, so these should be processed first. Some of the components are
    # virtual packages (defined with 'Provides:').
    build_depends = collections.Counter()

    # Then process all the packages for the different components and architectures
    for component in components:
        if filter_component and component != filter_component:
            continue

        # Without source package information it is impossible
        # to map data back to source packages
        if not 'source' in sha256[component]:
            continue

        (checksum, size, path) = sha256[component]['source']

        # download the relevant file
        request_url = f'{base_url}/{path}'
        request = requests.get(request_url)

        if request.status_code != 200:
            print(f"Cannot download '{request_url}' exiting", file=sys.stderr)
            sys.exit(2)

        # Then process the sources data
        sources_xz = request.content
        if len(sources_xz) != size:
            print(f"Invalid size for '{request_url}' exiting", file=sys.stderr)
            sys.exit(2)

        # then decompress the retrieved data
        try:
            sources = lzma.decompress(sources_xz)
        except:
            print(f"Cannot decompress '{request_url}' exiting", file=sys.stderr)
            sys.exit(2)

        # Information about binary files can be spread across multiple lines,
        # so some juggling is needed to properly process the lines.
        in_binary = False
        for line in sources.splitlines():
            line = line.decode().strip()
            if ':' in line:
                in_binary = False
            if in_binary:
                binaries = list(filter(lambda x: x != '', map(lambda x: x.strip(), line.split(','))))
                source_to_binaries[package_name] += binaries
                for b in binaries:
                    binaries_to_source[b] = package_name
            if line.startswith('Package:'):
                package_name = line.split(':')[1].strip()
            elif line.startswith('Binary:'):
                in_binary = True
                binaries = list(filter(lambda x: x != '', map(lambda x: x.strip(), line.split(':')[1].strip().split(','))))

                source_to_binaries[package_name] = binaries
                for b in binaries:
                    binaries_to_source[b] = package_name
            elif line.startswith('Build-Depends:') or line.startswith('Build-Depends-Indep:') or line.startswith('Build-Depends-Arch:'):
                depends = line.split(':', maxsplit=1)[1].split(',')
                for d in depends:
                    build_dependency = d.strip().split()[0].rsplit(':', maxsplit=1)[0]
                    build_depends.update([build_dependency])

        for architecture in sha256[component]:
            if architecture == 'source':
                continue
            (checksum, size, path) = sha256[component][architecture]

            # download the relevant path and process the contents

    # Pretty print the most used build dependencies.
    for binary, count in build_depends.most_common():
        if binary in binaries_to_source:
            print(binary, binaries_to_source[binary])

if __name__ == "__main__":
    crawl_debian_metadata()

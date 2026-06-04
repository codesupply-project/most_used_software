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
        distro = DEBIAN_VERSIONS.get(distro, distro)
    elif name == 'ubuntu':
        if not (distro in UBUNTU_VERSIONS or distro in UBUNTU_VERSIONS.values()):
            print(f'Invalid Ubuntu \'{distro}\', exiting', file=sys.stderr)
            sys.exit(1)
        distro = UBUNTU_VERSIONS.get(distro, distro)

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

            if not architecture in sha256:
                sha256[architecture] = {}

            sha256[architecture][component] = (checksum, int(size), path)

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

    if 'source' not in sha256:
        print("No 'source' archtitecture found, exiting", file=sys.stderr)
        sys.exit(3)

    # Process source archives to extract all the metadata
    source_to_binaries = {}
    binaries_to_source = {}

    # Store how often build dependencies are used in the Sources.xz files.
    # The dependencies are the names of *binary* packages, that eventually need
    # to be mapped back to source code. The dependencies could be from a different
    # component, so these should be processed first. Some of the components are
    # virtual packages (defined with 'Provides:').
    build_dependencies = collections.Counter()
    build_alts = set()

    # first process the source code "architecture"
    for component in sha256['source']:
        if filter_component and component != filter_component:
            continue

        (checksum, size, path) = sha256['source'][component]

        # download the relevant file
        request_url = f'{base_url}/{path}'
        request = requests.get(request_url)

        if request.status_code != 200:
            print(f"Cannot download '{request_url}' exiting", file=sys.stderr)
            sys.exit(2)

        # sanity check the retrieved data
        sources_xz = request.content
        if len(sources_xz) != size:
            print(f"Invalid size for '{request_url}' exiting", file=sys.stderr)
            sys.exit(2)

        if hashlib.sha256(sources_xz).hexdigest() != checksum:
            print(f"Invalid checksum for '{request_url}' exiting", file=sys.stderr)
            sys.exit(2)

        # decompress the retrieved data
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
                    # split alternatives. These should be treated slightly differently
                    # because some of these packages are possibly not even interesting
                    # and equivalent to a NOP, in case one of the other alternatives
                    # satisfies the dependency.
                    if '|' in d:
                        alts = []
                        alt_deps = d.split('|')
                        for a in alt_deps:
                            build_dependency = a.strip().split()[0].rsplit(':', maxsplit=1)[0].strip()
                            alts.append(build_dependency)
                        build_alts.update([tuple(alts)])
                    else:
                        build_dependency = d.strip().split()[0].rsplit(':', maxsplit=1)[0].strip()
                        build_dependencies.update([build_dependency])

    # Then process all the packages for the different architectures and components that are not source
    for architecture in architectures:
        if architecture in ['all', 'source']:
            continue

        provides_to_source = {}
        dependencies = collections.Counter()
        dep_alts = set()

        for component in sha256[architecture]:
            if filter_component and component != filter_component:
                continue

            (checksum, size, path) = sha256[architecture][component]

            # download the relevant path and process the contents
            request_url = f'{base_url}/{path}'
            request = requests.get(request_url)

            if request.status_code != 200:
                print(f"Cannot download '{request_url}' skipping", file=sys.stderr)
                continue

            # sanity check the retrieved data
            packages_xz = request.content
            if len(packages_xz) != size:
                print(f"Invalid size for '{request_url}' skipping", file=sys.stderr)
                continue

            if hashlib.sha256(packages_xz).hexdigest() != checksum:
                print(f"Invalid checksum for '{request_url}' skipping", file=sys.stderr)
                continue

            # decompress the retrieved data
            try:
                packages = lzma.decompress(packages_xz)
            except:
                print(f"Cannot decompress '{request_url}' exiting", file=sys.stderr)
                sys.exit(2)

            for line in packages.splitlines():
                line = line.decode().strip()
                if line.startswith('Package:'):
                    source_name = ''
                    package_name = line.split(':')[1].strip()
                elif line.startswith('Source:'):
                    source_name = line.split(':')[1].split('(')[0].strip()
                elif line.startswith('Provides:'):
                    provides = line.split(':', maxsplit=1)[1].split(',')
                    for p in provides:
                        provide = p.strip().split()[0].rsplit(':', maxsplit=1)[0].strip()
                        if provide not in provides_to_source:
                            provides_to_source[provide] = set()
                        if source_name:
                            provides_to_source[provide].add(source_name)
                        else:
                            provides_to_source[provide].add(package_name)
                elif line.startswith('Depends:') or line.startswith('Pre-Depends:'):
                    depends = line.split(':', maxsplit=1)[1].split(',')
                    for d in depends:
                        # split alternatives. These should be treated slightly differently
                        # because some of these packages are possibly not even interesting
                        # and equivalent to a NOP, in case one of the other alternatives
                        # satisfies the dependency.
                        if '|' in d:
                            alts = []
                            alt_deps = d.split('|')
                            for a in alt_deps:
                                dependency = a.strip().split()[0].rsplit(':', maxsplit=1)[0].strip()
                                alts.append(dependency)
                            dep_alts.update([tuple(alts)])
                        else:
                            dependency = d.strip().split()[0].rsplit(':', maxsplit=1)[0].strip()
                            dependencies.update([dependency])


        # Pretty print the most used build dependencies.
        # These should either be in actual packages or virtual packages.
        for binary, count in build_dependencies.most_common():
            if binary in binaries_to_source:
                pass
            elif binary in provides_to_source:
                pass
            else:
                # it could be that the binary is an alternative that
                # has already been fullfilled
                pass

if __name__ == "__main__":
    crawl_debian_metadata()

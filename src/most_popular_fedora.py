#!/usr/bin/env python3

# Copyright 2026 - Armijn Hemel
# Licensed under the terms of the Apache 2.0 license
# SPDX-License-Identifier: Apache-2.0

import collections
import copy
import datetime
import graphlib
import gzip
import hashlib
import io
import pathlib
import sys
import xml.dom

# external dependencies
import click
import defusedxml.ElementTree as et
import defusedxml.minidom
import packageurl
import requests
import zstandard


# supported fedora versions tend to be on mirrors,
# after which they are moved to the Fedora archive.
FEDORA_BASE_URLS = ['https://dl.fedoraproject.org/pub/fedora/linux',
                    'https://ftp.nluug.nl/pub/os/Linux/distr/fedora/linux',
                   ]

# the archive where old versions of Fedora live
FEDORA_ARCHIVE_URL = 'http://archives.fedoraproject.org/pub/archive/fedora/linux'

# a list of historically valid editions. This should be kept in sync with Fedora
VALID_EDITIONS = ['COSMIC-Atomic',
                  'Cloud',
                  'CloudImages',
                  'Cloud Atomic',
                  'Container',
                  'Docker',
                  'Everything',
                  'Fedora',
                  'KDE',
                  'Kinoite',
                  'Labs',
                  'Modular',
                  'Onyx',
                  'Sericea',
                  'Server',
                  'Silverblue',
                  'Workstation',
                 ]


@click.command(short_help='Crawl metadata for a version of Fedora')
@click.option('--distro', '-d', required=True, help='version number', type=click.INT)
@click.option('--out-directory', '-o', required=True, help='Output directory',
              type=click.Path(exists=True, path_type=pathlib.Path))
@click.option('--edition', 'edition', type=click.Choice(VALID_EDITIONS),
              help='Distro edition (Everything, Server, Cloud, etc.)')
@click.option('--architecture', '-a', 'architecture', required=True,
              help='Architecture (aarch64, x86_64, source, etc.)')
@click.option('--cache', default=False, is_flag=True, help='Use cached results')
@click.option('--verbose', '-v', is_flag=True)
def crawl_fedora_metadata(distro, out_directory, edition, architecture, cache, verbose):
    '''Download all source packages for a version of Fedora'''
    if distro < 1:
        raise click.ClickException(f"Invalid Fedora Linux {distro}")

    # Fedora Core 1 used a different download layout.
    # It is also from 2003 and is quite old.
    if distro == 1:
        raise click.ClickException("Fedora Core 1 is not supported. It's too old.")

    # editions were only introduced in later versions of Fedora
    have_editions = True
    if distro < 7:
        have_editions = False

    if have_editions and not edition:
        raise click.ClickException(f"parameter 'edition' is required for Fedora Linux {distro}")

    # set the User Agent and Authorization header for each user request
    # (optional, some FTP servers don't like this)
    user_agent_string = "CodeSupply-crawler/0.1"
    headers = {'user-agent': user_agent_string}

    # Every version < 42 is only hosted on the archive FTP mirror.
    # This should be kept in sync with whenever new releases appear
    # and the older ones are moved to the archive.
    archived = False
    if distro < 42:
        archived = True

    # Before Fedora 7 it was known as Fedora Core and data is stored
    # in a different download directory than later versions.
    dl_dir = 'releases'
    if distro < 7:
        dl_dir = 'core'

    if have_editions:
        download_subdir = pathlib.Path(dl_dir) / str(distro) / edition / architecture
    else:
        download_subdir = pathlib.Path(dl_dir) / str(distro) / architecture

    if architecture == 'source':
        repomd_directory = pathlib.Path('tree/repodata')
    else:
        repomd_directory = pathlib.Path('os/repodata')

    # create a cache directory that (mostly) mirrors the Fedora FTP layout
    cache_directory = out_directory / download_subdir / repomd_directory

    repomd_file = cache_directory / 'repomd.xml'

    if not (cache and repomd_file.exists()):
        if archived:
            base_url = f'{FEDORA_ARCHIVE_URL}/{download_subdir}/{repomd_directory}'
        else:
            base_url = f'{FEDORA_BASE_URLS[0]}/{download_subdir}/{repomd_directory}'

        request_url = f'{base_url}/repomd.xml'
        request = requests.get(request_url)

        # now first check the headers to see if it is OK to do more requests
        if request.status_code != 200:
            print(f"Cannot download '{repomd_file}' file, exiting", file=sys.stderr)
            sys.exit(2)

        repomd = request.text

        # sanity check to see if the XML file is valid
        try:
            repomd_contents = defusedxml.minidom.parseString(repomd)
        except:
            print("Cannot parse 'repomd.xml' file, exiting", file=sys.stderr)
            sys.exit(2)

        # create the out directory
        cache_directory.mkdir(exist_ok=True, parents=True)

        # write the repomd.xml file
        with open(cache_directory / 'repomd.xml', 'w') as repo:
            repo.write(repomd)
    else:
        with open(repomd_file, 'r') as repo:
            repomd = repo.read()
            repomd_contents = defusedxml.minidom.parseString(repomd)

    # process the repomd.xml file to extract information from primary and group (comps)
    # and optionally other and filelists (TODO)
    repomd_elements = {}
    for i in repomd_contents.documentElement.childNodes:
        if i.nodeType == xml.dom.Node.ELEMENT_NODE:
            if i.tagName == 'data':
                element_type = i.getAttribute('type')
                if element_type not in ['primary', 'group']:
                    continue

                repomd_elements[element_type] = {}

                # grab 'location' for download and 'checksum' for verification
                for c in i.childNodes:
                    if c.nodeType == xml.dom.Node.ELEMENT_NODE:
                        if c.tagName == 'location':
                            location = c.getAttribute('href')
                            repomd_elements[element_type]['location'] = location
                        elif c.tagName == 'checksum':
                            # traverse the child nodes to get the data
                            checksum_type = c.getAttribute('type')
                            repomd_elements[element_type]['checksum_type'] = checksum_type
                            for cc in c.childNodes:
                                if cc.nodeType == xml.dom.Node.TEXT_NODE:
                                    checksum = cc.data.strip()
                                    repomd_elements[element_type]['checksum'] = checksum

    # download the (compressed) data for each element and (optionally) write to disk
    for elem_type, elem_dict in repomd_elements.items():
        if 'location' not in elem_dict:
            continue

        # There is some overlap between the location and the directory in which repomd.xml was found
        elem_file = cache_directory.parent / elem_dict['location']

        if not (cache and elem_file.exists()):
            if archived:
                base_url = f'{FEDORA_ARCHIVE_URL}/{download_subdir}/{repomd_directory.parent}'
            else:
                base_url = f'{FEDORA_BASE_URLS[0]}/{download_subdir}/{repomd_directory.parent}'

            request_url = f'{base_url}/{elem_dict['location']}'
            request = requests.get(request_url)

            # now first check the headers to see if it is OK to do more requests
            if request.status_code != 200:
                print(f"Cannot download '{elem_dict['location']}' file, exiting", file=sys.stderr)
                sys.exit(2)

            elem_content = request.content

            # sanity check the downloaded data using the checksum,
            # depending on the checksum type
            if elem_dict['checksum_type'] == 'sha':
                if elem_dict['checksum'] != hashlib.sha1(elem_content).hexdigest():
                    print(f"Invalid checksum for '{elem_dict['location']}', exiting", file=sys.stderr)
                    sys.exit(2)
            elif elem_dict['checksum_type'] == 'sha256':
                if elem_dict['checksum'] != hashlib.sha256(elem_content).hexdigest():
                    print(f"Invalid checksum for '{elem_dict['location']}', exiting", file=sys.stderr)
                    sys.exit(2)
            else:
                # unknown checksum type, add support!
                print(f"Unsupported checksum for '{elem_dict['location']}', add support!", file=sys.stderr)
                sys.exit(2)

            # create the out directory
            cache_directory.mkdir(exist_ok=True, parents=True)

            # write the repomd.xml file
            with open(elem_file, 'wb') as e_file:
                e_file.write(elem_content)
        else:
            with open(elem_file, 'rb') as e_file:
                elem_content = e_file.read()

        # turn the XML into a BytesIO object so it can easily be read
        # by ElementTree, optionally decompress the data first
        if pathlib.Path(e_file.name).suffix == '.xml':
            elem_xml = io.BytesIO(elem_content)
        elif pathlib.Path(e_file.name).suffix == '.gz':
            elem_xml = io.BytesIO(gzip.decompress(elem_content))
        elif pathlib.Path(e_file.name).suffix == '.bz2':
            elem_xml = io.BytesIO(bz2.decompress(elem_content))
        elif pathlib.Path(e_file.name).suffix == '.zst':
            elem_xml = io.BytesIO(zstandard.ZstdDecompressor().stream_reader(elem_content).read())

        # then walk the XML results
        if elem_type == 'primary':
            packages = []
            package_names = set()
            for _, element in et.iterparse(elem_xml):
                if element.tag == '{http://linux.duke.edu/metadata/common}package':
                    if element.get('type') != 'rpm':
                        # cleanup to reduce memory usage
                        element.clear()
                        continue

                    package = {}

                    # extract the interesting data
                    for child in element:
                        if child.tag == '{http://linux.duke.edu/metadata/common}name':
                            package['name'] = child.text
                        elif child.tag == '{http://linux.duke.edu/metadata/common}version':
                            version = child.attrib['ver']
                            release = child.attrib['rel']
                        elif child.tag == '{http://linux.duke.edu/metadata/common}url':
                            if child.text:
                                package['url'] = child.text
                        elif child.tag == '{http://linux.duke.edu/metadata/common}format':
                            for format_child in child:
                                if format_child.tag == '{http://linux.duke.edu/metadata/rpm}sourcerpm':
                                    if format_child.text:
                                        source_pkg = format_child.text.rsplit('-', maxsplit=2)[0]
                                    else:
                                        source_pkg = package['name']

                    # find duplicates, for example for different architectures (x86-64, i686)
                    if package['name'] in package_names:
                        # cleanup to reduce memory usage
                        element.clear()
                        continue

                    package_names.add(package['name'])
                    packages.append(package)

                    # cleanup to reduce memory usage
                    element.clear()

        elif elem_type == 'group':
            pass


if __name__ == "__main__":
    crawl_fedora_metadata()

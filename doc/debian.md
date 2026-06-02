# Finding the most used open source software in Debian and Debian derivatives

Metadata about packages in Debian (and derivatives) is stored in the [Debian
repository format][debian_repository]. Each version is stored in a separate
directory with the name of the version (such as the names of
[Debian versions][debian_versions] or [Ubuntu versions][ubuntu_versions],
and with the metadata files in well known locations.

## Finding the most used software by creating a dependency graph

For each package in the metadata files a dependency graph can be created. By
walking this graph it becomes obvious which packages are the most used, as they
will be present in many of the graphs.

For each Linux distribution the following should be done for each version that
needs to be crawled:

1. download the file `InRelease`
1. extract the field `Components` to find all the components (as described in
   the [Debian repository format][debian_repository]
1. extract the field `Architectures` to find all the architectures (as
   described in the [Debian repository format][debian_repository]
1. for each component from the extracted components download the file
   `source/Sources.xz` or `source/Sources.gz`
1. parse the file `Sources.xz` or `Sources.gz` to extract metadata for the
   source code packages, including a mapping from source code to binary
   packages.
1. for each architecture from the extracted architectures (or a subset) download
   the file `binary-$architecture/Packages.xz` where `$architecture` should be
   replaced with the actual architecture (for example `binary-amd64`).
1. for each package extract the `Depends` and `Pre-Depends` fields (documented
   in the [Debian package relationship documentation][debian_dependencies]).
1. create a graph with all the dependencies between the packages, and keep
   some score to find the most used packages.

Some care should be taken with regards to so called "virtual packages".

## Using declared priorities

Both the `Sources.xz` and `Packages.xz` files contain a field called `Priority`
of which the possible values are described in the [section on
priorities][priorities] in the Debian Policy manual.

```
$ xzcat Sources.xz | grep Priority | sort | uniq -c
    121 Priority: extra
     87 Priority: important
   2030 Priority: optional
     50 Priority: required
     90 Priority: standard
```

[debian_repository]:https://wiki.debian.org/DebianRepository/Format
[debian_versions]:https://en.wikipedia.org/wiki/Debian_release_version_history
[ubuntu_versions]:https://en.wikipedia.org/wiki/Ubuntu_version_history
[debian_dependencies]:https://www.debian.org/doc/debian-policy/ch-relationships.html
[priorities]:https://www.debian.org/doc/debian-policy/ch-archive.html#s-priorities

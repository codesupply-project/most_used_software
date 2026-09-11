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
1. create a graph with all the dependencies between the packages for a single
   architecture, and keep some score to find the most used packages.

This is not as trivial as it sounds. As some of the declared (build)
dependencies can be so called "virtual packages" it requires some juggling of
data and a few passes. Each package belongs to a so called "component" (`main`,
`universe`, `restricted`, etc.) and (build) dependencies for one package can
be part of another component.

Not all dependencies are needed on all architectures, so it is best to group
all results for all components per architecture. Filtering which dependencies
are needed on which platforms is a bit of a hassle.

Some dependencies are presented as alternatives using a `|` character in either
the `Depends` or `Build-Depends` (or related) fields. Sometimes there are
dependencies listed that are not present in the total set of packages. This
isn't a problem when running the distribution, because only one of the
alternative dependencies needs to be satisfied.

## Using declared priorities

Both the `Sources.xz` and `Packages.xz` files contain a field called `Priority`
of which the possible values are described in the [section on
priorities][priorities] in the Debian Policy manual.

These priorities have been set by the developers. An easy list of most used
packages would be to simply get all the packages with priorities `required`,
`important` and `standard`. However, these tend to be at most a few hundred
packages and the packages that are labeled `optional`, `extra` or `source`
should still be processed.

An example from Ubuntu 26.04 (`main` component):
```
$ xzcat Sources.xz | grep ^Priority | sort | uniq -c
    106 Priority: extra
     95 Priority: important
   2068 Priority: optional
     50 Priority: required
     87 Priority: standard
```

and from Debian 13.5 (`main` component, x86-64):
```
$ xzcat Packages.xz | grep ^Priority | sort | uniq -c
    196 Priority: extra
     31 Priority: important
  68457 Priority: optional
     33 Priority: required
     38 Priority: standard
```

and from Debian 13.5 (`main` component):

```
$ xzcat Sources.xz | grep ^Priority | sort | uniq -c
   9091 Priority: extra
  15924 Priority: optional
  12617 Priority: source
```

## Using self reported use of packages

Debian has a mechanism called [Debian Popularity Contest][popcon] (or "popcon")
where users can self report which packages are installed, used regularly, and
updated. This gives potentially a little bit more information about which
packages are important to users, although it doesn't change which packages
are installed or distributed.

The popcon data is generated on a rolling basis and seems to be covering about
20 days to a month worth of data according to the [popcon FAQ][popcon_faq].

The popcon data aggregates data from all versions of Debian (and some
derivatives although that amount is negligible), so it doesn't map cleanly to
a single version of Debian (or derivative). Debian popcon also does not contain
the information from the metadata, so it still would need to be combined with
the metadata.

### Using the popcon data

The latest version of the exported data **from all packages** can be accessed though the following URL:

https://popcon.debian.org/by_inst

To extract data **from a single package**, use the following formatted URL:

```
https://qa.debian.org/cgi-bin/popcon-data?packages=<package_name>&from_date=<YYYY-MM-DD>
```

Where: 
* `<package_name>` is the name of the package.
* `<YYYY-MM-DD>` is the from date in Year-Month-Day format.

For example, to extract the data from the `lvm2` package (all history), the formatted URL looks like this:

```
https://qa.debian.org/cgi-bin/popcon-data?packages=lvm2;from_date=&to_date=
```

"From" and "To" dates can be also added using the `YYYY-MM-DD` format:

```
https://qa.debian.org/cgi-bin/popcon-data?packages=lvm2;from_date=2004-01-24;to_date=2026-09-01
```

#### Data format

The exported data is a TSV file, listing the popularity information per package (one row per package). This is an extract of an actual exported data file:

| **rank** | **name** | **inst** | **vote** | **old** | **recent** | **no-files** | **(maintainer)**            |
|----------|----------|----------|----------|---------|------------|--------------|-----------------------------|
| 1        | debconf  | 283740   | 267290   | 1287    | 15137      | 26           | (Debconf Developers)        |
| 2        | dpkg     | 283739   | 257047   | 9322    | 17332      | 38           | (Dpkg Developers)           |
| 3        | apt      | 283738   | 253149   | 13326   | 17217      | 46           | (Apt Development Team)      |
| 4        | adduser  | 283737   | 198148   | 65676   | 19874      | 39           | (Debian Adduser Developers) |

Where:

* `<name>` is the package name
* `<inst>` is the number of people who installed this package, which is the sum of:
  * `<vote>` is the number of people who use this package regularly;
  * `<old>` is the number of people who installed, but don't use this package regularly;
  * `recent>` is the number of people who upgraded this package recently;
  * `<no-files>` is the number of people whose entry didn't contain enough information (`atime` and `ctime` [1] were 0).

[1] Aclaratory note about the meaning of `atime` and `ctime` parameters, from [Debian Manpage](debian_manpage):

> The popularity-contest command gathers information about Debian packages installed on the system, and prints the name of the most recently used executable program in that package as well as its last-accessed time (atime) and last-attribute-changed time (ctime) to stdout.
>
> When aggregated with the output of popularity-contest from many other systems, this information is valuable because it can be used to determine which Debian packages are commonly installed, used, or installed and never used. This helps Debian maintainers make decisions such as which packages should be installed by default on new systems.


[debian_repository]:https://wiki.debian.org/DebianRepository/Format
[debian_versions]:https://en.wikipedia.org/wiki/Debian_release_version_history
[ubuntu_versions]:https://en.wikipedia.org/wiki/Ubuntu_version_history
[debian_dependencies]:https://www.debian.org/doc/debian-policy/ch-relationships.html
[priorities]:https://www.debian.org/doc/debian-policy/ch-archive.html#s-priorities
[popcon]:https://popcon.debian.org/
[popcon_faq]:https://popcon.debian.org/FAQ
[debiab_manpage]:https://manpages.debian.org/testing/popularity-contest/popularity-contest.8.en.html

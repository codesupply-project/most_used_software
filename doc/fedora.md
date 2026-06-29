# Finding the most used open source software in Fedora

Metadata about packages in Fedora are stored in separate files inside the
Fedora download directory. The main entry point into the metadata is a file
called `repomd.xml` which can be found inside a directory called `repodata`.
Depending on the version of Fedora, or the so called "spin" (a subset of
packages inside Fedora) there could be different locations.

In recent versions of Fedora source code packages can only be found in the
directories `Everything` and `Server`, for example:

* <https://archives.fedoraproject.org/pub/archive/fedora/linux/releases/42/Everything/source/tree/repodata/>
* <https://archives.fedoraproject.org/pub/archive/fedora/linux/releases/42/Server/source/tree/repodata/>

The items in the `repomd.xml` file point to the actual metadata files, which
are offered in two formats: sqlite, and compressed XML (Zstandard and zchunk
compression in recent version, gzip and XZ in older versions).

In `repomd.xml` there are pointers to three metadata sources for directories
with sources and binaries:

1. `primary`
1. `filelists`
1. `other`

The `primary` metadata file contains package information (license,
dependencies needed and provided, and so on). The `filelists` metadata file
contains the files in either the source code archive (in case of a source RPM)
or the files in the binary (in case of a regular RPM). `other` contains change
logs. This information could potentially be interesting (for example for
finding CVE references), but not for finding the most used open source
packages.

The binary distributions contain an extra compressed XML file referred to as
the "comps" file which contains extra information, such as categories. This
file has a slightly different naming convention, containing the name of the
Fedora "flavour" and the used compression. For example, the name of the comps
file for some instances of the `Server` edition ends in
`comps-Server.x86_64.xml.zst` (other compressions are also in use).

## Finding the most used software by creating a dependency graph

For each package in the metadata files a dependency graph can be created. By
walking this graph it becomes obvious which packages are the most used, as they
will be present in many of the graphs.

For each Fedora distribution the following should be done for each version (binary
and source) that needs to be crawled:

1. download the file `repomd.xml`
1. extract the download location for the `primary` file
1. parse the `primary` file, find the dependencies (build dependencies for
   source code, regular dependencies for binaries) and resolve to (source code)
   package names
1. create a dependency graph to find the most used open source package.

There is a lot of data in the `primary` file. For determining the most used
software only a few fields are needed:

1. `name` - name of the package. Some deduplication might be needed, for example
   for `x86_64` because the list might also contain the `i686` packages and
   this difference is not relevant.
1. `url` - for reporting. Note: not every package has this field.
1. `format/rpm:sourcerpm` - the associated source RPM, useful for deduplication,
   as the result of finding the most used software is a list of source code
   packages (not used in the `source` "architecture").
1. `format/rpm:provides` and `format/rpm:requires` for dependency analysis.

The `url` field is unfortunately not very well suited for deduplication. In
Fedora 44 the top 10 of most used URLs for the `x86_64` architecture
(`Everything` edition) is as follows:

| Count | URL |
|------|------|
| 4745 | http://tug.org/texlive/ |
| 1469 | https://haskell.org/ghc/ |
| 320 | http://llvm.org |
| 317 | https://notofonts.github.io/ |
| 303 | http://www.qt.io |
| 238 | http://www.gnu.org/software/glibc/ |
| 229 | https://github.com/gridcf/gct/ |
| 222 | https://crates.io/crates/nix |
| 197 | http://gcc.gnu.org |
| 192 | http://www.libreoffice.org/ |

When processing the `source` "architecture" (for build dependencies) not all
dependencies can be fully resolved.

For example, some packages have the following `requires`:

```
    <rpm:requires>
      <rpm:entry name="/usr/bin/appstream-util"/>
...
    </rpm:requires>
```

but this particular file cannot be found as a `provides`. This makes sense, as
it is a binary dependency and not a source package. This means that the
`source` architecture cannot be fully processed in isolation, but always needs
the information from another architecture (for example `x86_64`) to be able to
determine and resolve the build dependencies.

For the other architectures it *should* be possible to process all packages in
full isolation (where the collection of packages covers all dependencies), but
this is not always the case. As an example, in Fedora 44 the package `krecipes`
has a `requires` that says:

```
...
<rpm:entry name="libQtWebKit.so.4()(64bit)"/>
...
```

but this particular file cannot be found in any of the packages (even when
looking at the "filelists" file). It seems that [this was a
bug][fails_to_install_f44] because a package containing the library was reitred
and dependencies were not properly checked. The bug was [subsequently
fixed][qt4_readded]. In this case to get a more complete view of the actual
dependencies the update files should also be processed.

## Using groups defined in the comps file

Packages are grouped together and can be installed (or managed) together. There
are many groups defined in the comps file, for example, in Fedora 44 there are
200 groups:

```
$ zstdcat ca18d598b3f6c1d2f998eb3f5f368ebfc19892e20a294b562073e61c566526b4-comps-Everything.x86_64.xml.zst | grep '<id>'| wc -l
200
```

Each group contains a list of packages or other groups. For example, the group
`base-system` contains other groups such as `system-tools` and `standard`.

Some of the groups are defined as so called [cricital path][critical_path] groups:

```
$ zstdcat ca18d598b3f6c1d2f998eb3f5f368ebfc19892e20a294b562073e61c566526b4-comps-Everything.x86_64.xml.zst | grep '<id>' | grep critical-path
    <id>critical-path-anaconda</id>
    <id>critical-path-apps</id>
    <id>critical-path-base</id>
    <id>critical-path-build</id>
    <id>critical-path-compose</id>
    <id>critical-path-deepin-desktop</id>
    <id>critical-path-gnome</id>
    <id>critical-path-kde</id>
    <id>critical-path-lxde</id>
    <id>critical-path-lxqt</id>
    <id>critical-path-server</id>
    <id>critical-path-standard</id>
    <id>critical-path-xfce</id>
```

These critical path groups are packages that are seen as absolutely essential,
depending on the context. For example, the group `critical-path-kde` contains
all the packages that are critical for the KDE environment (edited for
clarity):

```
  <group>
    <id>critical-path-kde</id>
    <name>Critical Path (KDE)</name>
...
    <description>A set of packages that provide the Critical Path functionality for the KDE desktop</description>
...
    <default>false</default>
    <uservisible>false</uservisible>
    <packagelist>
      <packagereq type="mandatory">NetworkManager-ppp</packagereq>
      <packagereq type="mandatory">bluedevil</packagereq>
      <packagereq type="mandatory">kactivitymanagerd</packagereq>
      <packagereq type="mandatory">kdecoration</packagereq>
      <packagereq type="mandatory">kinfocenter</packagereq>
      <packagereq type="mandatory">kscreen</packagereq>
      <packagereq type="mandatory">kscreenlocker</packagereq>
      <packagereq type="mandatory">kwayland-integration</packagereq>
      <packagereq type="mandatory">kwin</packagereq>
      <packagereq type="mandatory">layer-shell-qt</packagereq>
      <packagereq type="mandatory">libheif</packagereq>
      <packagereq type="mandatory">plasma-breeze</packagereq>
      <packagereq type="mandatory">plasma-desktop</packagereq>
      <packagereq type="mandatory">plasma-discover</packagereq>
      <packagereq type="mandatory">plasma-integration</packagereq>
      <packagereq type="mandatory">plasma-nm</packagereq>
      <packagereq type="mandatory">plasma-systemsettings</packagereq>
      <packagereq type="mandatory">plasma-thunderbolt</packagereq>
      <packagereq type="mandatory">plasma-workspace</packagereq>
      <packagereq type="mandatory">polkit-kde</packagereq>
      <packagereq type="mandatory">qt6-qtwayland</packagereq>
      <packagereq type="mandatory">sddm</packagereq>
    </packagelist>
  </group>
```

These packages are likely a good candidate for "most used packages". It should
be noted that not every version of Fedora might have these groups defined.

Another metric would be to look at the `packagereq` element which the Fedora
developers use to flag packages that they think are important in for groups of
packages.

```
$ zstdcat ca18d598b3f6c1d2f998eb3f5f368ebfc19892e20a294b562073e61c566526b4-comps-Everything.x86_64.xml.zst | grep packagereq | cut -f 1 -d '>' | sort | uniq -c | sort -n
      1       <packagereq requires="darktable" type="conditional"
      1       <packagereq requires="gnome-control-center" type="conditional"
      1       <packagereq requires="gstreamer" type="conditional"
      1       <packagereq requires="gtk4" type="conditional"
      1       <packagereq requires="mingw32-nsis" type="conditional"
      1       <packagereq requires="plasma-desktop" type="conditional"
      1       <packagereq requires="qt" type="conditional"
      1       <packagereq requires="scribus" type="conditional"
      1       <packagereq requires="xfce4-panel" type="conditional"
      2       <packagereq requires="blender" type="conditional"
      2       <packagereq requires="gimp" type="conditional"
      2       <packagereq requires="gtk2" type="conditional"
      2       <packagereq requires="gtk3" type="conditional"
      2       <packagereq requires="inkscape" type="conditional"
      4       <packagereq requires="xorg-x11-server-Xorg" type="conditional"
   1121       <packagereq type="mandatory"
   1488       <packagereq type="default"
   1723       <packagereq type="optional"
```

The packages labeled `mandatory` are likely good candidates to be considered
"most used".

[critical_path]:https://fedoraproject.org/wiki/Critical_path_package
[fails_to_install_f44]:https://bugzilla.redhat.com/show_bug.cgi?id=2398098
[qt4_readded]:https://bodhi.fedoraproject.org/updates/FEDORA-2025-08d39ff8ce

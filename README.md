# Finding the most used open source software

This repository contains programs to find the most used open source software
in various ecosystems.

## Motivation

Knowledge bases for proprietary scanners are taking a completionist approach,
indexing all source code available on the Internet. This completionist "boiling
the ocean" approach is causing knowledge bases to be very big and preventing
tools from getting best results.

In reality, only a small portion of open source code is in wide use, as
products are built on well known components with little to no changes to the
code. Embedded Linux products for example tend to be built using vendor
supplied software development kits (SDKs) which use well known open source code
or are built using popular frameworks such as Yocto Project, which also include
well known open source code. There are of course domain specific or vendor
specific additions but these are either also well known open source software
packages, or niche open source software packages, or proprietary software
packages.

By focusing on the most open source software first (and filling gaps later)
and avoiding filler (such as forks of existing projects, barely used projects,
abandonware, etc.) knowledge bases can be kept much smaller, meaning more
accurate results (no useless results from unused Git repositories) faster.

Although there is the risk that some code will be missed this is easy to
remedy by identifying and adding the missing code. This isn't any different
from the proprietary tools.

## Important ecosystems

### (embedded) Linux, including Docker

* Alpine Linux
* [Debian Linux and derivatives (Ubuntu)](doc/debian.md)
* Fedora Linux
* OpenWrt
* OpenEmbedded & Yocto Project

### Source code repositories

* GitHub
* GitLab

### Language specific

* Maven (Java)
* Nuget (.NET)
* PyPI (Python)

## Methodology

The methodology used differs per ecosystem.

* [Debian Linux and derivatives (Ubuntu)](doc/debian.md)

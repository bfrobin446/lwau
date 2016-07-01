#! /usr/bin/env python3

import codecs
import functools
import json
import os
import sys
import traceback

from urllib.request import urlopen


# Whether we're checking for an update only or attempting to install, we need
#  to store the parsed version of each local .version file and its remote
#  counterpart.
class Mod:
    def __init__(self, local_version_path):
        self.local_version_path = local_version_path
        try:
            self.local_version_data = json.load(open(self.local_version_path))
            self.installed_version = Version(
                    **self.local_version_data["VERSION"])

            self.master_version_url = self.local_version_data["URL"]
            self.master_version_data = json.load(
                    codecs.getreader('utf-8')(urlopen(self.master_version_url)))
            self.available_version = Version(
                    **self.master_version_data["VERSION"])
        except Exception as e:
            self.exception = traceback.TracebackException.from_exception(e)
        else:
            self.exception = None

    def check_update(self):
        if self.exception:
            print("{}: Error".format(self.local_version_path))
            return False
        else:
            print("{:32} Installed: {!s:12} Available: {!s:12}".format(
                self.local_version_data["NAME"] + ':',
                self.installed_version,
                self.available_version
                ))
            return self.available_version > self.installed_version


# A version is a tuple of 1 to 4 non-negative integers, referred to as
#  "major", "minor", "patch", and "build".
# If fewer than four are given in the file, the remaining variables are set
#  to None.
@functools.total_ordering
class Version:
    # Our __init__ method accepts the keywords in all caps, as they appear in
    #  the .version file.
    def __init__(self,
            major=None, minor=None, patch=None, build=None, **kwargs):
        self.major = major or kwargs.get("MAJOR")
        self.minor = minor or kwargs.get("MINOR")
        self.patch = patch or kwargs.get("PATCH")
        self.build = build or kwargs.get("BUILD")

    # Equality is member-by-member. 
    def __eq__(self, other):
        return (     self.major == other.major
                 and self.minor == other.minor
                 and self.patch == other.patch
                 and self.build == other.build )

    # Comparison is lexicographic. A position that is not used (None)
    #  compares less than one that is set to zero.
    def __lt__(self, other):
        def cmp_numbers(left, right):
            if left is None:
                left = -1
            if right is None:
                right = -1

            if left < right:
                return -1
            elif left == right:
                return 0
            else:
                return 1

        return (    cmp_numbers(self.major, other.major)
                 or cmp_numbers(self.minor, other.minor)
                 or cmp_numbers(self.patch, other.patch)
                 or cmp_numbers(self.build, other.build) ) == -1

    def __str__(self):
        return '.'.join(
                str(part)
                for part in (self.major, self.minor, self.patch, self.build)
                if part is not None)

    def __repr__(self):
        return "Version({major}, {minor}, {patch}, {build})".format(
                **self.__dict__)


def main():
    import argparse
    arg_parser = argparse.ArgumentParser(
        "Check AVC-enabled mods for updates and optionally attempt to install.",
        epilog='\n'.join((
            "Exit status:",
            "0: All checked mods are up-to-date.",
            "1: One or more updates available but not installed.",
            "2: An error occurred."))
        )
    arg_parser.add_argument("verb", choices=("check", "update"),
            help="'check': List mods with updates available, but do not attempt to install. 'update': Attempt to install any available updates.")
    arg_parser.add_argument("target",
            help="A .version file, or 'all' to process all .version files in GameData.")

    args = arg_parser.parse_args()

    if args.verb == "check":
        if args.target == "all":
            need_updating = [m.check_update() for m in
                    find_installed_mods()]
            if any(need_updating):
                sys.exit(1)
            else:
                sys.exit(0)
        else:
            m = Mod(args.target)
            if m.exception:
                for s in m.exception.format():
                    print(s, end='')
                sys.exit(2)
            elif m.check_update():
                sys.exit(1)
            else:
                sys.exit(0)


def find_installed_mods():
    for dir in os.walk("GameData"):
        for fname in dir[2]:
            if fname.endswith(".version"):
                yield Mod(os.path.join(dir[0],fname))


if __name__ == '__main__':
    main()

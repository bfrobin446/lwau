#! /usr/bin/env python3


#--------------------------------------------------------------------------


import codecs
import functools
import json
import os
import pathlib
import sys
import traceback
import webbrowser

from urllib.parse   import urlsplit, urlunsplit
from urllib.request import urlopen


#--------------------------------------------------------------------------


# Whether we're checking for an update only or attempting to install, we need
#  to store the parsed version of each local .version file and its remote
#  counterpart.
class Mod:
    def __init__(self, local_version_path):
        self.local_version_path = local_version_path
        try:
            self.local_version_data = json.load(open(self.local_version_path,
                encoding='utf-8-sig'))
            self.installed_version = Version(
                    **self.local_version_data["VERSION"])

            self.master_version_url = self.local_version_data["URL"]
            self.master_version_data = json_load_from_url(
                    self.master_version_url)
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


    def update(self):
        self.find_download()

        if self.archive_url is None:
            return False

        return True


    def find_download(self):
        self.archive_url = None

        if "GITHUB" in self.master_version_data:
            self.archive_url = self.find_github_download()
            if self.archive_url is not None:
                return

        if "DOWNLOAD" in self.master_version_data:
            download_url = self.master_version_data["DOWNLOAD"]
            if ("spacedock" in download_url):
                self.archive_url = self.find_spacedock_download()
                if self.archive_url is not None:
                    return

            if ("github" in download_url and "GITHUB" not in
                    self.master_version_data):
                download_path = pathlib.PurePosixPath(
                        urlsplit(download_url)[2])
                gh_user = download_path.parts[1]
                gh_path = download_path.parts[2]
                self.archive_url = self.find_github_download(gh_user, gh_path)
                if self.archive_url is not None:
                    return

            print("Could not find an archive for {}".format(
                download_url))
            webbrowser.open(download_url, new=2)

        else:
            print("{} did not specify a download page.".format(
                self.local_version_data["NAME"]))


    def find_github_download(self, username=None, repo=None):
        if username is None:
            username = self.master_version_data["GITHUB"]["USERNAME"]
        if repo is None:
            repo = self.master_version_data["GITHUB"]["REPOSITORY"]
        github_releases_url = (
            "https://api.github.com/repos/{}/{}/releases".format(
                username, repo))
        github_releases_data = json_load_from_url(github_releases_url)

        try:
            wanted_release = next(r for r in github_releases_data
                    if str(self.available_version) in r["tag_name"])
        except StopIteration:
            print('GitHub: No tag matching "{}"'.format(
                    self.available_version))
            return None

        try:
            wanted_asset = next(a for a in wanted_release["assets"]
                    if a["name"].endswith(".zip"))
        except StopIteration:
            print('GitHub: No .zip archive for release "{}"'.format(
                wanted_release["tag_name"]))
            return None

        return wanted_asset["browser_download_url"]


    def find_spacedock_download(self):
        download_page = urlsplit(self.master_version_data["DOWNLOAD"])
        mod_id = pathlib.PurePosixPath(download_page.path).parts[2]
        mod_data = json_load_from_url(
                "http://spacedock.info/api/mod/{}".format(mod_id))

        try:
            wanted_version = next(v for v in mod_data["versions"]
                    if self.available_version.fuzzy_equals(
                        Version(str=v["friendly_version"])))
        except StopIteration:
            print('No Spacedock download for version "{}"'.format(
                    self.available_version))
            return None

        return urlunsplit(('http','spacedock.info',
                    wanted_version["download_path"], '', ''))


#--------------------------------------------------------------------------


# A version is a tuple of 1 to 4 non-negative integers, referred to as
#  "major", "minor", "patch", and "build".
# If fewer than four are given in the file, the remaining variables are set
#  to None.
@functools.total_ordering
class Version:
    # Our __init__ method accepts the keywords in all caps, as they appear in
    #  the .version file.
    def __init__(self,
            major=None, minor=None, patch=None, build=None,
            str=None, **kwargs):
        if str is not None:
            from itertools import zip_longest
            parts = map(int, str.split('.'))
            for member, val in zip_longest(("major", "minor", "patch",
                "build"), parts):
                setattr(self, member, val)
        else:
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

    def fuzzy_equals(self, other):
        def numbers_fuzzy_equal(x, y):
            return x == y or (x == 0 and y is None) or (x is None and y == 0)

        return (     numbers_fuzzy_equal(self.major, other.major)
                 and numbers_fuzzy_equal(self.minor, other.minor)
                 and numbers_fuzzy_equal(self.patch, other.patch)
                 and numbers_fuzzy_equal(self.build, other.build) )

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


#--------------------------------------------------------------------------


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
            need_updating = sum(m.check_update() for m in
                    find_installed_mods())
            print("{} packages have updates available.".format(need_updating))
            if need_updating:
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

    elif args.verb == "update":
        if args.target == "all":
            updates_failed = 0
            for m in find_installed_mods():
                if m.check_update():
                    if not m.update():
                        updates_failed += 1
            if updates_failed:
                print("{} mods need manual intervention.".format(
                    updates_failed))
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
                if m.update():
                    sys.exit(0)
                else:
                    sys.exit(1)
            else:
                sys.exit(0)


#--------------------------------------------------------------------------


def find_installed_mods():
    for dir in os.walk("GameData"):
        for fname in dir[2]:
            if fname.endswith(".version"):
                yield Mod(os.path.join(dir[0],fname))


def json_load_from_url(u):
    return json.load(codecs.getreader('utf-8-sig')(urlopen(u)))


#--------------------------------------------------------------------------


if __name__ == '__main__':
    main()

#! /usr/bin/env python3


#--------------------------------------------------------------------------


import codecs
import collections.abc
import functools
import json
import numbers
import os
import pathlib
import re
import shutil
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
                    self.local_version_data["VERSION"])

            self.master_version_url = self.local_version_data["URL"]
            self.master_version_data = json_load_from_url(
                    self.master_version_url)
            self.available_version = Version(
                    self.master_version_data["VERSION"])
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

        if self.local_version_path not in settings["recipes"]:
            if "download_dir" not in settings:
                print("No download location specified.")
                return False

            self.download_archive_to(settings["download_dir"])
            print("Downloaded {}".format(self.local_archive))
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


    def download_archive_to(self, dest_dir):
        response = urlopen(self.archive_url)

        disposition = response.getheader("Content-disposition")
        if disposition is not None:
            filename = re.search(r'filename=(\S+)', disposition).group(1)
        if disposition is None or filename is None:
            filename = pathlib.PurePosixPath(
                    urlsplit(response.geturl()).path).name

        self.local_archive = pathlib.Path(dest_dir) / filename
        shutil.copyfileobj(response, self.local_archive.open('xb'))


#--------------------------------------------------------------------------


# A version is a tuple of 1 to 4 non-negative integers, referred to as
#  "major", "minor", "patch", and "build".
# If fewer than four are given in the file, the remaining variables are set
#  to None.
@functools.total_ordering
class Version:
    # As alternatives to constructing a Version from four integers, we can
    # accept a dictionary of the type that would be found in a .version
    # file, or a dot-separated string resembling what we return from our
    # __str__ method.
    def __init__(self, major_or_object,
            minor=None, patch=None, build=None):
        if isinstance(major_or_object, collections.abc.Mapping):
            self.major = major_or_object.get("MAJOR")
            self.minor = major_or_object.get("MINOR")
            self.patch = major_or_object.get("PATCH")
            self.build = major_or_object.get("BUILD")

        elif isinstance(major_or_object, str):
            from itertools import zip_longest
            parts = map(int, major_or_object.split('.'))
            for member, val in zip_longest(("major", "minor", "patch",
                "build"), parts):
                setattr(self, member, val)
        elif isinstance(major_or_object, numbers.Integral):
            (self.major, self.minor, self.patch, self.build) = (major,
                    minor, patch, build)
        else:
            raise TypeError("Can't create a Version from {}".format(
                type(major_or_object)))

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
    import textwrap

    arg_parser = argparse.ArgumentParser(
        description="Check AVC-enabled mods for updates and optionally attempt to install.",
        epilog='\n'.join((
            "Exit status:",
            "0: All checked mods are up-to-date.",
            "1: One or more updates available but not installed.",
            "2: An error occurred.")),
        formatter_class = argparse.RawTextHelpFormatter
        )
    arg_parser.add_argument("verb", choices=("check", "update", "download-to"),
            help=textwrap.dedent('''\
                check:  List mods with updates available, but do not
                         attempt to install.
                update: Attempt to download and install any available
                         updates.
                download-to: Set default download location. The
                              selected location is saved in
                              PluginData/lwau.json.
                ''',
                ))
    arg_parser.add_argument("target",
            help=textwrap.dedent('''\
                If command is `check` or `update`, `target` is a
                 .version file, or 'all' to process all .version files
                 in GameData.
                If command is `download-to`, `target` is the path to
                 download archives that require manual installation.'''))

    arg_parser.add_argument("-d", "--download-to", dest="download_dir",
            help=textwrap.dedent('''\
                    Location to download archives. Overrides the default
                     path if one is set.'''))

    args = arg_parser.parse_args()

    load_settings()
    if args.download_dir is not None:
        settings["download_dir"] = args.download_dir

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

    elif args.verb == "download-to":
        settings["download_dir"] = args.target
        json.dump(settings, open("PluginData/lwau.json", 'w'))


#--------------------------------------------------------------------------


def load_settings():
    global settings
    try:
        settings = json.load(open("PluginData/lwau.json"))
    except:
        settings = {'recipes':{}}


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

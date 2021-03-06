from __future__ import print_function
import datetime
import logging
import fnmatch
import os
import re
import itertools
import glob
from .filelist_reader import iter_filelist_reader

indent = "    "


def get_now():
    """
    return current time without microsecond
    """
    return datetime.datetime.now().replace(microsecond=0)


def gen_hier(parent, child):
    """
    generate hierarchy scope
    """
    # return "{parent}/{child}".format(parent=parent, child=child)
    return os.path.join(parent, child)


def get_hier_basename(hier):
    return os.path.basename(hier)


# def create_logger(name):
#     return logging.getLogger(name)


def filelist_reader(filelist):
    return list(iter_filelist_reader(filelist))


def _iglobstar(dirname, basename):
    try:
        if os.path.isdir(dirname):
            yield dirname
        for root, dirs, files in os.walk(dirname):
            dirs[:] = [d for d in dirs if d[0] != "."]
            for f in itertools.chain(dirs, files):
                if f[0] != ".":
                    yield os.path.join(root, f)
    except os.error:
        pass


def _glob1(dirname, basename):
    pattern = "{(\S+)}"
    pattern = re.compile(pattern)
    basenames = pattern.split(basename)
    acc = [""]
    for base in basenames:
        _acc = []
        for ext in base.split(","):
            _acc.extend([f + ext for f in acc])
        acc = _acc

    for basename in acc:
        for name in glob.glob1(dirname, basename):
            yield name


def iglob(pathname, yield_even_not_exists=False):

    pathname = os.path.expandvars(pathname)
    dirname, basename = os.path.split(pathname)

    assert dirname != pathname, pathname

    if not glob.has_magic(pathname):
        if yield_even_not_exists:
            yield pathname
        elif basename:
            if os.path.lexists(pathname):
                yield pathname
        else:
            if os.path.isdir(dirname):
                yield dirname
        return

    if dirname == "":
        dirname = os.curdir

    if glob.has_magic(dirname):
        dirs = set(iglob(dirname))
    else:
        dirs = [dirname]

    if basename == "**":
        glob_in_dir = _iglobstar
    elif glob.has_magic(basename):
        glob_in_dir = _glob1
    else:
        glob_in_dir = glob.glob0

    for dirname in dirs:
        for name in glob_in_dir(dirname, basename):
            if glob_in_dir is _iglobstar:
                f = name
            else:
                f = os.path.join(dirname, name)
            yield f

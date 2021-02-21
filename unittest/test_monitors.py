import unittest
import shutil
import os
import subprocess
import shlex
import json
from time import sleep

# local packages
import monitors
import generic
import random

# import collections
from collections import defaultdict


def touch(filename):
    try:
        open(filename, "w").close()
        return True
    except Exception as e:
        return False


def create_tree(tree, hier=""):
    for item in tree:
        name = os.path.join(hier, item.get("name"))
        if "children" in item:
            try:
                os.mkdir(name)
            except OSError:
                pass
            else:
                create_tree(item.get("children"), name)
        else:
            touch(name)


class TestFileMonitor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pardir = os.path.abspath(os.path.join(__file__, os.pardir))
        filename = os.path.join(pardir, "tree.json")
        with open(filename, "r") as fo:
            tree = json.load(fo)
        cls.tree = tree
        cls.cwd = os.getcwd()
        os.chdir(pardir)
        create_tree(tree)

    @classmethod
    def tearDownClass(cls):
        for item in cls.tree:
            name = item.get("name")
            shutil.rmtree(name, ignore_errors=True)
        os.chdir(cls.cwd)

    def test_iglob(self):
        tests = [
            "root/**/*.sv",
            "root/**/f1/",
            "root/**/f1",
            "root/f3/**/*.v",
            "root/f3/**/**.v",
            "root/f1/**",
            "root/*",
            "notGonnaMatch/*",
            "notGonnaMatch/*/",
            "notGonnaMatch/**",
            "notGonnaMatch/**/",
            "root/*.{sv,v}",
            "root/*/*",
            "root/*/*/*",
            "root/*/*/*.notGonnaMatch",
            "root/**/*.notGonnaMatch",
            "root/**/leaf*",
            "root/**",
            "root/**////*.{sv,h}",
            "root/**/",
            "root/**.sv",
            "root/**/*",
            "root/*/**/*",
            "root/*/**/*.py",
            "root/**/**/*.py",
            "root/*/**/*.sv",
            "root/*/**/*.{h,sv}",
            "root/*//**//*.{h,sv}",
            "root/**/**/*.sv",
            "root/**/*/*.{sv,v}",
            "root/**/*/*.py",
            "root",
            "root/",
        ]

        for test in tests:
            cmd = "bash -c 'shopt -s globstar; ls -d %s'" % test
            worker = subprocess.Popen(
                shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = worker.communicate()
            golden = stdout.strip().splitlines()
            answer = list(generic.iglob(test))
            self.assertEqual(len(golden), len(answer))

    def test_FileMonitor_with_modifying_files(self):
        # crontab value doesn't matter in this test
        file_monitor = monitors.FileMonitor("@hourly", "root/**")
        sleep(0.1)  # add delay to avoid race condition
        targets = list(file_monitor.targets)
        for _ in range(10):
            golden = []
            for _ in range(20):
                pathname = random.choice(targets)
                if not os.path.isdir(pathname):
                    touch(pathname)
                    if pathname not in golden:
                        golden.append(pathname)
            if golden:
                sleep(0.1)  # add delay to avoid race condition
                events = file_monitor.diff(verbose=False)
                self.assertEqual(len(events), 1)
                for event, items in events:
                    self.assertEqual(len(items), len(golden))
                    self.assertEqual(event, monitors.MODIFIED)

    def test_FileMonitor_with_monitoring_folders(self):
        # only get folders
        file_monitor = monitors.FileMonitor("@hourly", "root/**/")
        targets = list(file_monitor.targets)
        sleep(0.1)  # add delay to avoid race condition
        golden = None
        for i in range(10):
            before = golden
            golden = defaultdict(list)
            if before:
                for name in before[monitors.ADDED]:
                    if random.choice([True, False]):
                        os.remove(name)
                        golden[monitors.REMOVED].append(name)

            for j in range(20):
                pathname = random.choice(targets)
                if os.path.isdir(pathname):
                    for name in os.listdir(pathname):
                        name = os.path.join(pathname, name)
                        if os.path.isfile(name):
                            if name.endswith(".add_file"):
                                # don't modified add file
                                continue
                            touch(name)
                            golden[monitors.MODIFIED].append(name)
                        else:
                            name = os.path.join(
                                name, "xxxx_{0}_{1}.add_file".format(i, j)
                            )
                            touch(name)
                            golden[monitors.ADDED].append(name)

            if golden:
                sleep(0.1)  # add delay to avoid race condition
                events = file_monitor.diff(verbose=False)
                self.assertEqual(len(events), len(golden))
                for event, items in events:
                    diff = set(golden[event]) - set(items)
                    # print items
                    # print golden[event]
                    # print diff, event
                    self.assertEqual(len(items), len(set(golden[event])))


class TestSvnMonitor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pardir = os.path.abspath(os.path.join(__file__, os.pardir))
        filename = os.path.join(pardir, "tree.json")
        with open(filename, "r") as fo:
            tree = json.load(fo)
        cls.tree = tree
        cls.cwd = os.getcwd()
        os.chdir(pardir)
        create_tree(tree)

    @classmethod
    def tearDownClass(cls):
        for item in cls.tree:
            name = item.get("name")
            shutil.rmtree(name, ignore_errors=True)
        os.chdir(cls.cwd)

    def test_xxx(self):
        print "Ooooops"


if __name__ == "__main__":
    unittest.main()

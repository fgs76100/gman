from __future__ import print_function
from monitors import FileMonitor, SvnMonitor, Scheduler
from event import EventManger
from generic import gen_hier, indent, get_hier_basename

import logging
import time
import os
import yaml
import argparse
import tempfile
import traceback
import copy
import shutil
from string import Template

logger = logging.getLogger(__name__)

TEMPDIR = os.path.join(os.getcwd(), ".gman_tempdir")
tempfile.tempdir = TEMPDIR
LOGFILE = "gman.log"


COMMANDS = ("list-targets", "list-schedule", "run", "clean")


def parse_args():
    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        "command",
        choices=COMMANDS,
    )
    argparser.add_argument(
        "name", nargs="?", help="specify a job name for helper command"
    )

    argparser.add_argument(
        "-c", "--config", required=True, help="a yaml configurtion file"
    )

    return argparser.parse_args()


def env_checker(env):
    for key, value in env.items():
        if not isinstance(value, str):
            raise TypeError("environment variable only can be string type: %s" % key)


def rename_files(command):

    if os.path.exists(TEMPDIR) and command == "run":
        mtime = int(os.stat(TEMPDIR).st_mtime)
        pathname, basename = os.path.split(TEMPDIR)
        dest = basename + "_%s" % mtime
        os.rename(TEMPDIR, os.path.join(pathname, dest))
        print("Previous %s was rename to %s" % (basename, dest))

    if os.path.exists(LOGFILE) and command == "run":
        mtime = int(os.stat(LOGFILE).st_mtime)
        # name, ext = LOGFILE.split(".", 1)
        # dest = "%s.%s" % (name, mtime, ext)
        dest = "%s.%s" % (LOGFILE, mtime)
        os.rename(LOGFILE, dest)
        print("Previous %s was rename to %s" % (LOGFILE, dest))

    if not os.path.exists(TEMPDIR):
        os.mkdir(TEMPDIR)


def constructor(jobs, glob_env, project):
    env_checker(glob_env)

    for name, settings in jobs.items():

        job_config = settings.get("job_config", {}) or {}
        job_env = glob_env.copy()
        job_config_env = job_config.get("env", {}) or {}

        env_checker(job_config_env)

        job_env.update(job_config_env)
        job_config["env"] = job_env

        monitor_config = settings.get("monitor", {}) or {}
        if not monitor_config:
            raise ValueError("monitor field is empty at %s" % name)
        monitor_config["name"] = gen_hier(project, name)
        monitor_type = monitor_config.get("type", "") or ""

        if monitor_type == "svn":
            monitor = SvnMonitor(**monitor_config)
        elif monitor_type == "file":
            monitor = FileMonitor(**monitor_config)
        elif not monitor_type or not monitor_config.get("targets", None):
            monitor = Scheduler(**monitor_config)
        else:
            raise TypeError(
                "This monitor type doesn't support: {0}".format(monitor_type)
            )

        on_events = settings.get("on_events", {}) or {}
        if not len(on_events):
            raise NotImplementedError

        continue_on_error = job_config.pop("continue_on_error", False)

        for event, callbacks in on_events.items():
            if callbacks:
                config = copy.deepcopy(job_config)
                monitor.add_event(event, callbacks, config, continue_on_error)

        for signal in ("on_error", "on_success"):
            callback = settings.get(signal, None)
            if callback:
                config = copy.deepcopy(job_config)
                monitor.add_handler(signal, callback["name"], callback["cmd"], **config)

        yield monitor


def helper(command, monitors, name):
    if command == "run":
        return

    if command == "clean":
        # remove log files and temp dirs
        for path in os.listdir("./"):
            if path.startswith(LOGFILE):
                os.unlink(path)
            elif path.startswith(os.path.basename(TEMPDIR)):
                shutil.rmtree(path, ignore_errors=True)
        raise SystemExit(0)

    for monitor in monitors:
        if name and get_hier_basename(monitor.name) != name:
            continue

        print(monitor.name)
        if command == "list-targets":
            for target in getattr(monitor, "targets", []):
                print(indent, target)
        if command == "list-schedule":
            for _ in range(5):
                print(indent, monitor.schedule_next_run(monitor.next_run))

    raise SystemExit(0)


def setup_root_logger(is_debug):
    logging_format = dict(
        fmt="%(asctime)s [%(levelname)s] %(name)s %(message)s",
        datefmt="%Y/%m/%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(
        logging.DEBUG if is_debug else logging.INFO,
    )

    formatter = logging.Formatter(**logging_format)

    sh = logging.StreamHandler()
    fh = logging.FileHandler(filename=LOGFILE, mode="w")
    sh.setFormatter(formatter)
    fh.setFormatter(formatter)
    root_logger.addHandler(sh)
    root_logger.addHandler(fh)


def event_loop(config=None):
    if config is None:
        args = parse_args()

        with open(args.config, "r") as f:
            working_env = yaml.safe_load(f)

        rename_files(args.command)
    else:
        working_env = config
        rename_files("run")

    if not isinstance(working_env, dict):
        raise TypeError("argument is not a dict type")

    glob_env = os.environ.copy()

    env = working_env.get("env", {}) or {}
    project = working_env.get("project", None)

    if not project:
        raise ValueError("The project value must be specified!")

    if isinstance(env, dict):
        glob_env.update(env)

    setup_root_logger(working_env.get("debug", False))

    monitors = []
    for monitor in constructor(working_env.get("jobs"), glob_env, project):
        monitors.append(monitor)

    if config is None:
        helper(args.command, monitors, args.name)

    print("\nInitializing...")
    for monitor in monitors:
        monitor.initialize()
    print("Running...\nPress Ctrl+c to exit")
    while True:
        try:
            for monitor in monitors:
                try:
                    monitor()
                except Exception:
                    traceback.print_exc()
                time.sleep(1)
        except KeyboardInterrupt:
            print("\ntrying to terminate unfinished tasks before exit...\n")
            logging.shutdown()
            for monitor in monitors:
                try:
                    monitor.kill()
                except Exception:
                    traceback.print_exc()
            print("goodbye...\n")
            raise SystemExit(0)


if __name__ == "__main__":
    event_loop()

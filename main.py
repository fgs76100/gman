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
from string import Template


TEMPDIR = os.path.join(os.getcwd(), ".gman_log")
tempfile.tempdir = TEMPDIR


commands = ("list-targets", "show-schedule", "run")


def parse_args():
    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        "command",
        choices=commands,
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


def check_tempdir():

    if os.path.exists(TEMPDIR):
        mtime = int(os.stat(TEMPDIR).st_mtime)
        pathname, basename = os.path.split(TEMPDIR)
        dest = basename + "_%s" % mtime
        os.rename(TEMPDIR, os.path.join(pathname, dest))
        print("Previous %s was rename to %s" % (basename, dest))

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

        monitor.add_events(on_events, continue_on_error=continue_on_error, **job_config)

        for signal in ("on_error", "on_success"):
            callback = settings.get(signal, None)
            if callback:
                monitor.add_handler(
                    signal, callback["name"], callback["cmd"], **job_config
                )

        yield monitor


def list_targets(jobs, name):
    for monitor in jobs:
        if name and monitor.name != name:
            continue
        print(monitor.name)
        for target in getattr(monitor, "targets", []):
            print(indent, target)


def helper(command, monitors, name):
    if command == "run":
        return

    for monitor in monitors:
        if name and get_hier_basename(monitor.name) != name:
            continue

        print(monitor.name)
        if command == "list-targets":
            for target in getattr(monitor, "targets", []):
                print(indent, target)
        if command == "show-schedule":
            for _ in range(5):
                print(indent, monitor.schedule_next_run(monitor.next_run))
                # print(indent, schedule)

    raise SystemExit(0)


def event_loop(config=None):
    if config is None:
        args = parse_args()

        with open(args.config, "r") as f:
            working_env = yaml.safe_load(f)
    else:
        working_env = config

    if not isinstance(working_env, dict):
        raise TypeError("argument is not a dict type")

    glob_env = os.environ.copy()

    env = working_env.get("env", {}) or {}
    project = working_env.get("project", None)

    if not project:
        raise ValueError("The project value must be specified!")

    if working_env.get("debug", False):
        logging.getLogger("Event").setLevel(logging.DEBUG)
        logging.getLogger("Monitor").setLevel(logging.DEBUG)

    if isinstance(env, dict):
        glob_env.update(env)

    monitors = []

    check_tempdir()

    for monitor in constructor(working_env.get("jobs"), glob_env, project):
        monitors.append(monitor)

    # args.name = gen_hier(project, args.name)

    if config is None:
        helper(args.command, monitors, args.name)

    print("\nInitializing... it could take a while")
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
            for monitor in monitors:
                try:
                    monitor.kill()
                except Exception:
                    traceback.print_exc()
            print("goodbye...\n")
            raise SystemExit(0)


if __name__ == "__main__":
    event_loop()

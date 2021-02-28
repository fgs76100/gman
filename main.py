# from __future__ import print_function
from monitors import FileMonitor, SvnMonitor
from event import EventManger
from generic import gen_hier

import logging
import time
import os
import yaml
import argparse
import tempfile
import traceback
from string import Template


tempdir = os.path.join(os.getcwd(), ".gman_tmp")

if not os.path.exists(tempdir):
    os.mkdir(tempdir)

tempfile.tempdir = tempdir


def parse_args():
    argparser = argparse.ArgumentParser()
    # argparser.add_argument("command", nargs="?")
    argparser.add_argument("command")
    argparser.add_argument("target", nargs="?")

    return argparser.parse_args()


def env_checker(env):
    for key, value in env.items():
        if not isinstance(value, str):
            raise TypeError("environment variable only can be string type: %s" % key)


def constructor(jobs, glob_env, project):
    env_checker(glob_env)

    for name, settings in jobs.items():

        job_config = settings.get("job_config", {}) or {}
        job_env = glob_env.copy()
        job_config_env = job_config.get("env", {}) or {}

        env_checker(job_config_env)

        job_env.update(job_config_env)
        job_config["env"] = job_env

        monitor_config = settings.get("monitor", None)
        monitor_config["name"] = name
        monitor_type = monitor_config.get("type").lower()

        if monitor_type == "svn":
            monitor = SvnMonitor(**monitor_config)
        elif monitor_type == "file":
            monitor = FileMonitor(**monitor_config)
        else:
            raise TypeError(
                "This monitor type doesn't support: {0}".format(monitor_type)
            )

        event_manager = EventManger(gen_hier(project, name))
        on_event = settings.get("on_event", {}) or {}
        if not len(on_event):
            raise NotImplementedError

        continue_on_error = job_config.pop("continue_on_error", False)

        for event, callbacks in on_event.items():
            if callbacks:
                event_manager.add_event(
                    event, callbacks, continue_on_error, **job_config
                )

        on_error = settings.get("on_error", None)
        if on_error:
            event_manager.add_error_handler(
                on_error["name"], on_error["cmd"], **job_config
            )

        on_success = settings.get("on_success", None)
        if on_success:
            event_manager.add_success_handler(
                on_success["name"], on_success["cmd"], **job_config
            )

        yield monitor, event_manager


def list_targets(jobs):
    for monitor in jobs.keys():
        print monitor.name
        for target in monitor.targets:
            print target


def event_loop(working_env=None):
    if not working_env:
        args = parse_args()

        with open(args.target, "r") as f:
            working_env = yaml.safe_load(f)
        # from pprint import pprint

        # pprint(working_env)

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

    jobs = {}
    for monitor, manager in constructor(working_env.get("jobs"), glob_env, project):
        jobs[monitor] = manager

    if not working_env:
        if args.command == "list-targets":
            list_targets(jobs)
            raise SystemExit(0)

    while True:
        try:
            for monitor, manager in jobs.items():
                if manager.is_done and monitor.is_on_duty:
                    monitor.schedule_next_run()
                    for event, items in monitor.iter_diff():
                        manager.on(event)
            time.sleep(1)
        except KeyboardInterrupt:
            print "\ntrying to terminate unfinished tasks before exit...\n"
            for monitor, manager in jobs.items():
                try:
                    monitor.kill()
                    manager.kill()
                except Exception:
                    traceback.print_exc()
            print "goodbye...\n"
            raise SystemExit(0)

        except Exception:
            traceback.print_exc()
            time.sleep(2)


if __name__ == "__main__":
    event_loop()

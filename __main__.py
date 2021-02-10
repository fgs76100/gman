from __future__ import print_function
from monitors import FileMonitor, SvnMonitor
from event import EventManger
from generic import gen_hier

import logging
import time
import os
import yaml
import argparse
import tempfile
from string import Template


# logging.getLogger("Event").setLevel(logging.DEBUG)
logging.getLogger("Monitor").setLevel(logging.DEBUG)

tempdir = os.path.join(os.getcwd(), ".gman_tmp")

if not os.path.exists(tempdir):
    os.mkdir(tempdir)

tempfile.tempdir = tempdir


def parse_args():
    argparser = argparse.ArgumentParser()
    argparser.add_argument("command", nargs="?")
    argparser.add_argument("target", nargs="?")

    return argparser.parse_args()


def constructor(jobs, glob_env, project):

    for name, settings in jobs.items():

        job_config = settings.get("config", {})
        job_env = glob_env.copy()
        job_env.update(job_config.get("env", {}) or {})
        job_config["env"] = job_env

        monitor_config = settings.get("monitor", None)
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
            event_manager.add_event(event, callbacks, continue_on_error, **job_config)

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


if __name__ == "__main__":
    # test = FileMonitor(
    x = parse_args()

    with open(x.target, "r") as f:
        working_env = yaml.safe_load(f)

    glob_env = os.environ.copy()

    env = working_env.get("env", {})
    project = working_env.get("project")

    if isinstance(env, dict):
        glob_env.update(env)

    jobs = {}
    for monitor, manager in constructor(working_env.get("jobs"), glob_env, project):
        jobs[monitor] = manager

    while True:
        try:
            for monitor, manager in jobs.items():
                if manager.is_done and monitor.is_on_duty:
                    for event, items in monitor.iter_diff():
                        manager.on(event)
                    monitor.schedule_next_run()
            time.sleep(1)
        except KeyboardInterrupt:
            for monitor, manager in jobs.items():
                manager.terminate()
            exit(0)

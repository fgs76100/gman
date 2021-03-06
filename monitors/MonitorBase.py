import logging
import os

# import sys
import datetime
import fnmatch
import re
from crontab import CronTab
from generic import get_now, iglob, iter_filelist_reader
from event import EventManger, ANY_EVENT
from fnmatch import fnmatch


# logger = create_logger("Monitor")

MODIFIED = "modified"
REMOVED = "removed"
ADDED = "added"

crontan_pattern = r"every\s+(\d+)?\s+(second|minute|hour)s?"
crontan_pattern = re.compile(crontan_pattern)


def crontab_mapper(crontab):
    match = crontan_pattern.match(crontab)
    if not match:
        return crontab
    else:
        unit = match.group(2)
        value = match.group(1)
        value = "/" + value if value else ""
        if unit == "second":
            return "*%s * * * * * *" % value
        elif unit == "minute":
            return "0 *%s * * * * *" % value
        elif unit == "hour":
            return "0 0 *%s * * * *" % value
        else:
            return crontab


class Scheduler(object):
    # logger = logger

    def __init__(self, schedule, name="", **kwargs):
        self.crontab = CronTab(crontab_mapper(schedule))
        self.next_run = None  # datetime object
        self.logger = logging.getLogger(name)

        self.name = name
        # self.schedule_next_run()
        self.event_manager = EventManger(name)

    def initialize(self):
        self.schedule_next_run()

    def schedule_next_run(self, date=None):
        if not date:
            date = get_now()
        self.next_run = date + datetime.timedelta(
            seconds=int(self.crontab.next(date, default_utc=True))
        )
        return self.next_run
        # self.logger.debug("%s is scheduled to run at %s", self.name, self.next_run)

    @property
    def is_on_duty(self):
        return get_now() >= self.next_run

    def add_events(self, events, *args, **kwargs):
        for event, callbacks in events.items():
            if callbacks:
                self.event_manager.add_event(event, callbacks, *args, **kwargs)

    def add_handler(self, signal, name, cmd, **kwargs):
        if signal == "on_error":
            self.event_manager.add_error_handler(name, cmd, **kwargs)
        elif signal == "on_success":
            self.event_manager.add_success_handler(name, cmd, **kwargs)

    def __call__(self, event=ANY_EVENT):
        if self.event_manager.is_done and self.is_on_duty:
            self.schedule_next_run()
            self.event_manager.on(event)

    def kill(self):
        self.event_manager.kill()


class MonitorBase(Scheduler):
    # logger = logger

    def __init__(self, schedule, targets, name="", **kwargs):

        super(MonitorBase, self).__init__(schedule, name, **kwargs)

        if isinstance(targets, str):
            targets = [targets]

        if not isinstance(targets, list):
            raise TypeError("targets should be a list or a string")

        self.targets = []
        self.ignores = kwargs.get("ignores", None) or []

        for target in targets:
            if target.startswith("-f"):
                target = re.split(r"\s+", target.strip())[-1]
                filelist = iter_filelist_reader(target)
            else:
                filelist = [target]
            for path in filelist:
                self.targets.extend(filter(self.filter_target, iglob(path, True)))
        self.targets = set(self.targets)
        # self.before = self.get_status()
        self.before = {}

    def initialize(self):
        super(MonitorBase, self).initialize()
        self.before = self.get_status()

    def filter_target(self, target):
        if not os.path.lexists(target):
            self.logger.error("The path doesn't exist: {0}".format(target))
            return False
        for ignore in self.ignores:
            if fnmatch(target, ignore):
                return False

        return True

    def get_status(self):
        raise NotImplementedError

    def iter_diff(self, verbose=True):
        before = self.before
        after = self.get_status()
        events = {
            ADDED: [f for f in after if f not in before],
            REMOVED: [f for f in before if f not in after],
        }
        events[MODIFIED] = [
            f
            for f, mtime in after.items()
            if f not in events[ADDED] and mtime != before[f]
        ]
        self.before = after
        for event, items in events.items():
            for item in items:
                if verbose:
                    self.verbose(event, item, before.get(item, -1), after.get(item, -1))
            if items:
                yield event, items

    def diff(self, verbose=True):
        return list(self.iter_diff(verbose=verbose))

    def verbose(self, event, item, before, after):
        self.logger.info(
            "| {0} | {1}".format(
                event.upper(),
                item,
            )
        )

    def __call__(self, event=None):
        if self.event_manager.is_done and self.is_on_duty:
            self.schedule_next_run()
            if event:
                self.event_manager.on(event)
            else:
                for event, items in self.iter_diff():
                    self.event_manager.on(event)

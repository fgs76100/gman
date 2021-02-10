import logging
import os
import sys
import datetime
from crontab import CronTab
from generic import get_now, create_logger


logger = create_logger("Monitor")


class MonitorBase(object):
    logger = logger

    def __init__(self, schedule, targets, extensions=None, recursive=False, **kwargs):
        if isinstance(targets, str):
            targets = [targets]
        if not isinstance(targets, list):
            raise TypeError("target should be a list or a string")

        self.crontab = CronTab(schedule)
        self.next_run = None  # datetime object

        self.extensions = extensions
        self.recursive = recursive
        self.before = {}

        self.schedule_next_run()

        self.targets = filter(self.filter_target, targets)
        self.before = self.get_status()

    def schedule_next_run(self):
        now = get_now()
        self.next_run = now + datetime.timedelta(
            seconds=int(self.crontab.next(now, default_utc=True))
        )

    @property
    def is_on_duty(self):
        return get_now() >= self.next_run

    def filter_target(self, target):
        target = os.path.expandvars(target)
        target = os.path.abspath(target)
        if not os.path.exists(target):
            self.logger.error("The path doesn't exist: {0}".format(target))
            sys.exit(1)

        return True

    def get_status(self):
        raise NotImplementedError
        # return {}

    def iter_diff(self, verbose=True):
        before = self.before
        after = self.get_status()
        events = {
            "added": [f for f in after if f not in before],
            "removed": [f for f in before if f not in after],
        }
        events["modified"] = [
            f
            for f, mtime in after.items()
            if f not in events["added"] and mtime != before[f]
        ]
        self.before = after
        for event, items in events.items():
            for item in items:
                if verbose:
                    self.verbose(event, item, before.get(item, -1), after.get(item, -1))
            if items:
                yield event, items

        # return events

    def diff(self, verbose=True):
        return list(self.iter_diff(verbose=verbose))

    def verbose(self, event, item, before, after):
        self.logger.info(
            "[{0}] {1}".format(
                event.upper(),
                item,
            )
        )

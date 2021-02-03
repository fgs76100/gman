import logging
import os

logger = logging.getLogger("Monitor")
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    '%(asctime)s %(name)s [%(levelname)s] %(message)s',
    datefmt="%Y/%m/%d %H:%M:%S"
)

handler = logging.StreamHandler()

handler.setFormatter(formatter)
logger.addHandler(handler)


class MonitorBase(object):
    logger = logger

    def __init__(self, sources, extensions=None, recursive=False, **kwargs):
        if isinstance(sources, str):
            sources = [sources]
        if not isinstance(sources, list):
            raise TypeError("source should be a list or a string")

        self.extensions = extensions
        self.recursive = recursive
        self.before = {}

        self.sources = filter(self.check_source, sources)
        self.before = self.get_status()

    def check_source(self, source):
        source = os.path.expandvars(source)
        source = os.path.abspath(source)
        if not os.path.exists(source):
            self.logger.error(
                "The path doesn't exist: {0}".format(source)
            )
            exit(1)
        return source

    def get_status(self):
        raise NotImplementedError
        # return {}

    def iter_diff(self):
        before = self.before
        after = self.get_status()
        events = {
            "added": [f for f in after if f not in before],
            "removed": [f for f in before if f not in after]
        }
        events["modified"] = [
            f for f, mtime in after.items() if f not in events["added"] and mtime != before[f]
        ]
        self.before = after
        for event, items in events.items():
            for item in items:
                self.logger.info(
                    "[{0}] {1}".format(event.upper(), item)
                )
                yield event, items

        # return events

    def diff(self):
        return list(self.iter_diff())











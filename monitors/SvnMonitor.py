import MonitorBase
import subprocess
import os
import xml.etree.ElementTree
import time
import tempfile
from generic import indent

NAME_INDEX = -1
REVISION_INDEX = 0

ST_LOCK_COLUMN = 2


class SvnMonitor(MonitorBase.MonitorBase):
    def __init__(self, *args, **kwargs):
        self.depth = kwargs.get("depth", "empty")
        if self.depth != "empty":
            raise NotImplementedError("Sorry! Only support depth==empty.")
        self.worker = None
        self.stdout = None
        self.stderr = None
        super(SvnMonitor, self).__init__(*args, **kwargs)

    def kill(self):
        if self.worker is not None and self.worker.returncode is None:
            try:
                self.worker.kill()
            except OSError:
                pass
        if self.stdout:
            self.stdout.close()
        if self.stderr:
            self.stderr.close()
        super(SvnMonitor, self).kill()

    def run_command(self, command, wd=None, delete_log=True, **kwargs):
        command.append("--non-interactive")

        self.kill()  # for closing tempfile correctly

        # self.stdout = tempfile.TemporaryFile(prefix="SvnMonitor_stdout_")
        # self.stderr = tempfile.TemporaryFile(prefix="SvnMonitor_stderr_")
        self.stdout = tempfile.NamedTemporaryFile(
            prefix="SvnMonitor_stdout_", delete=delete_log, suffix=".log"
        )
        self.stderr = tempfile.NamedTemporaryFile(prefix="SvnMonitor_stderr_")

        worker = subprocess.Popen(
            command, cwd=wd, stdout=self.stdout, stderr=self.stderr, **kwargs
        )
        self.worker = worker
        worker.wait()

        if worker.returncode != 0:
            self.stderr.seek(0)
            self.logger.error(
                "Command failed with {0}: {1}\nERR: {2}".format(
                    worker.returncode,
                    " ".join(command),
                    "".join(self.stderr.readlines()),
                )
            )

        self.stdout.seek(0)
        return self.stdout

    def filter_target(self, target):

        options = ["--depth", "empty", "--verbose"]

        for status in self.svn_st(target=target, options=options):
            if status["item"] == "unversioned":
                self.logger.error(
                    "The path is not under version control: {0}".format(target)
                )
                return False

        return super(SvnMonitor, self).filter_target(target)

    def svn_st(self, target="", options=None, **kwargs):
        svn_st = ["svn", "st", "--xml", target]

        if isinstance(options, list):
            svn_st.extend(options)

        file_object = self.run_command(svn_st, delete_log=True, **kwargs)
        # TODO: change parse into iterpase
        root = xml.etree.ElementTree.parse(file_object)

        entries = root.findall("target/entry")

        for entry in entries:
            path = entry.attrib.get("path")
            wc_status = entry.find("wc-status")
            wc_locked = wc_status.attrib.get("wc-locked", "false")

            commit = wc_status.find("commit")
            if commit is None:
                revision = "-1"
            else:
                revision = commit.attrib.get("revision", "-1")

            item = wc_status.get("item", None)
            yield dict(path=path, revision=revision, wc_locked=wc_locked, item=item)

    def svn_up(self, target=".", **kwargs):
        svn_up = [
            "svn",
            "up",
            target,
            "--quiet",
        ]

        return self.run_command(svn_up, **kwargs)

    def svn_log(self, target, options=None, **kwargs):
        svn_log = ["svn", "log", target]
        if options:
            if not isinstance(options, list):
                raise TypeError("options should be a list.")
            svn_log.extend(options)

        return self.run_command(svn_log, **kwargs)

    def get_status(self):
        status = {}

        for target in self.targets:
            if self.before:
                self.svn_up(target)

            svn_st = self.svn_st(
                target=target,
                options=[
                    "--quiet",
                    "--verbose",
                    "--show-updates",
                    "--depth",
                    self.depth,
                ],
            )

            svn_st = list(svn_st)

            if len(svn_st) == 0:
                continue

            # TODO: support --depth infinity
            # currently only support --depth empty
            svn_st = svn_st[0]

            wc_locked = svn_st.get("wc_locked", "false")

            if wc_locked != "false":
                if target in self.before:
                    status[target] = self.before[target]
                continue

            revision = svn_st.get("revision")

            if revision != "" and revision != "-1":
                status[target] = revision

        return status

    def get_log(self, item, before, after):
        out = self.svn_log(
            item,
            options=[
                "--revision",
                "{1}:{0}".format(after, int(before) + 1),
                # "--xml",
                "--verbose",
            ],
            delete_log=False,
        )
        return self.stdout.name

    def verbose(self, event, path, before, after):
        title = "{revision} | {event} {path}{logs}"
        logs = ""

        if event == MonitorBase.REMOVED:
            revision = "r%s" % before
        elif event == MonitorBase.ADDED and os.path.isfile(path):
            revision = "r%s:r%s" % (after, before)
        elif event == MonitorBase.MODIFIED:
            revision = "r%s:r%s" % (after, before)

            logs = "\n%slog = %s" % (indent, self.get_log(path, before, after))
        else:
            raise NotImplementedError

        self.logger.info(
            "%s",
            title.format(revision=revision, event=event, path=path, logs=logs),
        )

from MonitorBase import MonitorBase
import subprocess
import os
import xml.etree.ElementTree
import sys

NAME_INDEX = -1
REVISION_INDEX = 0

ST_LOCK_COLUMN = 2


class SvnMonitor(MonitorBase):
    def __init__(self, *args, **kwargs):
        self.depth = kwargs.get("depth", "empty")
        super(SvnMonitor, self).__init__(*args, **kwargs)

    def run_command(self, command, wd=None, return_str=False, **kwargs):
        command.append("--non-interactive")

        worker = subprocess.Popen(
            command, cwd=wd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs
        )

        stdout, stderr = worker.communicate()
        returncode = worker.returncode

        if returncode != 0:
            self.logger.error(
                "Command failed with {0}: {1}\n\nOUT:\n{2}\n\nERR:\n{3}".format(
                    returncode, " ".join(command), stdout, stderr
                )
            )
            return None

        if return_str:
            return stdout

        return stdout.strip("\n").split("\n")

    def filter_target(self, target):

        options = ["--depth", "empty", "--verbose"]

        for status in self.svn_st(target=target, options=options):
            if status["item"] == "unversioned":
                self.logger.error(
                    "The path is not under version control: {0}".format(target)
                )
                sys.exit(1)

        return super(SvnMonitor, self).filter_target(target)

    def svn_st(self, target="", options=None, **kwargs):
        svn_st = ["svn", "st", "--xml", target]

        if isinstance(options, list):
            svn_st.extend(options)

        raw = self.run_command(svn_st, return_str=True, **kwargs)

        root = xml.etree.ElementTree.fromstring(raw)
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

            svn_st = svn_st[0]

            wc_locked = svn_st.get("wc_locked", "false")

            if wc_locked != "false":
                if target in self.before:
                    status[target] = self.before[target]
                continue

            revision = svn_st.get("revision")

            if revision != "" and revision != "-1":
                status[target] = revision

            self.svn_up(target)

        return status

    def get_log(self, event, item, before, after):
        raw = self.svn_log(
            item,
            options=[
                "--revision",
                "{1}:{0}".format(after, int(before) + 1),
                "--xml",
                "--verbose",
            ],
            return_str=True,
        )
        root = xml.etree.ElementTree.fromstring(raw)
        log_enties = root.findall("log/logentry")
        for entry in root.iter("logentry"):
            entry_info = {x.tag: x.text for x in list(entry)}

            entry_info["paths"] = []
            entry_info["revision"] = entry.attrib.get("revision")
            for path in entry.iter("path"):
                action = path.attrib.get("action")
                entry_info["paths"].append(dict(path=path.text, action=action))
            yield entry_info

    def verbose(self, event, path, before, after):
        indent = 4 * " "
        event = event.upper()
        msg = "r{revision} | {event} {path}"
        if event == "REMOVED":
            msg = msg.format(revision=before, event=event, path=path)
        elif event == "ADDED" and os.path.isfile(path):
            msg = msg.format(revision=after, event=event, path=path)
        else:
            msg = []

            msg.append(
                "r{after}:r{before} | {event} {path}".format(
                    event=event,
                    path=path,
                    before=before,
                    after=after,
                )
            )

            for log in self.get_log(event, path, before, after):
                msg.append(
                    "{indent}r{revision}  {author}  {msg}".format(indent=indent, **log)
                )
                if os.path.isdir(path):
                    for p in log["paths"]:
                        msg.append(
                            "{indent}{action}  {path}".format(indent=2 * indent, **p)
                        )
            msg = "{0}\n".format("\n".join(msg))

        self.logger.info(msg)

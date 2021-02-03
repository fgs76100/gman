from MonitorBase import MonitorBase
import subprocess
import os

NAME_INDEX = -1
REVISION_INDEX = 0

ST_LOCK_COLUMN = 2


class SvnMonitor(MonitorBase):

    def __init__(self, *args, **kwargs):
        self.depth = kwargs.get('depth', 'files')
        super(SvnMonitor, self).__init__(*args, **kwargs)

    def run_command(self, command, wd=None, return_str=False, **kwargs):
        command.append(
            "--non-interactive"
        )

        worker = subprocess.Popen(
            command,
            cwd=wd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kwargs
        )

        stdout, stderr = worker.communicate()
        returncode = worker.returncode

        if returncode != 0:
            self.logger.error(
                "Command failed with {0}: {1}\n\nOUT:\n{2}\n\nERR:\n{3}".format(
                    returncode,
                    " ".join(command),
                    stdout,
                    stderr
                )
            )
            return None

        if return_str:
            return stdout

        return stdout.strip("\n").split("\n")

    def svn_st(self, target=".", **kwargs):
        svn_st = [
            "svn",
            "st",
            "--show-updates",
            "--verbose",
            "--quiet",
            "--depth", self.depth,
            target
        ]

        return self.run_command(svn_st, **kwargs)

    def svn_up(self, target=".", **kwargs):
        svn_up = [
            "svn",
            "up",
            "--depth", self.depth,
            # "--quiet",
            target,
        ]

        return self.run_command(svn_up, **kwargs)

    def svn_list(self, target=".", **kwargs):
        svn_list = [
            "svn",
            "list",
            "--depth", self.depth,
            "--verbose",
            target
        ]

        return self.run_command(svn_list, **kwargs)

    def is_working_copy_locked(self, target):
        svn_st = self.svn_st(target=target)
        for st in svn_st[:-1]:
            st = st.split(" ")
            if st[ST_LOCK_COLUMN] == "L":
                return True
        else:
            return False

    def get_status(self):
        status = {}
        for source in self.sources:
            if os.path.isdir(source):
                # wd = working directory
                wd = source
            else:
                wd = os.path.abspath(os.path.join(source, os.pardir))

            # revision, is_lock = self.sync_with_remote(source)
            if len(self.before):
                if self.is_working_copy_locked(source):
                    for filename, revision in self.before.items():
                        if filename.startswith(source):
                            status[filename] = revision
                    continue
                self.svn_up(source)

            records = self.svn_list(target=source)
            for record in records:
                record = [item for item in record.split(" ") if item]
                filename = os.path.join(wd, record[NAME_INDEX])
                if not filename.endswith("./"):
                    status[filename] = record[REVISION_INDEX]

        return status

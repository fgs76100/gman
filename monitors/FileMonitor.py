from MonitorBase import MonitorBase
import os


class FileMonitor(MonitorBase):
    def gather_files(self):
        for target in self.targets:
            if os.path.isdir(target):
                if self.recursive:
                    for root, dirs, files in os.walk(target):
                        # remove hidden files and dirs
                        files = [f for f in files if not f.startswith(".")]
                        dirs[:] = [d for d in dirs if not d.startswith(".")]
                        for filename in files:
                            if self.endswith(filename):
                                yield os.path.join(root, filename)
                else:
                    for filename in os.listdir(target):
                        if not filename.startswith("."):
                            filename = os.path.join(target, filename)
                            if os.path.isfile(filename) and self.endswith(filename):
                                yield filename
            else:
                if os.path.exists(target) and self.endswith(target):
                    yield target

    def get_status(self):
        return dict([(f, os.path.getmtime(f)) for f in self.gather_files()])

    def endswith(self, string):
        if self.extensions is None:
            return True
        else:
            return string.endswith(self.extensions)

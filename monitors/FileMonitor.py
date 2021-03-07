from MonitorBase import MonitorBase
import os


class FileMonitor(MonitorBase):
    def gather_files(self):
        for target in self.iter_targets():
            if os.path.isdir(target):
                for filename in os.listdir(target):
                    if not filename.startswith("."):
                        filename = os.path.join(target, filename)
                        # if os.path.isfile(filename) and self.endswith(filename):
                        if os.path.isfile(filename):
                            yield filename
            else:
                # if os.path.lexists(target): # broken symbloic link does not have mtime stat, so cannot yield a broken link
                if os.path.exists(target):
                    yield target

    def get_status(self):
        return dict([(f, os.path.getmtime(f)) for f in self.gather_files()])

    # def endswith(self, string):
    #     if self.extensions is None:
    #         return True
    #     else:
    #         return string.endswith(self.extensions)

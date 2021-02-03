from __future__ import print_function
from monitors import FileMonitor, SvnMonitor
import time


if __name__ == '__main__':
    # test = FileMonitor(
    test = SvnMonitor(
        sources=[
            # "/Users/berdychzheng/projects/pythonProject/gman",
            "/Users/berdychzheng/projects/pythonProject/gman/unittest/two",
            "/Users/berdychzheng/projects/pythonProject/gman/unittest/two/test1/teset1.py",
        ],
        extensions=(".py"),
        recursive=False,
        # depth="files",
    )

    while True:
        try:
            # status = test.get_status()
            test.diff()
            time.sleep(2)
        except KeyboardInterrupt:
            exit(0)






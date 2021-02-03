#!/bin/zsh
local_repo=svn_local
test_file=test.py

cd ${local_repo}
## add a new file
touch ${test_file}
svn add ${test_file}
svn ci -m "add test file"
sleep 3

## edit files
echo "# add a line" >> ${test_file}
echo "# end of line" >> ./FileMonitor.py
svn ci -m "edit test file"
sleep 3

## delete the new file
svn del ${test_file}
svn ci -m "delete test file"
sleep 3

# rm -rf ${remote_repo} ${local_repo}

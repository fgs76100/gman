#!/bin/zsh

remote_repo=svn_remote
local_repo=svn_local

svnadmin create ${remote_repo}
cd ${remote_repo}
svn import $(pwd)/../../monitors file://$(pwd)/trunk -m "initial commit"
cd -

svn co file://$(pwd)/${remote_repo}/trunk ${local_repo}


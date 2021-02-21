#!/bin/bash

remote_repo=svn_remote
local_repo=svn_local

svnadmin create ${remote_repo}
cd ${remote_repo}
svn import $(pwd)/../root file://$(pwd)/trunk/root -m "initial commit"
cd -

svn co file://$(pwd)/${remote_repo} "${local_repo}1"
svn co file://$(pwd)/${remote_repo} "${local_repo}2"


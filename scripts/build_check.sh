#!/usr/bin/env bash
cd /home/ubuntu/tallyql
sudo rm -rf build/ dist/ *.egg-info src/*.egg-info 2>/dev/null
python3 -m build 2>&1 | tail -4
echo "BUILD_EXIT=$?"

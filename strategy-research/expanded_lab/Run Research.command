#!/bin/zsh
lab_dir=$(cd -- "$(dirname -- "$0")" && pwd)
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$lab_dir/launch.py" run
result=$?
printf "\nResearch ended with status %s. Press Return to close.\n" "$result"
read reply
exit "$result"

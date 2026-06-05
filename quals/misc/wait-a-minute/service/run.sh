#!/bin/sh

TIME_LIMIT=60

echo "Input your python code:"
echo -n ">>> "
read -r input

output=$(timeout "$TIME_LIMIT" python server.py "$input" 2>&1)
status=$?

case $status in
    0) echo "$output" ;;
    1) echo "$output" ;;
    *) echo "Internal error (code $status). Report to admin: $(cat logs/err.log)" ;;
esac
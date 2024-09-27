#!/bin/sh

# Start the first process
python3 -m app_monitor &
      
# Exit with status of process that exited first
exit $?

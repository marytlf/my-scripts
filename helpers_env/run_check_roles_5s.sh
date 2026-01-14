#!/bin/bash

# --- Configuration ---
INTERVAL=5  # Time in seconds to wait between runs
COMMAND="./check_roles.sh"  # Replace this with your actual command

echo "Starting loop to run command every $INTERVAL seconds. Press Ctrl+C to stop."
echo "----------------------------------------------------------------------"

while true; do
    # Execute the command
    eval $COMMAND
    
    # Wait for the specified interval
    sleep $INTERVAL
done


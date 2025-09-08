#!/bin/bash

# Define the path to the hosts file
HOSTS_FILE="/etc/hosts"

# --- Functions ---

# Function to display usage instructions
usage() {
    echo "Usage: $0 [-a | -r | -d] <ip_address> <hostname_prefix>"
    echo "  -a: Add a new entry to the /etc/hosts file."
    echo "  -r: Replace an existing entry with the pattern 'sa-east-1.compute.internal'."
    echo "  -d: Delete an existing entry with the provided hostname."
    echo "  The script will automatically append '.sa-east-1.compute.internal' to the hostname prefix."
    exit 1
}

# Function to check for root permissions
check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo "This script must be run as root."
        exit 1
    fi
}

# --- Main Logic ---

# Check for root permissions at the start
check_root

# Check if at least three arguments are provided (option, IP, hostname)
if [ "$#" -lt 3 ]; then
    usage
fi

# Store the provided arguments in variables for clarity
OPTION=$1
IP_ADDRESS=$2
HOSTNAME_PREFIX=$3

# Concatenate the hostname prefix with the full domain name
FULL_HOSTNAME="${HOSTNAME_PREFIX}.sa-east-1.compute.internal"

# Use a case statement to handle the different options
case "$OPTION" in
    -a)
        # Add a new entry to the hosts file
        echo "Adding entry: $IP_ADDRESS $FULL_HOSTNAME"
        echo -e "$IP_ADDRESS\t$FULL_HOSTNAME" | sudo tee -a $HOSTS_FILE > /dev/null
        echo "Entry added successfully."
        ;;
    -r)
        # Define the regex pattern to find the line to replace
        # This pattern matches any line containing the specified internal domain
        # The 'c' command in sed changes the entire line
        REGEX_PATTERN="sa-east-1.compute.internal"

        echo "Replacing entry with new details: $IP_ADDRESS $FULL_HOSTNAME"

        # The sed command finds the line with the pattern and replaces it
        # -i flag modifies the file in place
        # The 'c' command means 'change'
        sudo sed -i "/$REGEX_PATTERN/c\\$IP_ADDRESS\t$FULL_HOSTNAME" $HOSTS_FILE

        # Check if the sed command was successful
        if [ $? -eq 0 ]; then
            echo "Entry replaced successfully."
        else
            echo "Error: Could not find or replace entry with pattern '$REGEX_PATTERN'."
            exit 1
        fi
        ;;
    -d)
        # Define the regex pattern to find the line to delete
        # This pattern matches the full hostname
        REGEX_PATTERN="[[:space:]]$FULL_HOSTNAME"

        echo "Removing entry for: $FULL_HOSTNAME"

        # The sed command finds the line with the pattern and deletes it
        # -i flag modifies the file in place
        # The 'd' command means 'delete'
        sudo sed -i "/$REGEX_PATTERN/d" $HOSTS_FILE

        # Check if the sed command was successful
        if [ $? -eq 0 ]; then
            echo "Entry removed successfully."
        else
            echo "Error: Could not find or remove entry for '$FULL_HOSTNAME'."
            exit 1
        fi
        ;;
    *)
        # If the option is not -a, -r, or -d, display usage and exit
        usage
        ;;
esac

#!/bin/bash

# Get the current date in YYYY-MM-DD format
DATE=$(date +%Y-%m-%d)
VER="_$1"

# Create a directory to store logs if it doesn't exist
LOG_DIR="pod_logs_${DATE}${VER}"
mkdir -p "$LOG_DIR"

echo "Saving pod logs to directory: $LOG_DIR"

# Get all namespaces
NAMESPACES=$(kubectl get namespaces -o jsonpath='{.items[*].metadata.name}')

# Loop through each namespace
for NAMESPACE in $NAMESPACES
do
    echo "Processing namespace: $NAMESPACE"

    # Get all pods in the current namespace
    PODS=$(kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}')

    # Loop through each pod in the current namespace
    for POD in $PODS
    do
        echo "  - Fetching logs for pod: $POD in namespace: $NAMESPACE"
        
        # Define the output filename
        FILENAME="${LOG_DIR}/${NAMESPACE}_${POD}_${DATE}.log"

        # Get logs for the current pod and save to file
        # Check if the pod has multiple containers
        CONTAINERS=$(kubectl get pod "$POD" -n "$NAMESPACE" -o jsonpath='{.spec.containers[*].name}')
        NUM_CONTAINERS=$(echo "$CONTAINERS" | wc -w)

        if [ "$NUM_CONTAINERS" -gt 1 ]; then
            echo "    Pod $POD in namespace $NAMESPACE has multiple containers. Fetching logs for each."
            for CONTAINER in $CONTAINERS; do
                echo "      - Fetching logs for container: $CONTAINER"
                kubectl logs "$POD" -n "$NAMESPACE" -c "$CONTAINER" > "${FILENAME%.log}_${CONTAINER}.log" 2>&1
                if [ $? -ne 0 ]; then
                    echo "      WARNING: Could not retrieve logs for container $CONTAINER in pod $POD in namespace $NAMESPACE."
                fi
            done
        else
            kubectl logs "$POD" -n "$NAMESPACE" > "$FILENAME" 2>&1
            if [ $? -ne 0 ]; then
                echo "    WARNING: Could not retrieve logs for pod $POD in namespace $NAMESPACE."
            fi
        fi
    done
done

echo "Log collection complete. Logs are saved in the '$LOG_DIR' directory."

#!/bin/bash

# --- Configuration ---
RANCHER_NAMESPACE="fleet-default"
TARGET_LABEL="node-role.kubernetes.io/worker"

# Global flag for verbose output (default is off)
VERBOSE=0

# --- Option Parsing ---
while getopts "v" opt; do
    case ${opt} in
        v )
            VERBOSE=1
            ;;
        \? )
            echo "Usage: $0 [-v]"
            echo "  -v: Enable verbose mode (print all node labels and details)."
            exit 1
            ;;
    esac
done
shift $((OPTIND - 1))

# --- Main Script ---

echo "--- Starting Node Label Check via Management API ---"
echo "Searching namespace: ${RANCHER_NAMESPACE}"
echo "----------------------------------------------------"

if ! command -v jq &> /dev/null; then
    echo "ERROR: 'jq' is required for this script. Please install it (sudo apt install jq)."
    exit 1
fi

CLUSTER_NAMES=$(kubectl get clusters.provisioning.cattle.io -n "${RANCHER_NAMESPACE}" -o jsonpath='{.items[*].metadata.name}')

if [ -z "$CLUSTER_NAMES" ]; then
    echo "No Cluster resources found in the ${RANCHER_NAMESPACE} namespace."
    exit 0
fi

MISSING_NODES_FOUND=0

# 1. Loop through each Cluster
for CLUSTER_NAME in $CLUSTER_NAMES; do
    
    echo "Checking Cluster: ${CLUSTER_NAME}..."

    # Get the full Cluster resource JSON
    CLUSTER_JSON=$(kubectl get clusters.provisioning.cattle.io "${CLUSTER_NAME}" -n "${RANCHER_NAMESPACE}" -o json)
    
    # 2. Extract the entire array of node objects from the .status.nodes field
    # The -c flag makes each node object a single line for easy shell iteration
    NODE_ARRAY=$(echo "$CLUSTER_JSON" | jq -c '.status.nodes[]?')

    if [ -z "$NODE_ARRAY" ]; then
        echo "  [WARN] Node details are empty in status field for ${CLUSTER_NAME}. Skipping."
        continue
    fi
    
    # 3. Loop through each extracted node JSON object
    # We use 'read' to safely process each JSON object line-by-line
    while read -r NODE_JSON; do
        
        # Extract name and check labels within the current node's JSON
        NODE_NAME=$(echo "$NODE_JSON" | jq -r '.nodeName')
        
        # Check if the target label exists (jq returns null if label is not present)
        # We check for the specific label key within the .labels object
        LABEL_EXISTS=$(echo "$NODE_JSON" | jq -r ".labels[\"${TARGET_LABEL}\"] // empty")

        if [ "$VERBOSE" -eq 1 ]; then
            # Verbose Mode: Print all labels/annotations
            echo "  --- Node: ${NODE_NAME} (VERBOSE) ---"
            echo "    Labels:"
            echo "$NODE_JSON" | jq '.labels' | sed 's/^/      /g'
            echo "    Annotations:"
            echo "$NODE_JSON" | jq '.annotations' | sed 's/^/      /g'
            echo "  -----------------------------------"
        fi

        if [ -z "$LABEL_EXISTS" ]; then
            # The label key was NOT found
            echo "  [MISSING] Cluster: ${CLUSTER_NAME}, Node: ${NODE_NAME}"
            MISSING_NODES_FOUND=1
        fi

    done <<< "$NODE_ARRAY"
done

echo "----------------------------------------"

if [ "$MISSING_NODES_FOUND" -eq 0 ]; then
    echo "SUCCESS: All checked nodes have the '${TARGET_LABEL}' label."
else
    echo "Verification complete. See [MISSING] entries above."
fi

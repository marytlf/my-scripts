#!/bin/bash

# --- Configuration ---
# The namespace where your Cluster resources reside
RANCHER_NAMESPACE="fleet-default"

# The target label to check for
TARGET_LABEL="node-role.kubernetes.io/worker"



wait_for_cluster_active() {
    local CLUSTER_NAME=$1
    local MAX_ATTEMPTS=3
    local DELAY=15
    local KUBE_CONTEXT=$2

    echo "  -> Waiting for Cluster ${CLUSTER_NAME} to stabilize..."

    for ((i=1; i<=$MAX_ATTEMPTS; i++)); do
        # We check both STATE (for safety) and try connecting to the Kube API
        if kubectl get clusters.provisioning.cattle.io "${CLUSTER_NAME}" -n fleet-default -o jsonpath='{.status.state}' | grep -q 'active'; then
            # Even if the state is active, ensure the context is reachable
            if kubectl --context "${KUBE_CONTEXT}" get nodes > /dev/null 2>&1; then
                echo "  -> Cluster is ACTIVE and reachable."
                return 0
            fi
        fi
        echo "  Attempt $i/${MAX_ATTEMPTS}: Not yet fully active or reachable. Waiting ${DELAY}s..."
        sleep $DELAY
    done

    echo "  ❌ Cluster failed to reach a fully active state within the timeout."
    return 1
}


# --- Main Script ---

echo "--- Starting Worker Node Label Check ---"
echo "Searching for missing label: ${TARGET_LABEL} in namespace: ${RANCHER_NAMESPACE}"
echo "----------------------------------------"

# 1. Get the names of all Cluster resources in the target namespace
# The provisioned cluster names are stored as 'clusters.provisioning.cattle.io'
CLUSTER_NAMES=$(kubectl get clusters.provisioning.cattle.io -n "${RANCHER_NAMESPACE}" -o jsonpath='{.items[*].metadata.name}')

# Check if any clusters were found
if [ -z "$CLUSTER_NAMES" ]; then
    echo "No Cluster resources found in the ${RANCHER_NAMESPACE} namespace."
    exit 0
fi

# Flag to track if any missing nodes were found
MISSING_NODES_FOUND=0

# 2. Loop through each Cluster (the downstream cluster name)
for CLUSTER_NAME in $CLUSTER_NAMES; do
    
    echo "Checking Cluster: ${CLUSTER_NAME}..."

    # The actual Kubernetes cluster name is typically stored in the status field
    KUBE_CLUSTER_NAME=$(kubectl get clusters.provisioning.cattle.io "${CLUSTER_NAME}" -n "${RANCHER_NAMESPACE}" -o jsonpath='{.status.clusterName}')
     
    if ! wait_for_cluster_active "${CLUSTER_NAME}" 15 "${KUBE_CLUSTER_NAME}"; then
        echo "  [SKIP] Skipping check for unstable cluster ${CLUSTER_NAME}."
        continue
    fi

    if [ -z "$KUBE_CLUSTER_NAME" ]; then
        echo "  [SKIP] Could not find the underlying Kubernetes cluster name for ${CLUSTER_NAME}."
        continue
    fi

    # 3. Use the 'rancher kubectl' command to target the specific downstream cluster.
    #    The command below gets all node names from the downstream cluster.
    NODE_NAMES=$(kubectl --context "${KUBE_CLUSTER_NAME}" get nodes -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
    
    if [ -z "$NODE_NAMES" ]; then
        echo "  [WARN] No nodes found or failed to connect to cluster ${CLUSTER_NAME} (Context: ${KUBE_CLUSTER_NAME})."
        continue
    fi

    # 4. Loop through each Node in the downstream cluster
    for NODE_NAME in $NODE_NAMES; do
        
        # Check if the node has the target label. We use grep to check the output of JSONPath.
        HAS_LABEL=$(kubectl --context "${KUBE_CLUSTER_NAME}" get node "${NODE_NAME}" -o jsonpath="{.metadata.labels}" | grep "${TARGET_LABEL}")

        if [ -z "$HAS_LABEL" ]; then
            # Label is missing!
            echo "  [MISSING] Cluster: ${CLUSTER_NAME}, Node: ${NODE_NAME}"
            MISSING_NODES_FOUND=1
        fi
    done
done

echo "----------------------------------------"

if [ "$MISSING_NODES_FOUND" -eq 0 ]; then
    echo "SUCCESS: All checked nodes have the '${TARGET_LABEL}' label."
else
    echo "Verification complete. See [MISSING] entries above."
fi

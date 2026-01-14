#!/bin/bash

# --- Configuration ---
CLUSTER_TEMPLATE_FILE="cluster_template.yaml"
MC_TEMPLATE_FILE="machine_config_template.yaml"
OUTPUT_DIR="clusters"

# --- Functions ---
generate_uid() { head /dev/urandom | tr -dc a-f0-9 | head -c 32; } # Longer UID for cluster
generate_random_suffix() { head /dev/urandom | tr -dc a-z0-9 | head -c 5; }

# --- Main Script ---

if [ ! -f "$CLUSTER_TEMPLATE_FILE" ] || [ ! -f "$MC_TEMPLATE_FILE" ]; then
    echo "Error: Both template files ('cluster_template.yaml' and 'machine_config_template.yaml') must exist."
    exit 1
fi

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <NUMBER_OF_CLUSTERS> <NODES_PER_POOL>"
    exit 1
fi

NUM_CLUSTERS=$1
NUM_NODES=$2

mkdir -p "$OUTPUT_DIR"
echo "--- Starting Cluster Generation ---"

for i in $(seq 1 $NUM_CLUSTERS); do
    CLUSTER_INDEX=$(printf "%02d" $i)
    CLUSTER_NAME="load-cluster-${CLUSTER_INDEX}"
    
    # 1. Generate ALL Unique IDs/Names
    CLUSTER_UID=$(generate_uid) # New UID for the Cluster resource
    NEW_MACHINECONFIG_REF_SUFFIX_CP=$(generate_random_suffix)
    NEW_MACHINECONFIG_REF_SUFFIX_WKR=$(generate_random_suffix)
    NEW_CLUSTER_STATUS_ID=$(generate_random_suffix) 

    # Machine Config Full Names (These MUST match the 'name' fields in both YAMLs)
    CP_MC_NAME="nc-${CLUSTER_NAME}-cp-${NEW_MACHINECONFIG_REF_SUFFIX_CP}"
    WKR_MC_NAME="nc-${CLUSTER_NAME}-wkr-${NEW_MACHINECONFIG_REF_SUFFIX_WKR}"

    # --- 2. Generate Amazonec2Config YAMLs ---
    
    # A. Control Plane/ETCD Machine Config
    MC_CP_FILE="$OUTPUT_DIR/${CP_MC_NAME}.yaml"
    cp "$MC_TEMPLATE_FILE" "$MC_CP_FILE"
    
    # Replace MC placeholders in the CP file
    sed -i "s/PLACEHOLDER_MC_NAME/${CP_MC_NAME}/g" "$MC_CP_FILE"
    sed -i "s/PLACEHOLDER_CLUSTER_NAME/${CLUSTER_NAME}/g" "$MC_CP_FILE"
    sed -i "s/PLACEHOLDER_CLUSTER_UID/${CLUSTER_UID}/g" "$MC_CP_FILE"
    sed -i "s/PLACEHOLDER_MC_GENERATE_NAME/nc-${CLUSTER_NAME}-cp/g" "$MC_CP_FILE" # For generateName
    
    # B. Worker Machine Config
    MC_WKR_FILE="$OUTPUT_DIR/${WKR_MC_NAME}.yaml"
    cp "$MC_TEMPLATE_FILE" "$MC_WKR_FILE"
    
    # Replace MC placeholders in the WKR file
    sed -i "s/PLACEHOLDER_MC_NAME/${WKR_MC_NAME}/g" "$MC_WKR_FILE"
    sed -i "s/PLACEHOLDER_CLUSTER_NAME/${CLUSTER_NAME}/g" "$MC_WKR_FILE"
    sed -i "s/PLACEHOLDER_CLUSTER_UID/${CLUSTER_UID}/g" "$MC_WKR_FILE"
    sed -i "s/PLACEHOLDER_MC_GENERATE_NAME/nc-${CLUSTER_NAME}-wkr/g" "$MC_WKR_FILE"
    
    # --- 3. Generate Cluster YAML ---
    

    CLUSTER_OUTPUT_FILE="$OUTPUT_DIR/${CLUSTER_NAME}.yaml"
    cp "$CLUSTER_TEMPLATE_FILE" "$CLUSTER_OUTPUT_FILE"

    # CRITICAL: Replace ALL references in the Cluster YAML
    sed -i "s/name: cluster-03/name: ${CLUSTER_NAME}/g" "$CLUSTER_OUTPUT_FILE"
    sed -i "s/management-cluster-display-name: cluster-03/management-cluster-display-name: ${CLUSTER_NAME}/g" "$CLUSTER_OUTPUT_FILE"

    # Replace Machine Pool Names
    sed -i "s/pool-cluster-03/pool-${CLUSTER_NAME}-cp/g" "$CLUSTER_OUTPUT_FILE"
    sed -i "s/pool-cluster-04/pool-${CLUSTER_NAME}-wkr/g" "$CLUSTER_OUTPUT_FILE"

    # --- NEW FIX: Replace the faulty prefix (e.g., nc-cluster-03-pool) ---
    # This replacement is crucial because the full name might contain dynamic suffixes
    # and we only want to fix the hardcoded "cluster-03-pool" part.
    sed -i "s/nc-cluster-03-pool-cluster-03/nc-${CLUSTER_NAME}/g" "$CLUSTER_OUTPUT_FILE"
    sed -i "s/nc-cluster-03-pool-cluster-04/nc-${CLUSTER_NAME}/g" "$CLUSTER_OUTPUT_FILE"

    # OLD, Simple Replacement (MUST BE VERIFIED AGAINST TEMPLATE):
    # This assumes the template only contains the old name.
    # If the template contains 'nc-cluster-03-pool-cluster-03-p5r49', these lines are necessary:
    #sed -i "s/nc-cluster-03-pool-cluster-03-p5r49/${CP_MC_NAME}/g" "$CLUSTER_OUTPUT_FILE"
    #sed -i "s/nc-cluster-03-pool-cluster-04-474qb/${WKR_MC_NAME}/g" "$CLUSTER_OUTPUT_FILE"

    sed -i "s/PLACEHOLDER_MC_REF_CP/${CP_MC_NAME}/g" "$CLUSTER_OUTPUT_FILE"
    sed -i "s/PLACEHOLDER_MC_REF_WKR/${WKR_MC_NAME}/g" "$CLUSTER_OUTPUT_FILE"

    # Node Quantity, UID, Status ID cleanup
    sed -i "s/quantity: 3/quantity: ${NUM_NODES}/g" "$CLUSTER_OUTPUT_FILE"
    sed -i "s/uid: 7fb2209c-f024-4f39-bc8e-efc016b3f1d5/uid: ${CLUSTER_UID}/g" "$CLUSTER_OUTPUT_FILE"
    sed -i "s/clusterName: c-m-dzp4wkbz/clusterName: c-m-${NEW_CLUSTER_STATUS_ID}/g" "$CLUSTER_OUTPUT_FILE"
    sed -i "/creationTimestamp:/d" "$CLUSTER_OUTPUT_FILE"
    sed -i "/resourceVersion:/d" "$CLUSTER_OUTPUT_FILE"
    
    echo "  -> Created ${CLUSTER_NAME}.yaml and supporting Machine Configs."
done

echo "--- Generation Complete ---"

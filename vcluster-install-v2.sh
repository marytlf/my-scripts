#!/bin/bash
set -e

# --- Configuration Variables ---
VCLUSTER_NAME="rancher-vcluster"
K3D_CLUSTER_NAME="my-host-cluster"
#RANCHER_HOSTNAME=$(hostname).sa-east-1.compute.internal
RANCHER_HOSTNAME=$(hostname)
RANCHER_PASSWORD="admin" # Change this to a secure password

# --- Step 1: Clean up previous deployments (Idempotent) ---
echo "--- Step 1: Cleaning up any previous deployments ---"
vcluster disconnect > /dev/null 2>&1 || true
vcluster delete "$VCLUSTER_NAME" > /dev/null 2>&1 || true
k3d cluster delete "$K3D_CLUSTER_NAME" > /dev/null 2>&1 || true
echo "Clean up complete."
echo ""

# --- Step 2: Create the K3D Host Cluster ---
echo "--- Step 2: Creating K3D host cluster ---"
k3d cluster create "$K3D_CLUSTER_NAME" --image rancher/k3s:v1.29.5-k3s1
echo "K3D cluster created."
echo ""

# --- Step 3: Create the vcluster and Wait for it to be Ready ---
echo "--- Step 3: Creating vcluster '$VCLUSTER_NAME' and waiting for it to be ready ---"
# Create a temporary vcluster.yaml file with the configuration
cat <<EOF > /tmp/vcluster.yaml
apiVersion: v1beta1
kind: VCluster
metadata:
  name: $VCLUSTER_NAME
spec:
  distro:
    k8s:
      # Explicitly setting a known-good image version to avoid errors
      image:
        repository: ghcr.io/loft-sh/vcluster
        tag: "0.28.0"
  resources:
    limits:
      cpu: 500m
      memory: 256Mi
    requests:
      cpu: 250m
      memory: 128Mi
EOF

# Create the vcluster using the configuration file
vcluster create "$VCLUSTER_NAME" --distro k8s -f /tmp/vcluster.yaml
rm /tmp/vcluster.yaml

# Give the pod a moment to be created before we start the loop
sleep 5

# Critical: This loop waits until the vcluster pod is running
#while [ "$(kubectl get pods -n vcluster-$VCLUSTER_NAME -o jsonpath='{.items[0].status.phase}')" != "Running" ]; do
#  echo "Waiting for vcluster pod to be in 'Running' state..."
#  sleep 5
#done
echo "vcluster is now running."
echo ""

# --- Step 4: Install an Ingress Controller inside the vcluster ---
# This step is crucial to ensure the Rancher Ingress can be created.
echo "--- Step 4: Installing an Ingress Controller into the vcluster ---"
vcluster connect "$VCLUSTER_NAME" -- helm repo add traefik https://helm.traefik.io/traefik
vcluster connect "$VCLUSTER_NAME" -- helm repo update
vcluster connect "$VCLUSTER_NAME" -- helm install traefik traefik/traefik \
  --namespace kube-system
echo "Ingress controller installed."
echo ""

# --- Step 5: Install Cert-Manager inside the vcluster ---
echo "--- Step 5: Installing Cert-Manager into the vcluster ---"
vcluster connect "$VCLUSTER_NAME" -- kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.2/cert-manager.crds.yaml

vcluster connect "$VCLUSTER_NAME" -- helm repo add jetstack https://charts.jetstack.io
vcluster connect "$VCLUSTER_NAME" -- helm repo update

vcluster connect "$VCLUSTER_NAME" -- helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version v1.17.2 \
  --set crds.enabled=false
echo "Cert-Manager installed."
echo ""

# --- Step 6: Install Rancher and create the Ingress ---
echo "--- Step 6: Installing Rancher with Ingress ---"
vcluster connect "$VCLUSTER_NAME" -- helm repo add rancher-stable https://releases.rancher.com/server-charts/stable
vcluster connect "$VCLUSTER_NAME" -- helm repo update

vcluster connect "$VCLUSTER_NAME" -- helm upgrade --install rancher rancher-stable/rancher \
  --namespace cattle-system \
  --create-namespace \
  --set replicaCount=1 \
  --set hostname="$RANCHER_HOSTNAME" \
  --set ingress.enabled=true \
  --set bootstrapPassword="$RANCHER_PASSWORD"
echo "Rancher installation started. Please wait a few minutes for the pods to be ready."
echo ""

# --- Step 7: Instructions for Access ---
echo "--- Deployment Complete ---"
echo "The Rancher dashboard is now deploying inside the vcluster."
echo "Once the pods are ready, you can access the dashboard."
echo "Open a new terminal and run the following command to connect to the vcluster:"
echo ""
echo "    vcluster connect rancher-vcluster"
echo ""
echo "Then, open your browser and navigate to the following URL:"
echo ""
echo "    https://$RANCHER_HOSTNAME"
echo ""
echo "Remember to set up SSH port forwarding and to add the hostname to your local /etc/hosts file if you are on a remote server."


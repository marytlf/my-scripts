sudo systemctl stop rke2-server
sudo /usr/local/bin/rke2-uninstall.sh
sudo systemctl stop k3s
sudo /usr/local/bin/k3s-uninstall.sh


vcluster disconnect
vcluster delete rancher-vcluster
k3d cluster delete my-host-cluster

k3d cluster create my-host-cluster --image rancher/k3s:v1.29.5-k3s1

vcluster create rancher-vcluster --distro k8s --kubernetes-version 1.31.10 --image ghcr.io/loft-sh/vcluster:0.28.0

# **Wait for the vcluster pod to be Running.**
# Run the following command and wait until you see the 'STATUS' as 'Running'
kubectl get pods -n vcluster-rancher-vcluster

vcluster connect rancher-vcluster

# This command installs the Cert-Manager CRDs
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.2/cert-manager.crds.yaml

# Add the jetstack helm repo
helm repo add jetstack https://charts.jetstack.io
helm repo update

# Install Cert-Manager
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version v1.17.2 \
  --set crds.enabled=false


helm repo add rancher-stable https://releases.rancher.com/server-charts/stable
helm repo update
HOST=$(hostname)
helm upgrade --install rancher rancher-stable/rancher \
  --namespace cattle-system \
  --create-namespace \
  --set replicaCount=3 \
  --set hostname=${HOST}.sa-east-1.compute.internal \
  --set bootstrapPassword=admin \
  --version=v2.10.0

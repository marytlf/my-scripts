sudo systemctl stop rke2-server
sudo /usr/local/bin/rke2-uninstall.sh
sudo systemctl stop k3s
sudo /usr/local/bin/k3s-uninstall.sh

# Disconnect from the vcluster (if you are still connected)
vcluster disconnect

# Delete the vcluster
vcluster delete rancher-vcluster

# Delete the k3d cluster
k3d cluster delete my-host-cluster

sleep 10

HOST=$(hostname)

if grep -q "ID=sles" /etc/os-release || grep -q "ID=opensuse" /etc/os-release; then
    echo "SUSE OS detected. Installing k3s-selinux..."
    sudo zypper install k3s-selinux -y
else
    echo "Non-SUSE OS detected. Skipping k3s-selinux installation."
fi

curl -sfLk https://get.k3s.io | sudo INSTALL_K3S_VERSION=v1.31.10+k3s1 sh -s -
#curl -sfLk https://get.k3s.io | sudo sh -s -

sleep 2

sudo systemctl enable k3s
sudo systemctl start k3s

sleep 10

curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

sudo ln -s /var/lib/rancher/k3s/bin/kubectl /usr/local/bin/kubectl
export PATH=$PATH:/usr/local/bin/k3s

mkdir -p .kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER:$USER /home/$USER/.kube/config 
sudo chmod 600 /home/$USER/.kube/config
export KUBECONFIG=/home/$USER/.kube/config
kubectl get nodes

sleep 5

kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.2/cert-manager.crds.yaml

helm repo add jetstack https://charts.jetstack.io
helm repo update
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version v1.17.2 \
  --set crds.enabled=false

sleep 60
#helm repo rm rancher-alpha
#helm repo add rancher-alpha https://releases.rancher.com/server-charts/alpha
#helm repo update
#helm upgrade --install rancher rancher-alpha/rancher \
#  --devel \
#  --namespace cattle-system \
#  --set rancherImageTag=head \
#  --set "extraEnv[0].name=CATTLE_SERVER_URL" \
#  --set "extraEnv[1].name=CATTLE_AGENT_IMAGE" \
#  --set hostname=ip-172-31-36-232.sa-east-1.compute.internal \
#  --set bootstrapPassword=admin \
#  --set agentTLSMode=system-store \
#  --set replicas=1 --create-namespace \
#  --set global.cattle.image.repository=docker.io/rancher/rancher \
#  --set global.cattle.image.tag=v2.12-5814c45fd818a99b0c7a95406445bc85deb535e9-head \
#  --set global.cattle.image.pullPolicy=Never \
#  --set "extraEnv[0].value=ip-172-31-36-232.sa-east-1.compute.internal" \
#  --set "extraEnv[1].value=rancher/rancher-agent:head" \
#  --version=v2.12.0-alpha9
#

helm repo add rancher-latest https://releases.rancher.com/server-charts/latest
helm install rancher rancher-latest/rancher \
  --namespace cattle-system \
  --set hostname=${HOST}.sa-east-1.compute.internal \
  --set replicas=3 \
  --set bootstrapPassword=admin \
  --version=2.12.1 --create-namespace 
  
source ~/.bashrc
touch ~/.bash_aliases
if [ -z "$KUBECONFIG" ]; then
    # If it's empty, set the default path
    export KUBECONFIG=/home/$USER/.kube/config
else
    echo "if [ -z \"\$KUBECONFIG\" ]; then
    export KUBECONFIG=/home/ubuntu/.kube/config
    fi" >> ~/.bash_aliases
    export KUBECONFIG=/home/$USER/.kube/config
fi
source ~/.bash_aliases
source ~/.bashrc

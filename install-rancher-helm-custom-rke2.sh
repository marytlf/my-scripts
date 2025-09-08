sudo systemctl stop rke2-server.service
sudo /usr/local/bin/rke2-uninstall.sh
sudo systemctl stop k3s
sudo /usr/local/bin/k3s-uninstall.sh

sleep 10

#sudo zypper install k3s-selinux -y
if grep -q "ID=sles" /etc/os-release || grep -q "ID=opensuse" /etc/os-release; then
    echo "SUSE OS detected. Installing k3s-selinux..."
    sudo zypper install k3s-selinux -y
else
    echo "Non-SUSE OS detected. Skipping k3s-selinux installation."
fi

curl -sfL https://get.rke2.io | sudo INSTALL_RKE2_VERSION=v1.30.0+rke2r1 sh -

sleep 2

sudo systemctl enable rke2-server.service
sudo systemctl start rke2-server.service

sleep 10

sudo ln -s /var/lib/rancher/rke2/bin/kubectl /usr/local/bin/kubectl

mkdir -p .kube
sudo cp /etc/rancher/rke2/rke2.yaml .kube/config
sudo chown ubuntu:ubuntu /home/ubuntu/.kube/config
sudo chmod 600 /home/ubuntu/.kube/config
export KUBECONFIG=/home/ubuntu/.kube/config
kubectl get nodes

curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.2/cert-manager.crds.yaml

helm repo add jetstack https://charts.jetstack.io
helm repo update
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version v1.17.2 \
  --set crds.enabled=false

sleep 60

if [ ! -f "rancher-values.yaml" ]; then
    echo "Error: rancher-values.yaml not found!" >&2
    exit 1
fi

helm repo add rancher-latest https://releases.rancher.com/server-charts/latest
helm install rancher rancher-latest/rancher \
  --namespace cattle-system --create-namespace \
  --set replicas=1 \
  --set bootstrapPassword=admin \
  --version=v2.12.0 \
  --values rancher-values.yaml
  
  
source ~/.bashrc
touch ~/.bash_alises
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

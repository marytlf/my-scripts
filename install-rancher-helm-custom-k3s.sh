sudo systemctl stop rke2-server.service
sudo /usr/local/bin/rke2-uninstall.sh
sudo systemctl stop k3s
sudo /usr/local/bin/k3s-uninstall.sh

sleep 10

if grep -q "ID=sles" /etc/os-release || grep -q "ID=opensuse" /etc/os-release; then
    echo "SUSE OS detected. Installing k3s-selinux..."
    sudo zypper install k3s-selinux -y
else
    echo "Non-SUSE OS detected. Skipping k3s-selinux installation."
fi

curl -sfLk https://get.k3s.io | sudo sh -s -

sleep 2

sudo systemctl enable k3s
sudo systemctl start k3s

sleep 10

sudo ln -s /var/lib/rancher/k3s/bin/kubectl /usr/local/bin/kubectl
export PATH=$PATH:/usr/local/bin/k3s

mkdir -p .kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER:$USER /home/$USER/.kube/config 
sudo chmod 600 /home/$USER/.kube/config
export KUBECONFIG=/home/$USER/.kube/config
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

sudo systemctl stop rke2-server
sudo /usr/local/bin/rke2-uninstall.sh
sudo systemctl stop k3s
sudo /usr/local/bin/k3s-uninstall.sh

sleep 10

HOST=$(hostname)

#K102e4b8d2432f7a838556f3a3d6074b8a2e450ccbedf0386a05d2477a2171c4c34::server:87313f1713391a2e13ae54056fcd024d

curl -sfL https://get.rke2.io | sudo INSTALL_RKE2_VERSION=v1.31.10+rke2r1 sh -

sleep 2

sudo systemctl enable rke2-server.service
sudo systemctl start rke2-server.service

sleep 10

curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

sudo ln -s /var/lib/rancher/rke2/bin/kubectl /usr/local/bin/kubectl
export PATH=$PATH:/opt/rke2/bin

mkdir -p /home/$USER/.kube
sudo cp /etc/rancher/rke2/rke2.yaml /home/$USER/.kube/config
sudo chown $USER:$USER /home/$USER/.kube/config
sudo chmod 600 /home/$USER/.kube/config
export KUBECONFIG=/home/$USER/.kube/config
kubectl get nodes


kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.2/cert-manager.crds.yaml

helm repo add jetstack https://charts.jetstack.io
helm repo update
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version v1.17.2 

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
  --set replicas=1 \
  --set bootstrapPassword=admin \
  --version=2.12.0 --create-namespace 
  
  
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

sudo systemctl stop rke2-server.service
sudo /usr/local/bin/rke2-uninstall.sh

sleep 10

curl -sfL https://get.rke2.io | sudo INSTALL_RKE2_VERSION=v1.32.5+rke2r1 sh -

sleep 2

sudo systemctl enable rke2-server.service
sudo systemctl start rke2-server.service

sleep 10

mkdir -p .kube
sudo cp /etc/rancher/rke2/rke2.yaml .kube/config
sudo chown ubuntu:ubuntu /home/ubuntu/.kube/config
sudo chmod 600 /home/ubuntu/.kube/config
export KUBECONFIG=/home/ubuntu/.kube/config
kubectl get nodes


kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.2/cert-manager.crds.yaml

helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version v1.17.2 \
  --set crds.enabled=false


helm install rancher rancher-prime/rancher \
  --namespace cattle-system \
  --set hostname=rancher.my.org \
  --set bootstrapPassword=abc \
  --set replicas=1 \
  --version=2.11.2 --create-namespace 

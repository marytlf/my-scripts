sudo systemctl stop rke2-server.service
sudo /usr/local/bin/rke2-uninstall.sh
sudo systemctl stop k3s
sudo /usr/local/bin/k3s-uninstall.sh


sleep 5

curl -sfL https://get.rke2.io | sudo INSTALL_RKE2_VERSION=v1.30.5+rke2r1 sh -

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

sleep 5
#kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.2/cert-manager.crds.yaml

#helm install cert-manager jetstack/cert-manager \
#  --namespace cert-manager \
#  --create-namespace \
#  --version v1.17.2 \
#  --set crds.enabled=false

kubectl create ns cattle-system

kubectl -n cattle-system create secret tls tls-rancher-ingress \
  --cert=/home/ubuntu/certificates-teste/cacerts-4.crt \
  --key=/home/ubuntu/certificates-teste/private-4.key

kubectl -n cattle-system create secret generic tls-ca \
  --from-file=/home/ubuntu/certificates-teste/cacerts.pem

helm repo add rancher-prime https://charts.rancher.com/server-charts/prime
helm repo update
HOST=$(hostname)
helm upgrade --install rancher rancher-prime/rancher \
  --namespace cattle-system \
  --set hostname=${HOST}.sa-east-1.compute.internal \
  --set replicas=3 \
  --set bootstrapPassword=admin \
  --set rancherImage=stgregistry.suse.com/rancher/rancher \
  --set rancherImageTag=v2.10.5 --create-namespace \
  --version=2.10.5 \
  --set 'extraEnv[0].name=RANCHER_VERSION_TYPE' \
  --set 'extraEnv[0].value=prime' \
  --set 'extraEnv[1].name=CATTLE_BASE_UI_BRAND' \
  --set 'extraEnv[1].value=suse' \
  --set 'extraEnv[2].name=CATTLE_DEBUG' \
  --set 'extraEnv[2].value="true"' \
  --set ingress.tls.source=secret \
  --set privateCA=true 


#helm install rancher rancher-prime/rancher \
#  --namespace cattle-system \
#  --set hostname=rancher.my.org \
#  --set bootstrapPassword=abc \
#  --set replicas=1 \
#  --version=2.11.2 --create-namespace 

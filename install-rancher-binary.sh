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

curl -sfLk https://get.k3s.io | sudo INSTALL_K3S_VERSION=v1.31.10+k3s1 sh -s -
#curl -sfLk https://get.k3s.io | sudo sh -s -

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




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


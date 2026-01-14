#!/bin/sh
#
set -e

/usr/local/bin/cgroup-setup.sh


# Start k3s server in the background
/usr/local/bin/k3s server --disable-helm-controller --kubelet-arg='cgroup-driver=cgroupfs' --snapshotter=native --debug &


# Wait for k3s API server to be available
echo "Waiting for k3s to start..."

while ! /usr/local/bin/k3s kubectl get nodes; do
	echo "waiting..."
	export KUBECONFIG="/etc/rancher/k3s/k3s.yaml"

      	sleep 10
done
echo "k3s is up and running."

echo "k3s is up and running. Starting rancher...."

export KUBECONFIG="/etc/rancher/k3s/k3s.yaml"

#CATTLE_SERVER_URL="https://0.0.0.0" CATTLE_AGENT_TLS_MODE="system-store" CATTLE_BOOTSTRAP_PASSWORD="admin" CATTLE_DEV_MODE=320 /usr/local/bin/rancher-server --add-local=true --kubeconfig /etc/rancher/k3s/k3s.yaml --debug --audit-log-path /tmp/rancher-audit.log --audit-log-maxsize 100 --audit-log-maxage 10 --audit-log-maxbackup 10 --audit-level 0 --http-listen-port 8080 --https-listen-port 8443 --no-cacerts

# Now run your pull command
#sudo k3s crictl pull localhost:5000/rancher-webhook:latest

tail -f /dev/null

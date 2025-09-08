#!/bin/bash

# Check if Dockerfile exists in the current directory
if [ -f "Dockerfile_webhook" ]; then
    # If the file exists, run the docker build command
    echo "Dockerfile found! Building the image..."
    docker build -t rancher-webhook:latest -f Dockerfile_webhook .
else
    # If the file does not exist, print an error and exit
    echo "Error: Dockerfile not found in the current directory." >&2
    exit 1
fi

IS_RUNNING=$(docker ps --format "{{.Names}}" | grep registry)

if [[  $IS_RUNNING == "" ]]; then
    docker run -d -p 5000:5000 --restart=always --name registry registry:2
fi
docker tag rancher-webhook:latest localhost:5000/rancher-webhook:latest
docker push localhost:5000/rancher-webhook:latest

# Check for the k3s binary
if [ -f "/usr/local/bin/k3s" ]; then
    echo "k3s cluster detected. Pulling the image..."
    sudo /usr/local/bin/k3s crictl pull localhost:5000/rancher-webhook:latest

# Check for the rke2 binary
elif [ -f "/usr/local/bin/rke2" ]; then
    echo "rke2 cluster detected. The command is specific to k3s and will not be executed."

# If neither is found
else
    echo "Error: Neither k3s nor rke2 binary found at /usr/local/bin/. Exiting." >&2
    exit 1
fi

#docker build -t rancher-webhook:latest .
#docker run -d -p 5000:5000 --restart=always --name registry registry:2
#docker tag rancher-webhook:latest localhost:5000/rancher-webhook:latest
#docker push localhost:5000/rancher-webhook:latest
#sudo /usr/local/bin/k3s crictl pull localhost:5000/rancher-webhook:latest



#!/bin/bash

# Usage:
# ./install_rancher.sh <rancher_version> <rancher_hostname> <rancher_helm_channel> <install_method> [k8s_method] [k8s_version] [install_cert_manager] [tls_type]

# Parameters:
# $1 = rancher_version
# $2 = rancher_hostname
# $3 = rancher_helm_channel
# $4 = install_method (helm|docker|binary)
# $5 = k8s_method (k3s|rke2|k3d) - only if install_method=helm
# $6 = k8s_version - only if install_method=helm
# $7 = install_cert_manager (true|false) - only if install_method=helm
# $8 = tls_type (rancher|letsEncrypt|secret)

set -e

rancher_version="$1"
rancher_hostname="$2"
rancher_helm_channel="$3"
install_method="$4"
install_type="$5"
k8s_method="$6"
k8s_version="$7"
install_cert_manager="$8"
tls_type="$9"
n_replicas="${10}"
clean_env="${11}"
generate_cert="${12}"

env_install_cmd=""
chart_install_path="$(pwd)/build/chart/rancher"

if [[ -z "$rancher_version" || -z "$rancher_hostname" || -z "$rancher_helm_channel" || -z "$install_method" || -z "$tls_type" ]]; then
  echo "Usage:"
  echo "$0 <rancher_version> <rancher_hostname> <rancher_helm_channel> <install_method> <install_type> [k8s_method] [k8s_version] [install_cert_manager] <tls_type> [n_replicas] [clean_env] "
  echo "install_method: helm|docker|binary"
  echo "If install_method=helm, provide k8s_method, k8s_version, install_cert_manager"
  echo "tls_type: rancher|letsEncrypt|secret"
  exit 1
fi

echo "Starting Rancher installation with parameters:"
echo "Rancher Version: $rancher_version"
echo "Rancher Hostname: $rancher_hostname"
echo "Rancher Helm Channel: $rancher_helm_channel"
echo "Install Method: $install_method"
echo "Number of replicas: $n_replicas"
if [[ "$install_method" == "helm" ]]; then
  echo "K8s Method: $k8s_method"
  echo "K8s Version: $k8s_version"
  echo "Install cert-manager: $install_cert_manager"
fi
echo "TLS Type: $tls_type"

clean_environment(){
    # The || true ensures that if the command fails (returns a non-zero exit code), 
    # the 'true' command runs (which returns a zero exit code), and the script continues.
    sudo systemctl stop rke2-server 2> /dev/null || true
    sudo /usr/local/bin/rke2-uninstall.sh 2> /dev/null || true
    sudo systemctl stop k3s 2> /dev/null || true
    sudo /usr/local/bin/k3s-uninstall.sh 2> /dev/null || true
}

install_helm(){
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
}

export_kubeconfig(){
  source ~/.bashrc
  touch ~/.bash_aliases
  if [ -z "$KUBECONFIG" ]; then
      # If it's empty, set the default path
      echo "if [ -z \"\$KUBECONFIG\" ]; then
      export KUBECONFIG=/home/ubuntu/.kube/config
      fi" >> ~/.bash_aliases
      export KUBECONFIG=/home/$USER/.kube/config
  fi

  source ~/.bash_aliases
  source ~/.bashrc

}

create_k3s_config() {
  local k3s_cfg="config.yaml"

  cat > "$k3s_cfg" <<EOF
# /etc/rancher/k3s/config.yaml
write-kubeconfig-mode: "0644"
kube-apiserver-arg:
  - enable-aggregator-routing=false 
#egress-selector-mode: disabled

EOF
  sudo touch /etc/rancher/k3s/config.yaml
  sudo cp $k3s_cfg /etc/rancher/k3s/config.yaml

  echo "Created k3s config file $k3s_cfg"
}

create_rke2_config() {
  local rke2_cfg="config.yaml"

  cat > "$rke2_cfg" <<EOF
# /etc/rancher/rke2/config.yaml
api-server-args:
  - enable-aggregator-routing=false
#egress-selector-mode: disabled
EOF
  sudo mkdir -p /etc/rancher/rke2/
  sudo touch /etc/rancher/rke2/config.yaml
  sudo cp $rke2_cfg /etc/rancher/rke2/config.yaml

  echo "Created rke2 config file $rke2_cfg"
}


create_openssl_config() {
  local hostname_full
  local ip_addr
  hostname_full="$(hostname).sa-east-1.compute.internal"
  ip_addr="$(hostname -i | awk -F\  '{print $1}')"
  local openssl_cfg="openssl.cnf"

  cat > "$openssl_cfg" <<EOF
[ req ]
req_extensions = v3_req
x509_extensions = v3_ca
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn

[ dn ]
C = BR
ST = Sao Paulo
L = Sao Paulo
O = Suse
CN = $hostname_full

[ v3_req ]
subjectAltName = @alt_names

[ v3_ca ]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = CA:true
subjectAltName = @alt_names

[alt_names]
DNS.1 = $hostname_full
DNS.2 = ip-172-31-6-197
IP.1 = $ip_addr
IP.2 = 172.31.6.197
EOF

  echo "Created OpenSSL config file $openssl_cfg"
}

generate_certificates() {
  local date_str
  date_str=$(date +%Y%m%d_%H%M%S)
  local cert_dir="certificates_$date_str"

  mkdir -p "$cert_dir"
  echo "Generating certificates in $cert_dir..."

  # Generate self-signed cert and key
  openssl req -x509 -nodes -newkey rsa:4096 \
    -keyout "$cert_dir/new-rsa-private.key" \
    -out "$cert_dir/cacerts.pem" \
    -days 365 -config openssl.cnf

  # Convert private key format if needed
  openssl pkey -in "$cert_dir/new-rsa-private.key" -out "$cert_dir/private.key"

  # Convert cert to crt format
  openssl x509 -in "$cert_dir/cacerts.pem" -out "$cert_dir/cacerts.crt"

  echo "Certificates generated."
}

apply_certificates() {
  local cert_dir="$1"
  echo "Applying certificates from $cert_dir to Kubernetes..."
  kubectl -n cattle-system delete secret tls-rancher-ingress --ignore-not-found
  kubectl -n cattle-system delete secret tls-ca --ignore-not-found

  kubectl -n cattle-system create secret tls tls-rancher-ingress \
    --cert="$cert_dir/cacerts.crt" \
    --key="$cert_dir/new-rsa-private.key" \
    --dry-run=client --save-config -o yaml | kubectl apply -f -

  kubectl -n cattle-system create secret generic tls-ca \
    --from-file="$cert_dir/cacerts.pem" \
    --dry-run=client --save-config -o yaml | kubectl apply -f -

  echo "Certificates applied."
}


install_k3s(){
    if grep -q "ID=sles" /etc/os-release || grep -q "ID=opensuse" /etc/os-release; then
        echo "SUSE OS detected. Installing k3s-selinux..."
        sudo zypper install k3s-selinux -y
    else
        echo "Non-SUSE OS detected. Skipping k3s-selinux installation."
    fi

    curl -sfLk https://get.k3s.io | sudo INSTALL_K3S_VERSION=${k8s_version}+k3s1 sh -s -

    create_k3s_config

    sudo systemctl enable k3s
    sudo systemctl start k3s

    sleep 5

    sudo ln -sf /usr/local/bin/k3s /usr/local/bin/kubectl    
    #export PATH=$PATH:/usr/local/bin/k3s

    mkdir -p .kube
    sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
    sudo chown $USER:$USER /home/$USER/.kube/config
    sudo chmod 600 /home/$USER/.kube/config
    export KUBECONFIG=/home/$USER/.kube/config
    kubectl get nodes

    sleep 10
}

install_rke2(){
    curl -sfL https://get.rke2.io | sudo INSTALL_RKE2_VERSION=${k8s_version}+rke2r1 sh -

    sleep 2
    create_rke2_config

    sudo systemctl enable rke2-server.service
    sudo systemctl start rke2-server.service


    sudo ln -sf /var/lib/rancher/rke2/bin/kubectl /usr/local/bin/kubectl 
    #export PATH=$PATH:/opt/local/bin/kubectl

    mkdir -p .kube
    sudo cp /etc/rancher/rke2/rke2.yaml .kube/config
    sudo chown $USER:$USER /home/$USER/.kube/config
    sudo chmod 600 /home/$USER/.kube/config
    export KUBECONFIG=/home/$USER/.kube/config
    kubectl get nodes
    sleep 10

}


install_k3d(){
    # --- Configuration Variables ---
    VCLUSTER_NAME="rancher-vcluster"
    K3D_CLUSTER_NAME="my-host-cluster"

    # --- Step 1: Clean up previous deployments (Idempotent) ---
    echo "--- Step 1: Cleaning up any previous deployments ---"
    vcluster disconnect > /dev/null 2>&1 || true
    vcluster delete "$VCLUSTER_NAME" > /dev/null 2>&1 || true
    k3d cluster delete "$K3D_CLUSTER_NAME" > /dev/null 2>&1 || true
    echo "Clean up complete."
    echo ""

    # --- Step 2: Create the K3D Host Cluster ---
    echo "--- Step 2: Creating K3D host cluster ---"
    k3d cluster create "$K3D_CLUSTER_NAME" --image rancher/k3s:${k8s_version}-k3s1
    echo "K3D cluster created."
    echo ""

}

install_vcluster_version(){
  curl -s -L "https://github.com/loft-sh/vcluster/releases/download/v0.26.0/vcluster-linux-amd64" | sudo tee /usr/local/bin/vcluster >/dev/null && sudo chmod +x /usr/local/bin/vcluster

  install_helm
}

install_vcluster(){
  install_vcluster_version
  VCLUSTER_NAME="rancher-vcluster"
  # --- Step 1: Clean up previous deployments (Idempotent) ---
  echo "--- Step 1: Cleaning up any previous deployments ---"
  vcluster disconnect > /dev/null 2>&1 || true
  vcluster delete "$VCLUSTER_NAME" > /dev/null 2>&1 || true

  vcluster create "$VCLUSTER_NAME" --chart-version v0.26.1 --expose=true 
}

choose_k8s_install_method() {
  # Example: Setup Kubernetes cluster based on k8s_method (simplified)
    case "$k8s_method" in
      k3s)
        echo "Setting up k3s cluster version $k8s_version..."
        # Add your k3s setup commands here
        install_k3s
        install_helm
        ;;
      rke2)
        echo "Setting up rke2 cluster version $k8s_version..."
        # Add your rke2 setup commands here
        install_rke2
        install_helm
        ;;
      k3d)
        echo "Setting up k3d cluster version $k8s_version..."
        # Add your k3d setup commands here
        install_k3d
        install_helm
        ;;
      vcluster)
        echo "Setting up vcluster cluster version $k8s_version..."
        install_rke2 # This sets up the host cluster
        install_helm
        
        # --- Add Robust Host Cluster Readiness Check Here ---
        echo "Waiting for host cluster (RKE2) to be ready (up to 5 minutes)..."
        # 1. Wait for all Kubernetes nodes in the host cluster to be in the Ready state
        kubectl wait --for=condition=Ready node --all --timeout=300s
        # 2. Wait for a core deployment (like CoreDNS) in the host cluster to be available
        #kubectl wait --for=condition=available deployment/coredns -n kube-system --timeout=300s
        echo "Host cluster ready. Proceeding with vcluster creation."
        # ---------------------------------------------------

        install_vcluster # Now executes after a guaranteed ready state
        ;;
      *)
        echo "Unsupported k8s_method: $k8s_method"
        exit 1
        ;;
    esac
}

validate_rancher_channel(){
    case "$rancher_helm_channel" in
        stable)
          echo "Setting up rancher chart channel $rancher_helm_channel..."
          helm repo add rancher-stable https://releases.rancher.com/server-charts/stable
          ;;
        latest)
          echo "Setting up rancher chart channel $rancher_helm_channel..."
          helm repo add rancher-latest https://releases.rancher.com/server-charts/latest
          ;;
        alpha)
          echo "Setting up rancher chart channel $rancher_helm_channel..."
          helm repo add rancher-stable https://releases.rancher.com/server-charts/alpha
          ;;
        prime)
          echo "Setting up rancher chart channel $rancher_helm_channel..."
          helm repo add rancher-prime https://charts.rancher.com/server-charts/prime
          env_install_cmd='--set rancherImage=stgregistry.suse.com/rancher/rancher \
                          --set "extraEnv[0].name=RANCHER_VERSION_TYPE" \
                          --set "extraEnv[0].value=prime" \
                          --set "extraEnv[1].name=CATTLE_BASE_UI_BRAND" \
                          --set "extraEnv[1].value=suse" \
                          --set "extraEnv[2].name=CATTLE_DEBUG" \
                          --set "extraEnv[2].value=\"true\""'
          ;;
        local)
          echo "Setting up rancher chart channel $rancher_helm_channel..."
          echo "chart placed on: $chart_install_path"
          ;;
        *)
          echo "Unsupported rancher_helm_channel: $rancher_helm_channel"

          exit 1
          ;;
      esac
      helm repo update
}

install_rancher(){
    if [[ $clean_env == "true" ]]; then
      clean_environment
    fi

    if [[ "$install_method" == "helm" ]]; then
      # Validate required helm params
      if [[ -z "$k8s_method" || -z "$k8s_version" || -z "$install_cert_manager" ]]; then
        echo "For helm installation, k8s_method, k8s_version and install_cert_manager must be provided."
        exit 1
      fi

      echo "Installing Rancher via Helm..."
      choose_k8s_install_method
      
      kubectl create ns cattle-system 

      # Install cert-manager if requested
      if [[ "$install_cert_manager" == "true" ]]; then
        echo "Installing cert-manager..."
        kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.2/cert-manager.crds.yaml

        helm repo add jetstack https://charts.jetstack.io
        helm repo update
        helm install cert-manager jetstack/cert-manager \
          --namespace cert-manager \
          --create-namespace \
          --version v1.17.2 \
          --set crds.enabled=false
        sleep 5   
      else
        if [[ "$generate_cert" == "true" ]]; then 
          echo "Cert-manager not requested, generating self-signed certificates..."

          create_openssl_config
          generate_certificates

          # Pass the generated cert folder to apply_certificates
          # The folder name is certificates_<date>, get the latest one:
          latest_cert_dir=$(ls -td certificates_* | head -1)
          apply_certificates "$latest_cert_dir"  
        fi      
      fi

      # Add Rancher Helm repo and update
      #helm repo add rancher-latest https://releases.rancher.com/server-charts/latest
      #helm repo update
      validate_rancher_channel
      
      if [[ "$rancher_helm_channel" != "local" ]]; then
        # Prepare Helm install command
        helm_install_cmd="helm install rancher rancher-${rancher_helm_channel}/rancher \
          --namespace cattle-system --create-namespace \
          --set hostname=$rancher_hostname \
          --set bootstrapPassword=admin \
          --set replicas=$n_replicas \
          ${env_install_cmd} \
          --set rancherImageTag=$rancher_version \
          --version=$rancher_version"
      else
        # Prepare Helm install command for build chart local
        helm_install_cmd="helm install rancher ${chart_install_path} \
          --namespace cattle-system --create-namespace \
          --set hostname=$rancher_hostname \
          --set bootstrapPassword=admin \
          --set replicas=$n_replicas \
          ${env_install_cmd} \
          --set rancherImageTag=$rancher_version"
      fi

      # TLS options
      case "$tls_type" in
        rancher)
          echo "Using Rancher default TLS"
          # No extra flags needed
          ;;
        letsEncrypt)
          echo "Using Let's Encrypt TLS"
          helm_install_cmd+=" --set ingress.tls.source=letsEncrypt"
          ;;
        secret)
          echo "Using TLS from secret, enabling privateCA"
          helm_install_cmd+=" --set ingress.tls.source=secret --set privateCA=true"
          ;;
        *)
          echo "Unsupported TLS type: $tls_type"
          exit 1
          ;;
      esac

      echo "Running Helm install command:"
      echo "$helm_install_cmd"
      eval "$helm_install_cmd"

      export_kubeconfig

    elif [[ "$install_method" == "docker" ]]; then
      echo "Installing Rancher via Docker..."


      docker_run_cmd="docker run -d --restart=unless-stopped -p 80:80 -p 443:443 \
        --name rancher-server \
        rancher/rancher:$rancher_version"

      echo "Running Docker command:"
      echo "$docker_run_cmd"
      eval "$docker_run_cmd"

    elif [[ "$install_method" == "binary" ]]; then
      echo "Installing Rancher via Binary..."

      # Example placeholder for binary installation steps
      echo "Downloading Rancher binary version $rancher_version..."
      # Add your binary download and install commands here

    else
      echo "Unsupported install method: $install_method"
      exit 1
    fi

    echo "Rancher installation script completed."
}

update_rancher(){
    # Install cert-manager if requested
    if [[ "$install_cert_manager" == "false" && "$generate_cert" == "true" ]]; then
      echo "Cert-manager not requested, generating self-signed certificates..."

      create_openssl_config
      generate_certificates

      # Pass the generated cert folder to apply_certificates
      # The folder name is certificates_<date>, get the latest one:
      latest_cert_dir=$(ls -td certificates_* | head -1)
      apply_certificates "$latest_cert_dir"        
    fi

    # Add Rancher Helm repo and update
    #helm repo add rancher-latest https://releases.rancher.com/server-charts/latest
    #helm repo update
    validate_rancher_channel
    
    # Prepare Helm install command
    helm_install_cmd="helm upgrade --install rancher rancher-${rancher_helm_channel}/rancher \
      --namespace cattle-system \
      --set bootstrapPassword=admin \
      --set hostname=$rancher_hostname \
      --set replicas=$n_replicas \
      ${env_install_cmd} \
      --set rancherImageTag=$rancher_version"


    # TLS options
    case "$tls_type" in
      rancher)
        echo "Using Rancher default TLS"
        # No extra flags needed
        ;;
      letsEncrypt)
        echo "Using Let's Encrypt TLS"
        helm_install_cmd+=" --set ingress.tls.source=letsEncrypt"
        ;;
      secret)
        echo "Using TLS from secret, enabling privateCA"
        helm_install_cmd+=" --set ingress.tls.source=secret --set privateCA=true"
        ;;
      *)
        echo "Unsupported TLS type: $tls_type"
        exit 1
        ;;
    esac

    echo "Running Helm install command:"
    echo "$helm_install_cmd"
    eval "$helm_install_cmd"

}

uninstall_rancher(){
  helm uninstall rancher -n cattle-system
}

case "$install_type" in
  install)
    echo "Installing rancher..."
    install_rancher
  ;;
  update) 
    echo "Updating rancher..."
    update_rancher
  ;;
  remove)
    echo "Uninstalling rancher..."
    uninstall_rancher
    ;;
  *)
    echo "Unsuported installation type: $install_type"
    exit 1
    ;;
esac 


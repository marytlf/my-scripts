#!/usr/bin/env python3

import subprocess
import os
from datetime import datetime


def create_incremental_path(base_path):
    """
    Creates a unique path by appending an incremental number.
    e.g., 'file.txt', 'file_1.txt', 'file_2.txt'
    """
    if not os.path.exists(base_path):
        return base_path

    name, ext = os.path.splitext(base_path)
    counter = 1
    while True:
        new_path = f"{name}_{counter}{ext}"
        if not os.path.exists(new_path):
            return new_path
        counter += 1



def run_cmd(cmd):
    """Run shell command and return output."""
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(f"Error running command: {cmd}\n{result.stderr}")
        return None
    return result.stdout.strip()

def get_node_name():
    # Try to get node name from environment or hostname
    # If running inside a pod, NODE_NAME env var might be set
    node_name = os.environ.get("NODE_NAME")
    if node_name:
        return node_name
    # fallback to hostname
    hostname = run_cmd("hostname")
    if hostname:
        return hostname
    return "unknown-node"

def get_all_namespaces():
    output = run_cmd("kubectl get namespaces -o jsonpath='{.items[*].metadata.name}'")
    if output:
        return output.strip("'").split()
    return []

def get_pods(namespace):
    output = run_cmd(f"kubectl get pods -n {namespace} -o jsonpath='{{.items[*].metadata.name}}'")
    if output:
        return output.split()
    return []

def save_kubectl_top(base_dir):
    top_dir = os.path.join(base_dir, "kubectl_top")
    os.makedirs(top_dir, exist_ok=True)

    print("Gathering 'kubectl top nodes'...")
    top_nodes = run_cmd("kubectl top nodes")
    if top_nodes:
        with open(os.path.join(top_dir, "top_nodes.txt"), "w") as f:
            f.write(top_nodes)

    print("Gathering 'kubectl top pods --all-namespaces'...")
    top_pods = run_cmd("kubectl top pods --all-namespaces")
    if top_pods:
        with open(os.path.join(top_dir, "top_pods_all_namespaces.txt"), "w") as f:
            f.write(top_pods)

def save_k8s_versions(base_dir):
    version_dir = os.path.join(base_dir, "versions")
    os.makedirs(version_dir, exist_ok=True)

    print("Gathering Kubernetes version info...")
    version_info = run_cmd("kubectl version --short")
    if version_info:
        with open(os.path.join(version_dir, "kubectl_version.txt"), "w") as f:
            f.write(version_info)

def save_cluster_events(base_dir):
    events_dir = os.path.join(base_dir, "events")
    os.makedirs(events_dir, exist_ok=True)

    print("Gathering cluster events (last 1000)...")
    events = run_cmd("kubectl get events --all-namespaces --sort-by='.metadata.creationTimestamp' -o wide")
    if events:
        with open(os.path.join(events_dir, "cluster_events.txt"), "w") as f:
            f.write(events)

def save_network_policies(base_dir, namespaces):
    np_dir = os.path.join(base_dir, "network_policies")
    os.makedirs(np_dir, exist_ok=True)

    for ns in namespaces:
        names = get_resource_names("networkpolicies", ns)
        for name in names:
            save_describe("networkpolicy", name, ns, base_dir)

def save_storage_info(base_dir, namespaces):
    # PVs are cluster-wide
    pvs = get_resource_names("persistentvolumes")
    for pv in pvs:
        save_describe("persistentvolume", pv, None, base_dir)

    # PVCs per namespace
    for ns in namespaces:
        pvcs = get_resource_names("persistentvolumeclaims", ns)
        for pvc in pvcs:
            save_describe("persistentvolumeclaim", pvc, ns, base_dir)

def save_rbac_info(base_dir, namespaces):
    rbac_resources = [
        ("roles", True),
        ("rolebindings", True),
        ("clusterroles", False),
        ("clusterrolebindings", False),
    ]

    for res, namespaced in rbac_resources:
        if namespaced:
            for ns in namespaces:
                names = get_resource_names(res, ns)
                for name in names:
                    save_describe(res, name, ns, base_dir)
        else:
            names = get_resource_names(res)
            for name in names:
                save_describe(res, name, None, base_dir)

def save_ingress_classes(base_dir):
    ingress_classes = get_resource_names("ingressclasses")
    for ic in ingress_classes:
        save_describe("ingressclass", ic, None, base_dir)

def save_logs(namespace, pod, date_str, base_dir):
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    filename = f"{namespace}_{pod}_{date_str}.log"
    filepath = os.path.join(logs_dir, filename)
    print(f"Getting logs for pod {pod} in namespace {namespace}...")
    logs = run_cmd(f"kubectl logs -n {namespace} {pod}")
    if logs is not None:
        with open(filepath, "w") as f:
            f.write(logs)

def save_describe(resource_type, name, namespace, base_dir):
    desc_dir = os.path.join(base_dir, "describes", resource_type)
    os.makedirs(desc_dir, exist_ok=True)
    if namespace:
        filename = f"{namespace}_{name}.txt"
        describe_cmd = f"kubectl describe {resource_type} {name} -n {namespace}"
        yaml_cmd = f"kubectl get {resource_type} {name} -n {namespace} -o yaml"
    else:
        filename = f"{name}.txt"
        describe_cmd = f"kubectl describe {resource_type} {name}"
        yaml_cmd = f"kubectl get {resource_type} {name} -o yaml"
    filepath = os.path.join(desc_dir, filename)
    print(f"Describing {resource_type} {name} in namespace {namespace or 'cluster-wide'}...")
    describe_output = run_cmd(describe_cmd)
    yaml_output = run_cmd(yaml_cmd)
    if describe_output is None and yaml_output is None:
        print(f"Failed to get describe and yaml for {resource_type} {name}")
        return
    with open(filepath, "w") as f:
        if describe_output:
            f.write("--- DESCRIBE OUTPUT ---\n")
            f.write(describe_output)
            f.write("\n\n")
        else:
            f.write("--- DESCRIBE OUTPUT ---\n<No output>\n\n")
        if yaml_output:
            f.write("--- YAML OUTPUT ---\n")
            f.write(yaml_output)
            f.write("\n")
        else:
            f.write("--- YAML OUTPUT ---\n<No output>\n")

def save_describe_2(resource_type, name, namespace, base_dir):
    desc_dir = os.path.join(base_dir, "describes", resource_type)
    os.makedirs(desc_dir, exist_ok=True)
    if namespace:
        filename = f"{namespace}_{name}.txt"
        cmd = f"kubectl describe {resource_type} {name} -n {namespace}"
    else:
        filename = f"{name}.txt"
        cmd = f"kubectl describe {resource_type} {name}"
    filepath = os.path.join(desc_dir, filename)
    print(f"Describing {resource_type} {name} in namespace {namespace or 'cluster-wide'}...")
    desc = run_cmd(cmd)
    if desc is not None:
        with open(filepath, "w") as f:
            f.write(desc)

def get_resource_names(resource_type, namespace=None):
    if namespace:
        cmd = f"kubectl get {resource_type} -n {namespace} -o jsonpath='{{.items[*].metadata.name}}'"
    else:
        cmd = f"kubectl get {resource_type} -o jsonpath='{{.items[*].metadata.name}}'"
    output = run_cmd(cmd)
    if output:
        return output.split()
    return []

def save_os_info(base_dir):
    os_dir = os.path.join(base_dir, "os_info")
    os.makedirs(os_dir, exist_ok=True)

    # CPU usage (top 1 snapshot)
    cpu_file = os.path.join(os_dir, "cpu_usage.txt")
    print("Gathering CPU usage info...")
    cpu_info = run_cmd("top -bn1 | head -20")
    if cpu_info:
        with open(cpu_file, "w") as f:
            f.write(cpu_info)

    # Memory usage
    mem_file = os.path.join(os_dir, "memory_usage.txt")
    print("Gathering memory usage info...")
    mem_info = run_cmd("free -h")
    if mem_info:
        with open(mem_file, "w") as f:
            f.write(mem_info)

    # Disk space usage
    disk_file = os.path.join(os_dir, "disk_usage.txt")
    print("Gathering disk usage info...")
    disk_info = run_cmd("df -h")
    if disk_info:
        with open(disk_file, "w") as f:
            f.write(disk_info)

    # Network dropped packets
    net_file = os.path.join(os_dir, "network_drops.txt")
    print("Gathering network dropped packets info...")
    net_info = get_network_drops()
    if net_info:
        with open(net_file, "w") as f:
            f.write(net_info)

def get_network_drops():
    # Parse /proc/net/dev for dropped packets per interface
    try:
        with open("/proc/net/dev", "r") as f:
            lines = f.readlines()
    except Exception as e:
        return f"Error reading /proc/net/dev: {e}"

    result_lines = ["Interface  RX_dropped  TX_dropped"]
    for line in lines[2:]:
        parts = line.strip().split()
        if len(parts) < 17:
            continue
        iface = parts[0].strip(":")
        rx_drop = parts[3]
        tx_drop = parts[11]
        result_lines.append(f"{iface:10} {rx_drop:10} {tx_drop:10}")

    return "\n".join(result_lines)

def save_nodes_describe(base_dir):
    nodes_dir = os.path.join(base_dir, "describes", "nodes")
    os.makedirs(nodes_dir, exist_ok=True)
    print("Describing all nodes...")
    nodes = get_resource_names("nodes")
    for node in nodes:
        filepath = os.path.join(nodes_dir, f"{node}.txt")
        desc = run_cmd(f"kubectl describe node {node}")
        if desc:
            with open(filepath, "w") as f:
                f.write(desc)
def save_k8s_system_logs(base_dir):
    syslog_dir = os.path.join(base_dir, "k8s_system_logs")
    os.makedirs(syslog_dir, exist_ok=True)

    # List of systemd units to try
    systemd_units = [
        "k3s",
        "rke2-server",
        "rke2-agent",
        "kubelet",
        "kube-apiserver",
        "kube-controller-manager",
        "kube-scheduler",
    ]

    print("Gathering Kubernetes system logs from systemd units...")
    for unit in systemd_units:
        log_file = os.path.join(syslog_dir, f"{unit}.log")
        logs = run_cmd(f"journalctl -u {unit} --no-pager -n 1000")  # last 1000 lines
        if logs:
            print(f"Saving logs for systemd unit: {unit}")
            with open(log_file, "w") as f:
                f.write(logs)
        else:
            # No logs or unit not found, skip silently
            pass

    # Check for common log files and save if exist
    common_log_files = [
        "/var/log/k3s.log",
        "/var/log/rke2.log",
        "/var/log/kubelet.log",
        "/var/log/kube-apiserver.log",
        "/var/log/kube-controller-manager.log",
        "/var/log/kube-scheduler.log",
    ]

    print("Checking common Kubernetes log files...")
    for filepath in common_log_files:
        if os.path.isfile(filepath):
            dest_file = os.path.join(syslog_dir, os.path.basename(filepath))
            print(f"Copying log file: {filepath}")
            try:
                with open(filepath, "r") as src, open(dest_file, "w") as dst:
                    dst.write(src.read())
            except Exception as e:
                print(f"Failed to copy {filepath}: {e}")

def save_helm_list(base_dir):
    helm_dir = os.path.join(base_dir, "helm_releases")
    os.makedirs(helm_dir, exist_ok=True)
    helm_file = os.path.join(helm_dir, "helm_list_all_namespaces.txt")
    print("Gathering Helm releases list (all namespaces)...")
    helm_output = run_cmd("helm list -A")
    if helm_output:
        with open(helm_file, "w") as f:
            f.write(helm_output)
    else:
        print("No Helm releases found or helm command failed.")

def main():
    date_str = datetime.now().strftime("%Y-%m-%d")
    node_name = get_node_name()

    base_dir_name = f"k8s_backup_{node_name}_{date_str}"
    base_dir = create_incremental_path(base_dir_name)
    os.makedirs(base_dir, exist_ok=True)

    namespaces = get_all_namespaces()
    if not namespaces:
        print("No namespaces found or error fetching namespaces.")
        return

    # Get logs for all pods in all namespaces
    for ns in namespaces:
        pods = get_pods(ns)
        for pod in pods:
            save_logs(ns, pod, date_str, base_dir)

    # Resources to describe cluster-wide (no namespace)
    cluster_resources = ["apiservices"]
    for res in cluster_resources:
        names = get_resource_names(res)
        for name in names:
            save_describe(res, name, None, base_dir)

    # Resources to describe per namespace
    namespaced_resources = [
        "pods",
        "deployments",
        "statefulsets",
        "replicasets",
        "services",
        "endpoints",
        "ingress",
    ]

    for ns in namespaces:
        for res in namespaced_resources:
            names = get_resource_names(res, ns)
            for name in names:
                save_describe(res, name, ns, base_dir)

    # Handle CRDs cluster-wide (they are cluster scoped)
    crds = get_resource_names("customresourcedefinitions")
    for crd in crds:
        save_describe("customresourcedefinitions", crd, None, base_dir)

    # Save OS info
    save_os_info(base_dir)

    # Save nodes describe
    save_nodes_describe(base_dir)

    # Save Kubernetes system logs
    save_k8s_system_logs(base_dir)

    # Save Helm releases list
    save_helm_list(base_dir)

    # Save kubectl top info
    save_kubectl_top(base_dir)

    # Save Kubernetes versions
    save_k8s_versions(base_dir)
    
    # Save cluster events
    save_cluster_events(base_dir)
    
    # Save network policies
    save_network_policies(base_dir, namespaces)
    
    # Save storage info
    save_storage_info(base_dir, namespaces)
    
    # Save RBAC info
    save_rbac_info(base_dir, namespaces)
    
    # Save ingress classes
    save_ingress_classes(base_dir)
    
    print(f"Backup completed in folder: {base_dir}")

if __name__ == "__main__":
    main()

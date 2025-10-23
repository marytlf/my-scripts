#!/usr/bin/env python3

import subprocess
import os
import time
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
    """Run shell command and return output. Local execution only."""
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


def get_current_node():
    """Get the current node name (for single-node execution)."""
    return [get_node_name()]


def get_nodes_with_ips():
    """Get list of (node_name, internal_ip) pairs from 'kubectl get nodes -o wide'."""
    output = run_cmd("kubectl get nodes -o wide")
    if not output:
        return []

    lines = output.split('\n')
    node_ips = []
    for line in lines[1:]:  # Skip header
        if line.strip():
            parts = line.split()
            if len(parts) >= 6:
                name = parts[0]
                internal_ip = parts[5]  # INTERNAL-IP is the 6th column (0-based index 5)
                if internal_ip and internal_ip != '<none>':  # Skip if no IP
                    node_ips.append((name, internal_ip))
                else:
                    print(f"Warning: No internal IP found for node {name}")
    return node_ips


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


def save_pods_wide(base_dir, namespaces):
    """
    Save 'kubectl get pods -o wide' output for each namespace.
    """
    pods_wide_dir = os.path.join(base_dir, "pods_wide")
    os.makedirs(pods_wide_dir, exist_ok=True)

    for ns in namespaces:
        print(f"Gathering 'kubectl get pods -o wide' for namespace {ns}...")
        cmd = f"kubectl get pods -n {ns} -o wide"
        output = run_cmd(cmd)
        if output:
            filename = f"{ns}_pods_wide.txt"
            filepath = os.path.join(pods_wide_dir, filename)
            with open(filepath, "w") as f:
                f.write(output)


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

    print("Gathering cluster events from all namespaces (last 1000 most recent)...")
    # Use --sort-by='.lastTimestamp' to sort by last update time (ascending: oldest first)
    # Then tail -1000 to get the most recent 1000 events (approximate, includes header if present)
    # This covers all namespaces with --all-namespaces and should capture recent cluster-wide activity
    # Note: Kubernetes events are namespaced but --all-namespaces aggregates them; node-level events may appear under relevant namespaces like kube-system
    events_cmd = "kubectl get events --all-namespaces --sort-by='.lastTimestamp' -o wide | tail -1000"
    events = run_cmd(events_cmd)
    if events:
        with open(os.path.join(events_dir, "cluster_events.txt"), "w") as f:
            f.write(events)
    else:
        print("No events found or command failed.")


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
    """Save OS info locally (single-node execution)."""
    os_dir = os.path.join(base_dir, "os_info")
    os.makedirs(os_dir, exist_ok=True)

    node = get_node_name()
    print(f"Gathering OS info for node {node}...")

    # CPU usage (top 1 snapshot)
    cpu_file = os.path.join(os_dir, "cpu_usage.txt")
    cpu_info = run_cmd("top -bn1 | head -20")
    if cpu_info:
        with open(cpu_file, "w") as f:
            f.write(f"--- Node: {node} ---\n")
            f.write(cpu_info)

    # Memory usage
    mem_file = os.path.join(os_dir, "memory_usage.txt")
    mem_info = run_cmd("free -h")
    if mem_info:
        with open(mem_file, "w") as f:
            f.write(f"--- Node: {node} ---\n")
            f.write(mem_info)

    # Disk space usage
    disk_file = os.path.join(os_dir, "disk_usage.txt")
    disk_info = run_cmd("df -h")
    if disk_info:
        with open(disk_file, "w") as f:
            f.write(f"--- Node: {node} ---\n")
            f.write(disk_info)

    # Network dropped packets (custom parse)
    net_file = os.path.join(os_dir, "network_drops.txt")
    net_info = get_network_drops_local()
    if net_info:
        with open(net_file, "w") as f:
            f.write(f"--- Node: {node} ---\n")
            f.write(net_info)

    # Kernel logs (dmesg)
    dmesg_file = os.path.join(os_dir, "kernel_dmesg.txt")
    dmesg_info = run_cmd("dmesg -T")  # Human-readable timestamps
    if dmesg_info:
        with open(dmesg_file, "w") as f:
            f.write(f"--- Node: {node} ---\n")
            f.write(dmesg_info)


def get_network_drops_local():
    # Local version of network drops parsing
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
    nodes = get_all_nodes()
    for node in nodes:
        filepath = os.path.join(nodes_dir, f"{node}.txt")
        desc = run_cmd(f"kubectl describe node {node}")
        if desc:
            with open(filepath, "w") as f:
                f.write(desc)


def save_k8s_system_logs(base_dir):
    """Save K8s system logs locally (single-node execution)."""
    syslog_dir = os.path.join(base_dir, "k8s_system_logs")
    os.makedirs(syslog_dir, exist_ok=True)

    node = get_node_name()
    node_syslog_dir = os.path.join(syslog_dir, node)
    os.makedirs(node_syslog_dir, exist_ok=True)

    print(f"Gathering K8s system logs for node {node}...")

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

    # Systemd units logs
    for unit in systemd_units:
        log_file = os.path.join(node_syslog_dir, f"{unit}.log")
        logs_cmd = f"journalctl -u {unit} --no-pager -n 1000"  # last 1000 lines
        logs = run_cmd(logs_cmd)
        if logs:
            print(f"Saving logs for systemd unit: {unit} on {node}")
            with open(log_file, "w") as f:
                f.write(f"--- Node: {node} ---\n")
                f.write(logs)

    # Common log files
    common_log_files = [
        "/var/log/k3s.log",
        "/var/log/rke2.log",
        "/var/log/kubelet.log",
        "/var/log/kube-apiserver.log",
        "/var/log/kube-controller-manager.log",
        "/var/log/kube-scheduler.log",
        "/var/log/messages",
    ]

    for filepath in common_log_files:
        dest_file = os.path.join(node_syslog_dir, os.path.basename(filepath))
        if os.path.isfile(filepath):
            try:
                with open(filepath, "r") as src:
                    content = src.read()
                with open(dest_file, "w") as dst:
                    dst.write(f"--- Node: {node} ---\n")
                    dst.write(content)
                print(f"Copied local log file: {filepath}")
            except Exception as e:
                print(f"Failed to read {filepath}: {e}")

def save_node_port_scans(base_dir, node_ips):
    """
    For each node's internal IP, launch a temporary netshoot pod and run nmap -p 1-65535 on the IP.
    If more than 3 nodes, scan only the first node to avoid overload.
    Saves output to node_port_scans/<node>_<ip>_ports.txt.
    """
    scans_dir = os.path.join(base_dir, "node_port_scans")
    os.makedirs(scans_dir, exist_ok=True)
    
    # Limit to first node if more than 3 nodes
    if len(node_ips) > 3:
        original_count = len(node_ips)
        node_ips = node_ips[:1]  # Only first node
        first_node = node_ips[0][0]
        print(f"More than 3 nodes detected ({original_count}); scanning only the first node: {first_node} to avoid overload.")
    
    print("Starting node port scans using temporary netshoot pods...")
    for node, ip in node_ips:
        print(f"Scanning ports on node {node} (IP: {ip})...")
        filename = f"{node}_{ip}_ports.txt"
        filepath = os.path.join(scans_dir, filename)
        # Run nmap non-interactively in a temporary pod
        # --rm: auto-delete pod after completion
        # -i: stdin (not needed but for compatibility)
        # --restart=Never: run as a job, not daemon
        # --: separator for command args
        # Note: Pod name uses sanitized version if needed (from previous fixes)
        sanitized_node = node.replace('.', '-')  # Simple sanitization for pod name
        pod_name = f"net-test-{sanitized_node}"
        nmap_cmd = (
            f"kubectl run {pod_name} --image=nicolaka/netshoot --rm -i --restart=Never "
            f"-- nmap -p 1-65535 {ip} --open -sT -T4"  # -sT: TCP connect scan, -T4: faster timing
        )
        nmap_output = run_cmd(nmap_cmd)
        if nmap_output:
            with open(filepath, "w") as f:
                f.write(f"--- Node: {node} (IP: {ip}) ---\n")
                f.write(f"Scan command: nmap -p 1-65535 {ip} --open -sT -T4\n")
                f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(nmap_output)
            print(f"Saved port scan for {node} to {filepath}")
        else:
            print(f"Failed to scan ports for {node} (IP: {ip}) - check kubectl permissions or network.")
            # Save error note
            with open(filepath, "w") as f:
                f.write(f"--- Node: {node} (IP: {ip}) ---\n")
                f.write("Scan failed - no output captured.\n")


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


def save_detailed_system_info(base_dir):
    """Save detailed system information locally (single-node execution).
    Runs various commands and saves outputs to files in detailed_system_info/.
    Filenames match command names (e.g., etchosts.txt, dfh.txt).
    """
    info_dir = os.path.join(base_dir, "detailed_system_info")
    os.makedirs(info_dir, exist_ok=True)

    node = get_node_name()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Gathering detailed system info for node {node}...")

    # General System Commands
    system_commands = {
        "etchosts": "cat /etc/hosts",
        "etcresolvconf": "cat /etc/resolv.conf",
        "hostname": "hostname",
        "hostnamefqdn": "hostname -f",
        "date": "date",
        "freem": "free -m",
        "uptime": "uptime",
        "dmesg": "dmesg",
        "dfh": "df -h",
        "dfi": "df -i",
        "lsmod": "lsmod",
        "mount": "mount",
        "ps": "ps aux",
        "vmstat": "vmstat 1 5",  # 5 samples, 1s interval
        "top": "top -bn1",
        "cpuinfo": "cat /proc/cpuinfo",
        "ulimit-hard": "ulimit -a",  # All limits (hard/soft)
        "file-nr": "cat /proc/sys/fs/file-nr",
        "file-max": "cat /proc/sys/fs/file-max",
        "uname": "uname -a",
        "osrelease": "cat /etc/os-release",
        "lsblk": "lsblk",
        "lsof": "lsof",
        "sysctla": "sysctl -a",
        "systemd-units": "systemctl list-units --type=service",
        "systemd-unit-files": "systemctl list-unit-files --type=service",
        "service-statusall": "service --status-all",
    }

    # Network Commands
    network_commands = {
        "iptablessave": "iptables-save",
        "ip6tablessave": "ip6tables-save",
        "iptablesmangle": "iptables -t mangle -L -n -v",
        "iptablesnat": "iptables -t nat -L -n -v",
        "iptables": "iptables -L -n -v",
        "ip6tablesmangle": "ip6tables -t mangle -L -n -v",
        "ip6tablesnat": "ip6tables -t nat -L -n -v",
        "nft_ruleset": "nft list ruleset",
        "ipaddrshow": "ip addr show",
        "iproute": "ip route show",
        "ipneighbour": "ip neigh show",
        "iprule": "ip rule show",
        "ipv6neighbour": "ip -6 neigh show",
        "iplinkshow": "ip link show",
        "ipv6rule": "ip -6 rule show",
        "ipv6route": "ip -6 route show",
        "ipv6addrshow": "ip -6 addr show",
        "ssanp": "ss -anp",
        "ssitan": "ss -itan",
        "ssuapn": "ss -uapn",
        "sswapn": "ss -wapn",
        "ssxapn": "ss -xapn",
        "ss4apn": "ss -4apn",
        "ss6apn": "ss -6apn",
        "sstunlp6": "ss -tunlp6",
        "sstunlp4": "ss -tunlp4",
        "cni": "ls -l /opt/cni/bin/",  # CNI binaries dir (adjust path if needed)
    }

    all_commands = {**system_commands, **network_commands}

    for filename, cmd in all_commands.items():
        filepath = os.path.join(info_dir, f"{filename}.txt")
        output = run_cmd(cmd)
        if output:
            with open(filepath, "w") as f:
                f.write(f"--- Node: {node} (Timestamp: {timestamp}) ---\n")
                f.write(f"Command: {cmd}\n\n")
                f.write(output)
            print(f"Saved {filename} to {filepath}")
        else:
            print(f"Failed to run {cmd} for {filename}")
            with open(filepath, "w") as f:
                f.write(f"--- Node: {node} (Timestamp: {timestamp}) ---\n")
                f.write(f"Command failed: {cmd}\n")
                f.write("No output captured.\n")

    print(f"Detailed system info saved to {info_dir}")


def get_current_node():
    """Get the current node name (for single-node execution)."""
    return [get_node_name()]

def get_all_nodes():
    """Get list of all node names in the cluster."""
    output = run_cmd("kubectl get nodes -o jsonpath='{.items[*].metadata.name}'")
    if output:
        return output.split()
    return []


def save_nodes_describe(base_dir):
    nodes_dir = os.path.join(base_dir, "describes", "nodes")
    os.makedirs(nodes_dir, exist_ok=True)
    print("Describing all nodes...")
    nodes = get_all_nodes()
    if not nodes:
        print("No nodes found or error fetching nodes.")
        return
    for node in nodes:
        filepath = os.path.join(nodes_dir, f"{node}.txt")
        desc = run_cmd(f"kubectl describe node {node}")
        if desc:
            with open(filepath, "w") as f:
                f.write(desc)
        else:
            print(f"Failed to describe node {node}.")
            # Save empty file with note
            with open(filepath, "w") as f:
                f.write(f"--- Failed to describe node {node} ---\nNo output captured.\n")
def save_machines(base_dir):
    """Save details for all machines (cluster-wide)."""
    machines_dir = os.path.join(base_dir, "machines")
    os.makedirs(machines_dir, exist_ok=True)
    print("Gathering machines info...")
    names = get_resource_names("machines")
    if not names:
        print("No machines found or error fetching machines.")
        return
    for name in names:
        save_describe("machine", name, None, base_dir)  # Assuming cluster-wide; adjust if namespaced


def save_machinesets(base_dir):
    """Save details for all machinesets (in openshift-machine-api namespace)."""
    machinesets_dir = os.path.join(base_dir, "machinesets")
    os.makedirs(machinesets_dir, exist_ok=True)
    namespace = "fleet-default"  # Adjust if different
    print(f"Gathering machinesets info in namespace {namespace}...")
    names = get_resource_names("machinesets", namespace)
    if not names:
        print(f"No machinesets found in namespace {namespace}.")
        return
    for name in names:
        save_describe("machineset", name, namespace, base_dir)


def save_machinedeployments(base_dir):
    """Save details for all machinedeployments (in openshift-machine-api namespace)."""
    machinedeployments_dir = os.path.join(base_dir, "machinedeployments")
    os.makedirs(machinedeployments_dir, exist_ok=True)
    namespace = "fleet-default"  # Adjust if different
    print(f"Gathering machinedeployments info in namespace {namespace}...")
    names = get_resource_names("machinedeployments", namespace)
    if not names:
        print(f"No machinedeployments found in namespace {namespace}.")
        return
    for name in names:
        save_describe("machinedeployment", name, namespace, base_dir)

def save_helm_values(base_dir):
    """Save Helm values for each release from 'helm list -A'."""
    values_dir = os.path.join(base_dir, "helm_values")
    os.makedirs(values_dir, exist_ok=True)
    
    print("Gathering Helm values for each release...")
    
    # Get the helm list output (reuse the same command as save_helm_list)
    helm_list_output = run_cmd("helm list -A")
    if not helm_list_output:
        print("No Helm releases found or helm command failed.")
        return
    
    # Parse the output to extract release names and namespaces
    # Helm list -A output format: NAME  NAMESPACE   REVISION    UPDATED STATUS  CHART   APP VERSION
    lines = helm_list_output.strip().split('\n')
    if len(lines) < 2:
        print("No releases found in helm list.")
        return
    
    # Skip header
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 2:
            release_name = parts[0]
            namespace = parts[1]
            print(f"Getting values for release {release_name} in namespace {namespace}...")
            
            # Run helm get values
            values_cmd = f"helm get values {release_name} -n {namespace}"
            values_output = run_cmd(values_cmd)
            
            if values_output:
                filename = f"{namespace}_{release_name}_values.yaml"
                filepath = os.path.join(values_dir, filename)
                with open(filepath, "w") as f:
                    f.write(f"# Helm values for release {release_name} in namespace {namespace}\n")
                    f.write(f"# Command: {values_cmd}\n")
                    f.write(f"# Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    f.write(values_output)
                print(f"Saved values for {release_name} to {filepath}")
            else:
                print(f"Failed to get values for {release_name} in {namespace}.")
                # Save empty file with note
                filename = f"{namespace}_{release_name}_values.yaml"
                filepath = os.path.join(values_dir, filename)
                with open(filepath, "w") as f:
                    f.write(f"# Failed to get values for release {release_name} in namespace {namespace}\n")
                    f.write(f"# Command: {values_cmd}\n")
                    f.write(f"# Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("# No output captured.\n")
    
    print(f"Helm values saved to {values_dir}")


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

    # For local-only functions, use current node
    nodes = get_current_node()
    node_ips = get_nodes_with_ips()  # Still fetch all for port scans (cluster-wide)

    if not node_ips:
        print("No node IPs found.")
        return

    # Save node port scans (scans all nodes from current node)
    save_node_port_scans(base_dir, node_ips)

    # Save pods -o wide for all namespaces (cluster-wide, local kubectl)
    save_pods_wide(base_dir, namespaces)

    # Get logs for all pods in all namespaces (cluster-wide, local kubectl)
    for ns in namespaces:
        pods = get_pods(ns)
        for pod in pods:
            save_logs(ns, pod, date_str, base_dir)

    # Resources to describe cluster-wide (no namespace, local kubectl)
    cluster_resources = ["apiservices"]
    for res in cluster_resources:
        names = get_resource_names(res)
        for name in names:
            save_describe(res, name, None, base_dir)

    # Resources to describe per namespace (local kubectl)
    namespaced_resources = [
        "pods",
        "deployments",
        "statefulsets",
        "replicasets",
        "services",
        "endpoints",
        "ingress",
        "daemonsets",
    ]

    for ns in namespaces:
        for res in namespaced_resources:
            names = get_resource_names(res, ns)
            for name in names:
                save_describe(res, name, ns, base_dir)

    # Handle CRDs cluster-wide (they are cluster scoped, local kubectl)
    crds = get_resource_names("customresourcedefinitions")
    for crd in crds:
        save_describe("customresourcedefinitions", crd, None, base_dir)

    # Save OS info locally (single-node)
    save_os_info(base_dir)

    # Save detailed system info locally (single-node, new function)
    save_detailed_system_info(base_dir)

    # Save machines info (cluster-wide, local kubectl)
    save_machines(base_dir)
    
    # Save machinesets info (in openshift-machine-api namespace, local kubectl)
    save_machinesets(base_dir)
    
    # Save machinedeployments info (in openshift-machine-api namespace, local kubectl)
    save_machinedeployments(base_dir)

    # Save nodes describe (cluster-wide, local kubectl)
    save_nodes_describe(base_dir)

    # Save Kubernetes system logs locally (single-node)
    save_k8s_system_logs(base_dir)

    # Save Helm releases list (cluster-wide, local helm)
    save_helm_list(base_dir)

    # Save Helm values for each release (new function)
    save_helm_values(base_dir)

    # Save kubectl top info (cluster-wide, local kubectl)
    save_kubectl_top(base_dir)

    # Save Kubernetes versions (local kubectl)
    save_k8s_versions(base_dir)
    
    # Save cluster events (cluster-wide, local kubectl)
    save_cluster_events(base_dir)
    
    # Save network policies (per namespace, local kubectl)
    save_network_policies(base_dir, namespaces)
    
    # Save storage info (cluster-wide and per namespace, local kubectl)
    save_storage_info(base_dir, namespaces)
    
    # Save RBAC info (cluster-wide and per namespace, local kubectl)
    save_rbac_info(base_dir, namespaces)
    
    # Save ingress classes (cluster-wide, local kubectl)
    save_ingress_classes(base_dir)
    
    print(f"Backup completed in folder: {base_dir}")

if __name__ == "__main__":
    main()
#!/usr/bin/env python3

import subprocess
import os
import re
import argparse
from datetime import datetime


def create_incremental_path(base_path):
    """
    Creates a unique path by appending an incremental number.
    e.g., 'dir', 'dir_1', 'dir_2'
    """
    if not os.path.exists(base_path):
        return base_path

    name = os.path.splitext(base_path)[0]  # Handle if it has extension, but for dirs, it's fine
    counter = 1
    while True:
        new_path = f"{name}_{counter}"
        if not os.path.exists(new_path):
            return new_path
        counter += 1


def sanitize_pod_name(name):
    """
    Sanitize node name for Kubernetes pod naming (RFC 1123 compliance for DNS subdomain/label).
    - Lowercase everything.
    - Replace invalid chars (e.g., '.', '_', uppercase) with '-'.
    - Remove consecutive hyphens.
    - Ensure starts/ends with alphanumeric.
    - Truncate to 253 chars max.
    """
    # Lowercase and replace invalid chars with '-'
    sanitized = re.sub(r'[^a-z0-9.-]', '-', name.lower())
    # Replace dots with hyphens (for subdomain safety, though dots are allowed in subdomains)
    sanitized = sanitized.replace('.', '-')
    # Remove consecutive hyphens
    sanitized = re.sub(r'-+', '-', sanitized)
    # Strip leading/trailing hyphens
    sanitized = sanitized.strip('-')
    # Truncate if too long (unlikely)
    if len(sanitized) > 253:
        sanitized = sanitized[:253]
    return sanitized


def run_cmd(cmd, retries=2):
    """Run shell command and return output (stdout). Retries on failure. Captures stderr for errors."""
    for attempt in range(retries + 1):
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
        print(f"Error on attempt {attempt + 1}/{retries + 1}: {cmd}\n{result.stderr}")
        if attempt < retries:
            print("Retrying in 5 seconds...")
            time.sleep(5)  # Wait before retry
    return None


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


def save_node_port_scans(base_dir, node_ips, full_scan=False):
    """
    For each node's internal IP, launch temporary netshoot pods and run nmap on port ranges.
    - Always: 1-1024 and 30000-32767 (separate files).
    - If full_scan=True: Additional full 1-65535 scan.
    No --open: Shows all states (open/closed/filtered) like manual.
    Added -v for verbose output.
    """
    scans_dir = os.path.join(base_dir, "scans")
    os.makedirs(scans_dir, exist_ok=True)

    ranges = [
        ("1-1024", "1-1024", "well-known ports"),
        ("30000-32767", "30000-32767", "K8s NodePorts")
    ]
    if full_scan:
        ranges.append(("full", "1-65535", "full range"))

    print("Starting node port scans using temporary netshoot pods...")
    print(f"Scanning ranges: {', '.join([r[1] for r in ranges])} - separate files per range.")
    
    for node, ip in node_ips:
        print(f"Scanning ports on node {node} (IP: {ip})...")
        
        # Generate base timestamp WITHOUT underscore (e.g., 20251010182714)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        sanitized_node = sanitize_pod_name(node)

        for range_id, port_range, description in ranges:
            print(f"  - Scanning {port_range} ({description})...")
            filename = f"{node}_{ip}_ports_{range_id}.txt"
            filepath = os.path.join(scans_dir, filename)
            pod_name = f"net-test-{sanitized_node}-{timestamp}-{range_id}"
            nmap_cmd = (
                f"kubectl run {pod_name} --image=nicolaka/netshoot --rm -i --restart=Never "
                f"-- nmap -p {port_range} {ip} -v -sT -T3"  # -v verbose, -T3 balanced timing, no --open
            )
            nmap_output = run_cmd(nmap_cmd)

            if nmap_output:
                with open(filepath, "w") as f:
                    f.write(f"--- Node: {node} (IP: {ip}) ---\n")
                    f.write(f"Scan command: nmap -p {port_range} {ip} -v -sT -T3\n")
                    f.write(f"Port range: {port_range} ({description})\n")
                    f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Pod used: {pod_name}\n\n")
                    f.write(nmap_output)
                print(f"    Saved {port_range} scan for {node} to {filepath}")
            else:
                print(f"    Failed {port_range} scan for {node} after retries.")
                with open(filepath, "w") as f:
                    f.write(f"--- Node: {node} (IP: {ip}) ---\n")
                    f.write(f"Scan failed - no output captured after retries.\n")
                    f.write(f"Port range: {port_range} ({description})\n")
                    f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Command attempted: {nmap_cmd}\n")

        print(f"Completed scans for {node}.")


def main():
    parser = argparse.ArgumentParser(description="Scan Kubernetes node ports using nmap in temporary pods.")
    parser.add_argument("--full", action="store_true", help="Also scan full 1-65535 range (like manual command).")
    args = parser.parse_args()

    date_str = datetime.now().strftime("%Y-%m-%d")
    base_dir_name = f"k8s_backup_node_ports_scan_{date_str}"
    base_dir = create_incremental_path(base_dir_name)
    os.makedirs(base_dir, exist_ok=True)
    print(f"Port scan results will be saved to: {base_dir}")
    num_scans = 3 if args.full else 2
    print(f"Files per node: {num_scans} (1-1024, 30000-32767, and full if --full).")

    node_ips = get_nodes_with_ips()
    if not node_ips:
        print("No node IPs found. Exiting.")
        return

    print(f"Found {len(node_ips)} nodes to scan ({num_scans} scans each).")
    save_node_port_scans(base_dir, node_ips, full_scan=args.full)
    print(f"Port scans completed. Check directory: {base_dir}")


if __name__ == "__main__":
    import time  # For sleep in retries
    main()
#!/usr/bin/env python3

import os
import re
import sys
from collections import defaultdict
from difflib import unified_diff

def list_txt_files(root):
    txt_files = set()
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.endswith(".txt"):
                full_path = os.path.join(dirpath, f)
                rel_path = os.path.relpath(full_path, root)
                txt_files.add(rel_path)
    return txt_files

def count_resources(folder, resource_types):
    counts = {}
    for rtype in resource_types:
        rdir = os.path.join(folder, "describes", rtype)
        if os.path.isdir(rdir):
            files = [f for f in os.listdir(rdir) if f.endswith(".txt")]
            counts[rtype] = len(files)
        else:
            counts[rtype] = 0
    return counts

def count_pods_by_phase(folder):
    pod_dir = os.path.join(folder, "describes", "pods")
    phases = defaultdict(int)
    if not os.path.isdir(pod_dir):
        return phases
    for f in os.listdir(pod_dir):
        if not f.endswith(".txt"):
            continue
        filepath = os.path.join(pod_dir, f)
        try:
            with open(filepath, "r") as file:
                content = file.read()
                # Look for "Status: Running" or "Phase: Running" etc.
                m = re.search(r"Status:\s*(\w+)", content)
                if not m:
                    m = re.search(r"Phase:\s*(\w+)", content)
                phase = m.group(1) if m else "Unknown"
                phases[phase] += 1
        except Exception as e:
            log(f"Failed to read pod file {filepath}: {e}")
    return phases

def parse_env_vars_from_deployment_file(filepath):
    env_vars = defaultdict(set)
    current_container = "default"

    try:
        with open(filepath, "r") as f:
            lines = f.readlines()
    except Exception as e:
        log(f"Failed to read {filepath}: {e}")
        return env_vars

    in_env_section = False
    for line in lines:
        line_strip = line.strip()

        container_match = re.match(r"^Containers?:\s*$", line_strip)
        container_name_match = re.match(r"^Container:\s*(\S+)", line_strip)
        if container_name_match:
            current_container = container_name_match.group(1)
            continue
        elif container_match:
            current_container = "default"
            continue

        if re.match(r"^Environment( Variables)?:\s*$", line_strip):
            in_env_section = True
            continue

        if in_env_section:
            if not line.startswith(" ") and not line.startswith("\t"):
                in_env_section = False
                continue

            m_eq = re.match(r"^\s*([A-Z0-9_]+)=(.*)$", line_strip)
            m_colon = re.match(r"^\s*([A-Z0-9_]+):\s*(.*)$", line_strip)
            if m_eq:
                env_vars[current_container].add(m_eq.group(1))
            elif m_colon:
                env_vars[current_container].add(m_colon.group(1))

    return env_vars

def get_deployment_env_vars(folder):
    deploy_dir = os.path.join(folder, "describes", "deployments")
    env_vars_all = defaultdict(set)
    if not os.path.isdir(deploy_dir):
        return env_vars_all

    for f in os.listdir(deploy_dir):
        if not f.endswith(".txt"):
            continue
        filepath = os.path.join(deploy_dir, f)
        env_vars = parse_env_vars_from_deployment_file(filepath)
        for c, vars_set in env_vars.items():
            env_vars_all[c].update(vars_set)
    return env_vars_all

def extract_container_images_from_deployment(filepath):
    """
    Extract container images from deployment describe/yaml text.
    Heuristic: look for lines with 'Image: <image>'
    """
    images = defaultdict(set)  # container_name -> set of images
    current_container = "default"
    try:
        with open(filepath, "r") as f:
            lines = f.readlines()
    except Exception as e:
        log(f"Failed to read {filepath}: {e}")
        return images

    for line in lines:
        line_strip = line.strip()
        container_name_match = re.match(r"^Container:\s*(\S+)", line_strip)
        if container_name_match:
            current_container = container_name_match.group(1)
            continue
        m = re.match(r"^Image:\s*(\S+)", line_strip)
        if m:
            images[current_container].add(m.group(1))
    return images

def get_deployment_images(folder):
    deploy_dir = os.path.join(folder, "describes", "deployments")
    images_all = defaultdict(set)
    if not os.path.isdir(deploy_dir):
        return images_all

    for f in os.listdir(deploy_dir):
        if not f.endswith(".txt"):
            continue
        filepath = os.path.join(deploy_dir, f)
        images = extract_container_images_from_deployment(filepath)
        for c, imgs in images.items():
            images_all[c].update(imgs)
    return images_all

def extract_labels_from_deployment(filepath):
    """
    Extract labels from deployment describe/yaml text.
    Heuristic: look for lines under 'Labels:' section, e.g. 'key=value'
    """
    labels = {}
    in_labels_section = False
    try:
        with open(filepath, "r") as f:
            lines = f.readlines()
    except Exception as e:
        log(f"Failed to read {filepath}: {e}")
        return labels

    for line in lines:
        line_strip = line.strip()
        if re.match(r"^Labels:\s*$", line_strip):
            in_labels_section = True
            continue
        if in_labels_section:
            if not line.startswith(" ") and not line.startswith("\t"):
                break
            # parse key=value
            m = re.match(r"^\s*([^=]+)=(.*)$", line_strip)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                labels[key] = val
    return labels

def get_deployment_labels(folder):
    deploy_dir = os.path.join(folder, "describes", "deployments")
    labels_all = {}
    if not os.path.isdir(deploy_dir):
        return labels_all

    for f in os.listdir(deploy_dir):
        if not f.endswith(".txt"):
            continue
        filepath = os.path.join(deploy_dir, f)
        labels = extract_labels_from_deployment(filepath)
        labels_all[f] = labels
    return labels_all

def get_configmap_keys(folder):
    cm_dir = os.path.join(folder, "describes", "configmaps")
    keys_all = {}
    if not os.path.isdir(cm_dir):
        return keys_all

    for f in os.listdir(cm_dir):
        if not f.endswith(".txt"):
            continue
        filepath = os.path.join(cm_dir, f)
        keys = set()
        try:
            with open(filepath, "r") as file:
                content = file.read()
                # Heuristic: look for keys in YAML or describe output
                # e.g. lines under "Data" or "Data:" section
                # We'll just look for lines like "key: value"
                in_data_section = False
                for line in content.splitlines():
                    if re.match(r"^Data:\s*$", line.strip()):
                        in_data_section = True
                        continue
                    if in_data_section:
                        if not line.startswith(" ") and not line.startswith("\t"):
                            break
                        m = re.match(r"^\s*([^:]+):", line)
                        if m:
                            keys.add(m.group(1).strip())
        except Exception as e:
            log(f"Failed to read configmap file {filepath}: {e}")
        keys_all[f] = keys
    return keys_all

def count_events(folder):
    events_dir = os.path.join(folder, "events")
    count = 0
    if not os.path.isdir(events_dir):
        return count
    for f in os.listdir(events_dir):
        if not f.endswith(".txt"):
            continue
        filepath = os.path.join(events_dir, f)
        try:
            with open(filepath, "r") as file:
                content = file.read()
                # Count lines or entries - heuristic: count lines with timestamps or event names
                count += len(content.splitlines())
        except Exception as e:
            log(f"Failed to read event file {filepath}: {e}")
    return count

def read_version_file(folder, filename):
    path = os.path.join(folder, filename)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except Exception as e:
        log(f"Failed to read version file {path}: {e}")
        return None

def diff_resource_yamls(folder1, folder2, resource_type):
    """
    For resources present in both folders, do a line diff of their describe files.
    Returns dict: filename -> diff lines list
    """
    diffs = {}
    dir1 = os.path.join(folder1, "describes", resource_type)
    dir2 = os.path.join(folder2, "describes", resource_type)
    if not os.path.isdir(dir1) or not os.path.isdir(dir2):
        return diffs

    files1 = set(f for f in os.listdir(dir1) if f.endswith(".txt"))
    files2 = set(f for f in os.listdir(dir2) if f.endswith(".txt"))
    common_files = files1 & files2

    for f in common_files:
        path1 = os.path.join(dir1, f)
        path2 = os.path.join(dir2, f)
        try:
            with open(path1, "r") as file1, open(path2, "r") as file2:
                lines1 = file1.readlines()
                lines2 = file2.readlines()
                diff_lines = list(unified_diff(lines1, lines2, fromfile=f"{folder1}/{resource_type}/{f}", tofile=f"{folder2}/{resource_type}/{f}"))
                if diff_lines:
                    diffs[f] = diff_lines
        except Exception as e:
            log(f"Failed to diff files {path1} and {path2}: {e}")
    return diffs

def count_errors_fatal(folder):
    error_count = 0
    fatal_count = 0
    for dirpath, _, files in os.walk(folder):
        for f in files:
            if not f.endswith(".txt"):
                continue
            filepath = os.path.join(dirpath, f)
            try:
                with open(filepath, "r", errors="ignore") as file:
                    content = file.read()
                    error_count += len(re.findall(r"\bERROR\b", content, re.IGNORECASE))
                    fatal_count += len(re.findall(r"\bFATAL\b", content, re.IGNORECASE))
            except Exception as e:
                log(f"Failed to read {filepath}: {e}")
    return error_count, fatal_count

def compare_env_vars(env1, env2):
    all_containers = set(env1.keys()) | set(env2.keys())
    diffs = {}
    for c in all_containers:
        vars1 = env1.get(c, set())
        vars2 = env2.get(c, set())
        added = vars2 - vars1
        removed = vars1 - vars2
        if added or removed:
            diffs[c] = {"added": added, "removed": removed}
    return diffs

def compare_images(img1, img2):
    all_containers = set(img1.keys()) | set(img2.keys())
    diffs = {}
    for c in all_containers:
        i1 = img1.get(c, set())
        i2 = img2.get(c, set())
        added = i2 - i1
        removed = i1 - i2
        if added or removed:
            diffs[c] = {"added": added, "removed": removed}
    return diffs

def compare_labels(labels1, labels2):
    diffs = {}
    all_files = set(labels1.keys()) | set(labels2.keys())
    for f in all_files:
        l1 = labels1.get(f, {})
        l2 = labels2.get(f, {})
        added = {k: v for k, v in l2.items() if k not in l1}
        removed = {k: v for k, v in l1.items() if k not in l2}
        changed = {k: (l1[k], l2[k]) for k in l1 if k in l2 and l1[k] != l2[k]}
        if added or removed or changed:
            diffs[f] = {"added": added, "removed": removed, "changed": changed}
    return diffs

def compare_configmap_keys(cm1, cm2):
    diffs = {}
    all_files = set(cm1.keys()) | set(cm2.keys())
    for f in all_files:
        k1 = cm1.get(f, set())
        k2 = cm2.get(f, set())
        added = k2 - k1
        removed = k1 - k2
        if added or removed:
            diffs[f] = {"added": added, "removed": removed}
    return diffs

def get_ingress_labels(folder):
    ingress_dir = os.path.join(folder, "describes", "ingresses")
    labels_all = {}
    if not os.path.isdir(ingress_dir):
        return labels_all

    for f in os.listdir(ingress_dir):
        if not f.endswith(".txt"):
            continue
        filepath = os.path.join(ingress_dir, f)
        labels = extract_labels_from_deployment(filepath)  # same heuristic works
        labels_all[f] = labels
    return labels_all

def extract_ingress_hosts(filepath):
    """
    Extract hostnames from ingress describe/yaml text.
    Heuristic: look for lines starting with 'Host:' or 'Hosts:'
    """
    hosts = set()
    try:
        with open(filepath, "r") as f:
            for line in f:
                line_strip = line.strip()
                m = re.match(r"^Host:\s*(\S+)", line_strip)
                if m:
                    hosts.add(m.group(1))
                # Also handle 'Hosts:' section with multiple hosts
                if line_strip == "Hosts:":
                    # Next indented lines are hosts
                    for host_line in f:
                        host_line_strip = host_line.strip()
                        if not host_line_strip or not host_line.startswith(" "):
                            break
                        hosts.add(host_line_strip)
    except Exception as e:
        log(f"Failed to read ingress file {filepath}: {e}")
    return hosts

def get_ingress_hosts(folder):
    ingress_dir = os.path.join(folder, "describes", "ingresses")
    hosts_all = {}
    if not os.path.isdir(ingress_dir):
        return hosts_all

    for f in os.listdir(ingress_dir):
        if not f.endswith(".txt"):
            continue
        filepath = os.path.join(ingress_dir, f)
        hosts = extract_ingress_hosts(filepath)
        hosts_all[f] = hosts
    return hosts_all

def compare_ingress_hosts(hosts1, hosts2):
    diffs = {}
    all_files = set(hosts1.keys()) | set(hosts2.keys())
    for f in all_files:
        h1 = hosts1.get(f, set())
        h2 = hosts2.get(f, set())
        added = h2 - h1
        removed = h1 - h2
        if added or removed:
            diffs[f] = {"added": added, "removed": removed}
    return diffs

def read_helm_releases(folder):
    """
    Reads Helm releases from helm_releases/helm_list_all_namespaces.txt file.
    Returns a set of release names.
    """
    helm_file = os.path.join(folder, "helm_releases", "helm_list_all_namespaces.txt")
    releases = set()
    if not os.path.isfile(helm_file):
        return releases
    try:
        with open(helm_file, "r") as f:
            lines = f.readlines()
    except Exception as e:
        log(f"Failed to read helm releases file: {e}")
        return releases

    # Skip header line(s), parse release names (usually first column)
    for line in lines[1:]:
        parts = line.strip().split()
        if parts:
            releases.add(parts[0])
    return releases

def main(folder1, folder2, logfile_path):
    global log_file
    log_file = open(logfile_path, "w")

    def log(msg=""):
        log_file.write(msg + "\n")

    globals()['log'] = log

    log(f"Comparing folders:\n  Folder1: {folder1}\n  Folder2: {folder2}\n")

    # 1. File names
    files1 = list_txt_files(folder1)
    files2 = list_txt_files(folder2)
    only_in_1 = files1 - files2
    only_in_2 = files2 - files1

    log("File name differences:")
    if only_in_1:
        log(f"  Files only in folder1 ({len(only_in_1)}):")
        for f in sorted(only_in_1):
            log(f"    {f}")
    else:
        log("  No files unique to folder1.")

    if only_in_2:
        log(f"  Files only in folder2 ({len(only_in_2)}):")
        for f in sorted(only_in_2):
            log(f"    {f}")
    else:
        log("  No files unique to folder2.")

    log("\n")

    # 2. Resource counts
    resource_types = ["pods", "deployments", "statefulsets", "replicasets", "services", "configmaps", "secrets", "ingress"]
    counts1 = count_resources(folder1, resource_types)
    counts2 = count_resources(folder2, resource_types)
    log("Resource counts:")
    for r in resource_types:
        log(f"  {r}: Folder1={counts1.get(r,0)}, Folder2={counts2.get(r,0)}")
        if counts1.get(r,0) != counts2.get(r,0):
            log(f"    -> Count differs!")

    log("\n")

    # 3. Pod phases
    phases1 = count_pods_by_phase(folder1)
    phases2 = count_pods_by_phase(folder2)
    all_phases = set(phases1.keys()) | set(phases2.keys())
    log("Pod phases:")
    for p in sorted(all_phases):
        c1 = phases1.get(p,0)
        c2 = phases2.get(p,0)
        log(f"  {p}: Folder1={c1}, Folder2={c2}")
        if c1 != c2:
            log("    -> Phase count differs!")

    log("\n")

    # 4. Environment variables
    env1 = get_deployment_env_vars(folder1)
    env2 = get_deployment_env_vars(folder2)
    env_diffs = compare_env_vars(env1, env2)
    log("Environment variable differences in deployments:")
    if env_diffs:
        for container, changes in env_diffs.items():
            log(f"  Container: {container}")
            if changes["added"]:
                log(f"    Added vars: {', '.join(sorted(changes['added']))}")
            if changes["removed"]:
                log(f"    Removed vars: {', '.join(sorted(changes['removed']))}")
    else:
        log("  No differences in environment variables.")

    log("\n")

    # 5. Container images
    img1 = get_deployment_images(folder1)
    img2 = get_deployment_images(folder2)
    img_diffs = compare_images(img1, img2)
    log("Container image differences in deployments:")
    if img_diffs:
        for container, changes in img_diffs.items():
            log(f"  Container: {container}")
            if changes["added"]:
                log(f"    Added images: {', '.join(sorted(changes['added']))}")
            if changes["removed"]:
                log(f"    Removed images: {', '.join(sorted(changes['removed']))}")
    else:
        log("  No differences in container images.")

    log("\n")

    # 6. Deployment labels
    labels1 = get_deployment_labels(folder1)
    labels2 = get_deployment_labels(folder2)
    label_diffs = compare_labels(labels1, labels2)
    log("Deployment label differences:")
    if label_diffs:
        for f, changes in label_diffs.items():
            log(f"  Deployment file: {f}")
            if changes["added"]:
                log(f"    Added labels: {', '.join(f'{k}={v}' for k,v in changes['added'].items())}")
            if changes["removed"]:
                log(f"    Removed labels: {', '.join(f'{k}={v}' for k,v in changes['removed'].items())}")
            if changes["changed"]:
                log(f"    Changed labels:")
                for k, (v1, v2) in changes["changed"].items():
                    log(f"      {k}: Folder1='{v1}' vs Folder2='{v2}'")
    else:
        log("  No differences in deployment labels.")

    log("\n")

    # 7. ConfigMap keys
    cm1 = get_configmap_keys(folder1)
    cm2 = get_configmap_keys(folder2)
    cm_diffs = compare_configmap_keys(cm1, cm2)
    log("ConfigMap key differences:")
    if cm_diffs:
        for f, changes in cm_diffs.items():
            log(f"  ConfigMap file: {f}")
            if changes["added"]:
                log(f"    Added keys: {', '.join(sorted(changes['added']))}")
            if changes["removed"]:
                log(f"    Removed keys: {', '.join(sorted(changes['removed']))}")
    else:
        log("  No differences in ConfigMap keys.")

    log("\n")

    # 8. Events count
    events1 = count_events(folder1)
    events2 = count_events(folder2)
    log(f"Events count:")
    log(f"  Folder1: {events1}")
    log(f"  Folder2: {events2}")
    if events1 != events2:
        log("  -> Event counts differ!")
    else:
        log("  Event counts are the same.")

    log("\n")

    # 9. Kubernetes and Helm versions
    k8s_ver1 = read_version_file(folder1, "k8s_version.txt")
    k8s_ver2 = read_version_file(folder2, "k8s_version.txt")
    helm_ver1 = read_version_file(folder1, "helm_version.txt")
    helm_ver2 = read_version_file(folder2, "helm_version.txt")

    log("Kubernetes version:")
    log(f"  Folder1: {k8s_ver1 or 'N/A'}")
    log(f"  Folder2: {k8s_ver2 or 'N/A'}")
    if k8s_ver1 != k8s_ver2:
        log("  -> Kubernetes versions differ!")
    else:
        log("  Kubernetes versions are the same.")

    log("\n")

    log("Helm version:")
    log(f"  Folder1: {helm_ver1 or 'N/A'}")
    log(f"  Folder2: {helm_ver2 or 'N/A'}")
    if helm_ver1 != helm_ver2:
        log("  -> Helm versions differ!")
    else:
        log("  Helm versions are the same.")

    log("\n")

    # 10. Helm releases differences
    helm1 = read_helm_releases(folder1)
    helm2 = read_helm_releases(folder2)
    only_in_helm1 = helm1 - helm2
    only_in_helm2 = helm2 - helm1
    log("Helm releases differences:")
    if only_in_helm1:
        log(f"  Releases only in folder1 ({len(only_in_helm1)}): {', '.join(sorted(only_in_helm1))}")
    else:
        log("  No releases unique to folder1.")
    if only_in_helm2:
        log(f"  Releases only in folder2 ({len(only_in_helm2)}): {', '.join(sorted(only_in_helm2))}")
    else:
        log("  No releases unique to folder2.")

    log("\n")

    # 11. Resource YAML diffs for deployments and configmaps (example)
    for rtype in ["deployments", "configmaps"]:
        diffs = diff_resource_yamls(folder1, folder2, rtype)
        log(f"Resource YAML differences for {rtype}:")
        if diffs:
            for fname, diff_lines in diffs.items():
                log(f"  Differences in {fname}:")
                for line in diff_lines:
                    log("    " + line.rstrip())
        else:
            log(f"  No YAML differences found for {rtype}.")

        log("\n")
    # 12. Ingress Labels
    ingress_labels1 = get_ingress_labels(folder1)
    ingress_labels2 = get_ingress_labels(folder2)
    ingress_label_diffs = compare_labels(ingress_labels1, ingress_labels2)
    log("Ingress label differences:")
    if ingress_label_diffs:
        for f, changes in ingress_label_diffs.items():
            log(f"  Ingress file: {f}")
            if changes["added"]:
                log(f"    Added labels: {', '.join(f'{k}={v}' for k,v in changes['added'].items())}")
            if changes["removed"]:
                log(f"    Removed labels: {', '.join(f'{k}={v}' for k,v in changes['removed'].items())}")
            if changes["changed"]:
                log(f"    Changed labels:")
                for k, (v1, v2) in changes["changed"].items():
                    log(f"      {k}: Folder1='{v1}' vs Folder2='{v2}'")
    else:
        log("  No differences in ingress labels.")

    log("\n")

    # Ingress hosts
    ingress_hosts1 = get_ingress_hosts(folder1)
    ingress_hosts2 = get_ingress_hosts(folder2)
    ingress_host_diffs = compare_ingress_hosts(ingress_hosts1, ingress_hosts2)
    log("Ingress host differences:")
    if ingress_host_diffs:
        for f, changes in ingress_host_diffs.items():
            log(f"  Ingress file: {f}")
            if changes["added"]:
                log(f"    Added hosts: {', '.join(sorted(changes['added']))}")
            if changes["removed"]:
                log(f"    Removed hosts: {', '.join(sorted(changes['removed']))}")
    else:
        log("  No differences in ingress hosts.")

    log("\n")

    # Ingress YAML diffs
    ingress_diffs = diff_resource_yamls(folder1, folder2, "ingresses")
    log("Resource YAML differences for ingresses:")
    if ingress_diffs:
        for fname, diff_lines in ingress_diffs.items():
            log(f"  Differences in {fname}:")
            for line in diff_lines:
                log("    " + line.rstrip())
    else:
        log("  No YAML differences found for ingresses.")

    log("\n")

    # 13. ERROR/FATAL counts
    err1, fat1 = count_errors_fatal(folder1)
    err2, fat2 = count_errors_fatal(folder2)
    log("ERROR/FATAL counts:")
    log(f"  Folder1: ERROR={err1}, FATAL={fat1}")
    log(f"  Folder2: ERROR={err2}, FATAL={fat2}")
    if err1 != err2 or fat1 != fat2:
        log("  -> ERROR/FATAL counts differ!")
    else:
        log("  ERROR/FATAL counts are the same.")

    log_file.close()
    print(f"Comparison complete. Output saved to {logfile_path}")


if __name__ == "__main__":
    if len(sys.argv) not in [3,4]:
        print("Usage: python3 compare_folders.py <folder1> <folder2> [logfile]")
        sys.exit(1)
    folder1 = sys.argv[1]
    folder2 = sys.argv[2]
    logfile = sys.argv[3] if len(sys.argv) == 4 else "comparison_log.txt"
    main(folder1, folder2, logfile)


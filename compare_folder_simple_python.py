#!/usr/bin/env python3

import os
import re
import sys
from collections import defaultdict

def list_txt_files(root):
    txt_files = set()
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.endswith(".txt"):
                full_path = os.path.join(dirpath, f)
                rel_path = os.path.relpath(full_path, root)
                txt_files.add(rel_path)
    return txt_files

def count_pods(folder):
    pod_dir = os.path.join(folder, "describes", "pods")
    if not os.path.isdir(pod_dir):
        return 0
    pod_files = [f for f in os.listdir(pod_dir) if f.endswith(".txt")]
    return len(pod_files)

def parse_env_vars_from_deployment_file(filepath):
    """
    Parse environment variables from deployment describe or yaml text file.
    This is a heuristic text-based parser:
    - Looks for lines starting with 'Environment:' or 'Environment Variables:'
    - Then collects lines with format VAR=VALUE or VAR: VALUE
    """
    env_vars = defaultdict(set)  # container_name -> set of env var names
    current_container = "default"

    try:
        with open(filepath, "r") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Failed to read {filepath}: {e}")
        return env_vars

    in_env_section = False
    for line in lines:
        line_strip = line.strip()

        # Detect container name if possible (heuristic)
        # e.g. "Containers:" or "Container: <name>"
        container_match = re.match(r"^Containers?:\s*$", line_strip)
        container_name_match = re.match(r"^Container:\s*(\S+)", line_strip)
        if container_name_match:
            current_container = container_name_match.group(1)
            continue
        elif container_match:
            current_container = "default"
            continue

        # Detect start of environment section
        if re.match(r"^Environment( Variables)?:\s*$", line_strip):
            in_env_section = True
            continue

        # If in environment section, parse env vars lines
        if in_env_section:
            # Empty line or line not indented means end of env section
            if not line.startswith(" ") and not line.startswith("\t"):
                in_env_section = False
                continue

            # Parse lines like VAR=VALUE or VAR: VALUE
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

def read_helm_releases(folder):
    helm_file = os.path.join(folder, "helm_releases", "helm_list_all_namespaces.txt")
    releases = set()
    if not os.path.isfile(helm_file):
        return releases
    try:
        with open(helm_file, "r") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Failed to read helm releases file: {e}")
        return releases

    for line in lines[1:]:
        parts = line.strip().split()
        if parts:
            releases.add(parts[0])
    return releases

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
                print(f"Failed to read {filepath}: {e}")
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

def main(folder1, folder2):
    print(f"Comparing folders:\n  Folder1: {folder1}\n  Folder2: {folder2}\n")

    files1 = list_txt_files(folder1)
    files2 = list_txt_files(folder2)
    only_in_1 = files1 - files2
    only_in_2 = files2 - files1

    print("File name differences:")
    if only_in_1:
        print(f"  Files only in folder1 ({len(only_in_1)}):")
        for f in sorted(only_in_1):
            print(f"    {f}")
    else:
        print("  No files unique to folder1.")

    if only_in_2:
        print(f"  Files only in folder2 ({len(only_in_2)}):")
        for f in sorted(only_in_2):
            print(f"    {f}")
    else:
        print("  No files unique to folder2.")

    print("\n")

    pods1 = count_pods(folder1)
    pods2 = count_pods(folder2)
    print(f"Number of pods:")
    print(f"  Folder1: {pods1}")
    print(f"  Folder2: {pods2}")
    if pods1 != pods2:
        print("  -> Pod count differs!")
    else:
        print("  Pod count is the same.")

    print("\n")

    env1 = get_deployment_env_vars(folder1)
    env2 = get_deployment_env_vars(folder2)
    env_diffs = compare_env_vars(env1, env2)
    print("Environment variable differences in deployments:")
    if env_diffs:
        for container, changes in env_diffs.items():
            print(f"  Container: {container}")
            if changes["added"]:
                print(f"    Added vars: {', '.join(sorted(changes['added']))}")
            if changes["removed"]:
                print(f"    Removed vars: {', '.join(sorted(changes['removed']))}")
    else:
        print("  No differences in environment variables.")

    print("\n")

    helm1 = read_helm_releases(folder1)
    helm2 = read_helm_releases(folder2)
    only_in_helm1 = helm1 - helm2
    only_in_helm2 = helm2 - helm1
    print("Helm releases differences:")
    if only_in_helm1:
        print(f"  Releases only in folder1 ({len(only_in_helm1)}): {', '.join(sorted(only_in_helm1))}")
    else:
        print("  No releases unique to folder1.")
    if only_in_helm2:
        print(f"  Releases only in folder2 ({len(only_in_helm2)}): {', '.join(sorted(only_in_helm2))}")
    else:
        print("  No releases unique to folder2.")

    print("\n")

    err1, fat1 = count_errors_fatal(folder1)
    err2, fat2 = count_errors_fatal(folder2)
    print("ERROR/FATAL counts:")
    print(f"  Folder1: ERROR={err1}, FATAL={fat1}")
    print(f"  Folder2: ERROR={err2}, FATAL={fat2}")
    if err1 != err2 or fat1 != fat2:
        print("  -> ERROR/FATAL counts differ!")
    else:
        print("  ERROR/FATAL counts are the same.")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 compare_folders.py <folder1> <folder2>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

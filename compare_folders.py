#!/usr/bin/env python3

import os
import re
import yaml  # PyYAML required: pip install pyyaml
from collections import defaultdict

def list_txt_files(root):
    """Return set of relative paths of all .txt files under root."""
    txt_files = set()
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.endswith(".txt"):
                full_path = os.path.join(dirpath, f)
                rel_path = os.path.relpath(full_path, root)
                txt_files.add(rel_path)
    return txt_files

def count_pods(folder):
    """Count pods by counting pod describe files or parsing pod describe files."""
    pod_dir = os.path.join(folder, "describes", "pods")
    if not os.path.isdir(pod_dir):
        return 0
    # Count number of pod files
    pod_files = [f for f in os.listdir(pod_dir) if f.endswith(".txt")]
    return len(pod_files)

def parse_env_vars_from_deployment_file(filepath):
    """Parse environment variables from a deployment yaml or describe file."""
    env_vars = defaultdict(set)  # container_name -> set of env var names

    try:
        with open(filepath, "r") as f:
            content = f.read()
    except Exception as e:
        print(f"Failed to read {filepath}: {e}")
        return env_vars

    # Try to parse as YAML first
    try:
        data = yaml.safe_load(content)
        # If this is a deployment yaml, env vars are under:
        # spec.template.spec.containers[].env
        containers = data.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        for c in containers:
            cname = c.get("name", "<no-name>")
            envlist = c.get("env", [])
            for env in envlist:
                if "name" in env:
                    env_vars[cname].add(env["name"])
        return env_vars
    except Exception:
        # Not YAML or failed, try to parse from describe text
        # Look for lines like: "Environment:  VAR1=value1"
        # or "Environment Variables:"
        # We'll do a simple regex search for lines with env vars
        env_pattern = re.compile(r"^\s*([A-Z0-9_]+)=(.*)$", re.MULTILINE)
        matches = env_pattern.findall(content)
        for name, val in matches:
            env_vars["default"].add(name)
        return env_vars

def get_deployment_env_vars(folder):
    """Get env vars from all deployment files in folder."""
    deploy_dir = os.path.join(folder, "describes", "deployments")
    env_vars_all = defaultdict(set)  # container_name -> set of env var names
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
    """Read helm releases from helm_releases/helm_list_all_namespaces.txt"""
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

    # Skip header line(s), parse release names (usually first column)
    for line in lines[1:]:
        parts = line.strip().split()
        if parts:
            releases.add(parts[0])
    return releases

def count_errors_fatal(folder):
    """Count number of ERROR and FATAL occurrences in all .txt files under folder."""
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
    """Compare two env var dicts: container -> set of vars."""
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

    # 1. File names difference
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

    # 2. Number of pods
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

    # 3. Environment variables from deployments
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

    # 4. Helm releases differences
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

    # 5. Count ERROR/FATAL in all .txt files
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
    import sys
    if len(sys.argv) != 3:
        print("Usage: python3 compare_folders.py <folder1> <folder2>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

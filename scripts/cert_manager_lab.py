#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Local automation for kind + cert-manager smoke checks.

This script focuses on safe, repeatable setup for local validation:
1) Ensure a kind cluster exists (default: certman-lab)
2) Install/upgrade cert-manager using Helm
3) Run a minimal cert-manager self-signed smoke test
4) Optionally uninstall cert-manager and delete smoke resources

Examples:
    uv run scripts/cert_manager_lab.py up
    uv run scripts/cert_manager_lab.py smoke
    uv run scripts/cert_manager_lab.py status
    uv run scripts/cert_manager_lab.py down
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CLUSTER_NAME = "certman-lab"
DEFAULT_NODE_IMAGE = "kindest/node:v1.34.0"
DEFAULT_CERT_MANAGER_NS = "cert-manager"
DEFAULT_RELEASE_NAME = "cert-manager"
DEFAULT_HELM_REPO_NAME = "jetstack"
DEFAULT_HELM_REPO_URL = "https://charts.jetstack.io"
# Keep this pinned for repeatability; can be overridden by --chart-version.
DEFAULT_CHART_VERSION = "v1.18.2"
LAB_NAMESPACE = "certman-lab"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SMOKE_MANIFEST_PATH = PROJECT_ROOT / "k8s" / "cert-manager-smoke-selfsigned.yaml"


@dataclass(frozen=True)
class CmdResult:
    returncode: int
    stdout: str
    stderr: str


def _safe_write(text: str, *, is_stderr: bool = False) -> None:
    stream = sys.stderr if is_stderr else sys.stdout
    encoding = stream.encoding or "utf-8"
    payload = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    stream.write(payload + "\n")


def run_cmd(cmd: list[str], *, check: bool = True, cwd: Path | None = None) -> CmdResult:
    _safe_write(f"$ {' '.join(cmd)}")
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.stdout:
        _safe_write(completed.stdout.rstrip())
    if completed.stderr:
        _safe_write(completed.stderr.rstrip(), is_stderr=True)
    if check and completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(cmd)}")
    return CmdResult(completed.returncode, completed.stdout, completed.stderr)


def require_binary(binary: str) -> None:
    if shutil.which(binary) is None:
        raise RuntimeError(f"Missing required binary in PATH: {binary}")


def detect_prerequisites() -> None:
    for binary in ["docker", "kind", "kubectl", "helm"]:
        require_binary(binary)
    print("Prerequisite binaries found: docker, kind, kubectl, helm")


def cluster_exists(cluster_name: str) -> bool:
    result = run_cmd(["kind", "get", "clusters"], check=False)
    return cluster_name in [line.strip() for line in result.stdout.splitlines() if line.strip()]


def namespace_exists(name: str) -> bool:
    result = run_cmd(["kubectl", "get", "namespace", name], check=False)
    return result.returncode == 0


def ensure_namespace(name: str) -> None:
    if namespace_exists(name):
        return
    run_cmd(["kubectl", "create", "namespace", name])


def ensure_cluster(cluster_name: str, node_image: str) -> None:
    if cluster_exists(cluster_name):
        print(f"Kind cluster already exists: {cluster_name}")
        return

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as fp:
        fp.write(
            """
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  image: NODE_IMAGE_PLACEHOLDER
""".strip().replace("NODE_IMAGE_PLACEHOLDER", node_image)
            + "\n"
        )
        config_path = fp.name

    try:
        run_cmd(
            [
                "kind",
                "create",
                "cluster",
                "--name",
                cluster_name,
                "--config",
                config_path,
                "--wait",
                "5m",
            ]
        )
    finally:
        Path(config_path).unlink(missing_ok=True)


def install_cert_manager(namespace: str, release_name: str, chart_version: str) -> None:
    run_cmd(["helm", "repo", "add", DEFAULT_HELM_REPO_NAME, DEFAULT_HELM_REPO_URL], check=False)
    run_cmd(["helm", "repo", "update", DEFAULT_HELM_REPO_NAME])
    run_cmd(
        [
            "helm",
            "upgrade",
            "--install",
            release_name,
            f"{DEFAULT_HELM_REPO_NAME}/cert-manager",
            "--namespace",
            namespace,
            "--create-namespace",
            "--set",
            "crds.enabled=true",
            "--version",
            chart_version,
            "--wait",
            "--timeout",
            "5m",
        ]
    )


def cert_manager_status(namespace: str) -> None:
    run_cmd(["kubectl", "-n", namespace, "get", "pods", "-o", "wide"])
    for deploy in ["cert-manager", "cert-manager-cainjector", "cert-manager-webhook"]:
        run_cmd(
            [
                "kubectl",
                "-n",
                namespace,
                "rollout",
                "status",
                f"deployment/{deploy}",
                "--timeout=120s",
            ]
        )


def apply_smoke_manifest() -> None:
    if not SMOKE_MANIFEST_PATH.exists():
        raise RuntimeError(f"Smoke manifest not found: {SMOKE_MANIFEST_PATH}")
    ensure_namespace(LAB_NAMESPACE)
    run_cmd(["kubectl", "apply", "-f", str(SMOKE_MANIFEST_PATH)])


def smoke_status(*, strict: bool = True) -> None:
    if not namespace_exists(LAB_NAMESPACE):
        if strict:
            raise RuntimeError(f"Namespace not found: {LAB_NAMESPACE}")
        print(f"Smoke namespace not found: {LAB_NAMESPACE}")
        return

    run_cmd(["kubectl", "-n", LAB_NAMESPACE, "get", "issuer,certificate,secret"], check=False)
    wait_result = run_cmd(
        [
            "kubectl",
            "-n",
            LAB_NAMESPACE,
            "wait",
            "--for=condition=Ready",
            "certificate/smoke-cert-selfsigned",
            "--timeout=120s",
        ],
        check=False,
    )
    if wait_result.returncode != 0:
        message = "Smoke certificate is not Ready yet (or not deployed)."
        if strict:
            raise RuntimeError(message)
        print(message)


def delete_smoke_manifest() -> None:
    run_cmd(["kubectl", "delete", "-f", str(SMOKE_MANIFEST_PATH)], check=False)


def uninstall_cert_manager(namespace: str, release_name: str) -> None:
    run_cmd(["helm", "uninstall", release_name, "--namespace", namespace], check=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="kind + cert-manager local automation")
    parser.add_argument("command", choices=["up", "smoke", "status", "down"], help="Action to run")
    parser.add_argument("--cluster", default=DEFAULT_CLUSTER_NAME, help="Kind cluster name")
    parser.add_argument("--node-image", default=DEFAULT_NODE_IMAGE, help="Kind node image")
    parser.add_argument("--namespace", default=DEFAULT_CERT_MANAGER_NS, help="cert-manager namespace")
    parser.add_argument("--release", default=DEFAULT_RELEASE_NAME, help="Helm release name")
    parser.add_argument("--chart-version", default=DEFAULT_CHART_VERSION, help="cert-manager chart version")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    detect_prerequisites()

    if args.command == "up":
        ensure_cluster(args.cluster, args.node_image)
        install_cert_manager(args.namespace, args.release, args.chart_version)
        cert_manager_status(args.namespace)
        return

    if args.command == "smoke":
        apply_smoke_manifest()
        smoke_status(strict=True)
        return

    if args.command == "status":
        cert_manager_status(args.namespace)
        smoke_status(strict=False)
        return

    if args.command == "down":
        delete_smoke_manifest()
        uninstall_cert_manager(args.namespace, args.release)
        return

    raise RuntimeError(f"Unexpected command: {args.command}")


if __name__ == "__main__":
    main()

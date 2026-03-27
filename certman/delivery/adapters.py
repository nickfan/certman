from __future__ import annotations

from pathlib import Path
import subprocess

from certman.delivery.filesystem import deliver_filesystem_bundle


def deliver_nginx_bundle(*, files: dict[str, str], target_dir: Path) -> list[Path]:
    """Deliver certificate files for Nginx-like layouts."""
    return deliver_filesystem_bundle(files=files, target_dir=target_dir)


def deliver_openresty_bundle(*, files: dict[str, str], target_dir: Path) -> list[Path]:
    """Deliver certificate files for OpenResty-like layouts."""
    return deliver_filesystem_bundle(files=files, target_dir=target_dir)


def deliver_k8s_ingress_bundle(
    *,
    files: dict[str, str],
    target_dir: Path,
    namespace: str = "default",
    secret_name: str = "certman-tls",
    mode: str = "render",
    rollback_on_failure: bool = True,
    kubectl_bin: str = "kubectl",
) -> list[Path]:
    """Write cert files and manage Kubernetes TLS Secret workflow.

    mode:
    - render: only generate manifest files
    - apply: apply manifest to cluster, with optional rollback on failure
    """
    written = deliver_filesystem_bundle(files=files, target_dir=target_dir)

    tls_crt = files.get("fullchain.pem") or files.get("cert.pem")
    tls_key = files.get("privkey.pem")
    if tls_crt is None or tls_key is None:
        return written

    manifest = (
        "apiVersion: v1\n"
        "kind: Secret\n"
        "metadata:\n"
        f"  name: {secret_name}\n"
        f"  namespace: {namespace}\n"
        "type: kubernetes.io/tls\n"
        "stringData:\n"
        "  tls.crt: |-\n"
        f"{_indent_block(tls_crt, 4)}\n"
        "  tls.key: |-\n"
        f"{_indent_block(tls_key, 4)}\n"
    )
    manifest_path = target_dir / "k8s-tls-secret.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest, encoding="utf-8")
    written.append(manifest_path)

    normalized_mode = mode.strip().lower()
    if normalized_mode == "render":
        return written
    if normalized_mode != "apply":
        raise ValueError(f"unsupported k8s delivery mode: {mode}")

    previous_secret_yaml = _try_fetch_existing_secret(
        kubectl_bin=kubectl_bin,
        namespace=namespace,
        secret_name=secret_name,
    )

    apply_proc = subprocess.run(
        [kubectl_bin, "apply", "-f", str(manifest_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if apply_proc.returncode == 0:
        return written

    if rollback_on_failure and previous_secret_yaml:
        rollback_proc = subprocess.run(
            [kubectl_bin, "apply", "-f", "-"],
            input=previous_secret_yaml,
            capture_output=True,
            text=True,
            check=False,
        )
        if rollback_proc.returncode != 0:
            raise RuntimeError(
                "k8s apply failed and rollback failed: "
                f"apply_stderr={apply_proc.stderr.strip()} rollback_stderr={rollback_proc.stderr.strip()}"
            )
        raise RuntimeError(f"k8s apply failed and rolled back: {apply_proc.stderr.strip()}")

    raise RuntimeError(f"k8s apply failed: {apply_proc.stderr.strip()}")


def _try_fetch_existing_secret(*, kubectl_bin: str, namespace: str, secret_name: str) -> str | None:
    proc = subprocess.run(
        [kubectl_bin, "get", "secret", secret_name, "-n", namespace, "-o", "yaml"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    content = proc.stdout.strip()
    return content or None
    return written


def _indent_block(value: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(f"{prefix}{line}" for line in value.splitlines())

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import subprocess
import json
import logging
from typing import Any, Literal
import yaml

logger = logging.getLogger(__name__)


class K8sErrorCode(Enum):
    """K8s delivery error code classification"""
    DRY_RUN_FAILED = "dry_run_failed"
    RBAC_DENIED = "rbac_denied"
    APPLY_FAILED = "apply_failed"
    ROLLBACK_FAILED = "rollback_failed"
    CONNECT_TIMEOUT = "connect_timeout"
    MANIFEST_INVALID = "manifest_invalid"
    CLUSTER_UNREACHABLE = "cluster_unreachable"
    SUCCESS = "success"


@dataclass(frozen=True)
class K8sDeliveryResult:
    """Structured result for k8s delivery"""
    success: bool
    written_paths: list[Path]
    error_code: K8sErrorCode | str | None = None
    error_message: str | None = None
    rollback_manifest: str | None = None
    dry_run_output: str | None = None
    rbac_diagnostics: dict[str, bool] | None = None


@dataclass(frozen=True)
class _CmdResult:
    returncode: int
    stdout: str
    stderr: str
    success: bool


@dataclass(frozen=True)
class _RBACCheckResult:
    has_required_permissions: bool
    missing_perms: list[str]
    diagnostics: dict[str, bool]


def _run_kubectl(args: list[str], timeout: int, stdin: str | None = None) -> _CmdResult:
    """Unified kubectl command runner with timeout handling"""
    try:
        proc = subprocess.run(
            args,
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return _CmdResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            success=proc.returncode == 0,
        )
    except subprocess.TimeoutExpired as e:
        return _CmdResult(
            returncode=-1,
            stdout="",
            stderr=f"Command timeout after {timeout}s",
            success=False,
        )
    except Exception as e:
        return _CmdResult(
            returncode=-1,
            stdout="",
            stderr=str(e),
            success=False,
        )


def _kubectl_dry_run(kubectl_bin: str, manifest_path: Path, timeout: int) -> _CmdResult:
    """Execute kubectl apply --dry-run=server"""
    return _run_kubectl(
        [kubectl_bin, "apply", "--dry-run=server", "-f", str(manifest_path)],
        timeout=timeout,
    )


def _check_rbac_permissions(kubectl_bin: str, namespace: str, timeout: int) -> _RBACCheckResult:
    """
    Check RBAC using 'kubectl auth can-i' for required operations:
    - can-i get secrets -n <namespace>
    - can-i create secrets -n <namespace>
    - can-i update secrets -n <namespace>
    """
    required_verbs = ["get", "create", "update"]
    diagnostics = {}
    missing = []
    
    for verb in required_verbs:
        result = _run_kubectl(
            [kubectl_bin, "auth", "can-i", verb, "secrets", "-n", namespace],
            timeout=timeout,
        )
        allowed = result.returncode == 0 and result.stdout.strip().lower() == "yes"
        diagnostics[f"{verb}_secrets"] = allowed
        if not allowed:
            missing.append(f"{verb} secrets")
    
    return _RBACCheckResult(
        has_required_permissions=len(missing) == 0,
        missing_perms=missing,
        diagnostics=diagnostics,
    )


def _classify_dry_run_error(stderr: str) -> K8sErrorCode:
    """Classify dry-run error based on stderr content"""
    stderr_lower = stderr.lower()
    
    if "forbidden" in stderr_lower or "rbac" in stderr_lower:
        return K8sErrorCode.RBAC_DENIED
    if "timeout" in stderr_lower or "connection" in stderr_lower:
        return K8sErrorCode.CONNECT_TIMEOUT
    if "invalid" in stderr_lower or "could not parse" in stderr_lower:
        return K8sErrorCode.MANIFEST_INVALID
    if "unreachable" in stderr_lower:
        return K8sErrorCode.CLUSTER_UNREACHABLE
    
    return K8sErrorCode.DRY_RUN_FAILED


def _fetch_existing_secret(kubectl_bin: str, namespace: str, secret_name: str, timeout: int) -> str | None:
    """Fetch existing secret YAML for rollback"""
    result = _run_kubectl(
        [kubectl_bin, "get", "secret", secret_name, "-n", namespace, "-o", "yaml"],
        timeout=timeout,
    )
    return result.stdout if result.success else None


def _write_files_and_manifest(
    files: dict[str, str],
    target_dir: Path,
    namespace: str,
    secret_name: str,
) -> tuple[list[Path], Path]:
    """Write certificate files and generate k8s secret manifest"""
    target_dir.mkdir(parents=True, exist_ok=True)
    written = []
    
    for filename, content in files.items():
        path = target_dir / filename
        path.write_text(content)
        written.append(path)
    
    # Generate k8s secret manifest
    manifest = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": secret_name,
            "namespace": namespace,
        },
        "type": "kubernetes.io/tls",
        "data": {},
    }
    
    # Map certificate files
    for filename in files.keys():
        if "fullchain" in filename or "crt" in filename:
            manifest["data"]["tls.crt"] = files[filename]
        elif "privkey" in filename or "key" in filename:
            manifest["data"]["tls.key"] = files[filename]
    
    manifest_path = target_dir / "manifest.yaml"
    import yaml
    manifest_path.write_text(yaml.dump(manifest))
    
    return written, manifest_path


def deliver_k8s_bundle(
    *,
    files: dict[str, str],
    target_dir: Path,
    namespace: str = "default",
    secret_name: str = "certman-tls",
    mode: str = "render",
    rollback_on_failure: bool = True,
    kubectl_bin: str = "kubectl",
    enable_rbac_check: bool = True,
    dry_run_validation: bool = True,
    timeout: int = 30,
) -> K8sDeliveryResult:
    """
    Enhanced k8s bundle delivery with comprehensive error handling.
    
    Workflow:
    1. Write files to target_dir
    2. Generate k8s manifest
    3. (First-time) RBAC diagnostics (if enabled)
    4. Dry-run validation (if enabled & mode=apply)
    5. Real apply (if mode=apply)
    6. Rollback on failure (if enabled)
    
    Args:
        files: Dict of filename -> content
        target_dir: Directory to write files
        namespace: Kubernetes namespace
        secret_name: Name of TLS secret in k8s
        mode: "render" (just write files) or "apply" (deploy to cluster)
        rollback_on_failure: Whether to rollback on apply failure
        kubectl_bin: Path to kubectl binary
        enable_rbac_check: Whether to check RBAC permissions
        dry_run_validation: Whether to validate with --dry-run=server
        timeout: Timeout for kubectl commands
    
    Returns:
        K8sDeliveryResult with structured error info
    """
    try:
        # Phase 1: Write files + generate manifest
        written_paths, manifest_path = _write_files_and_manifest(
            files, target_dir, namespace, secret_name
        )
    except Exception as e:
        logger.error(f"Failed to write files and manifest: {e}")
        return K8sDeliveryResult(
            success=False,
            written_paths=[],
            error_code=K8sErrorCode.MANIFEST_INVALID,
            error_message=str(e),
        )
    
    # Phase 2: Render mode early return
    if mode == "render":
        return K8sDeliveryResult(success=True, written_paths=written_paths)
    
    # Phase 3: RBAC diagnostics (first-time check)
    if enable_rbac_check:
        rbac_result = _check_rbac_permissions(kubectl_bin, namespace, timeout)
        if not rbac_result.has_required_permissions:
            logger.warning(f"RBAC check failed: missing {rbac_result.missing_perms}")
            return K8sDeliveryResult(
                success=False,
                written_paths=written_paths,
                error_code=K8sErrorCode.RBAC_DENIED,
                error_message=f"Missing RBAC permissions: {', '.join(rbac_result.missing_perms)}",
                rbac_diagnostics=rbac_result.diagnostics,
            )
    
    # Phase 4: Dry-run validation
    if dry_run_validation:
        logger.info(f"Running kubectl dry-run on {manifest_path}")
        dry_run_result = _kubectl_dry_run(kubectl_bin, manifest_path, timeout)
        if not dry_run_result.success:
            error_code = _classify_dry_run_error(dry_run_result.stderr)
            logger.error(f"Dry-run failed with {error_code.value}: {dry_run_result.stderr}")
            return K8sDeliveryResult(
                success=False,
                written_paths=written_paths,
                error_code=error_code,
                error_message=dry_run_result.stderr,
                dry_run_output=dry_run_result.stdout,
            )
    
    # Phase 5: Fetch existing secret (for rollback)
    previous_manifest = _fetch_existing_secret(kubectl_bin, namespace, secret_name, timeout)
    
    # Phase 6: Real apply
    logger.info(f"Applying manifest to namespace {namespace}")
    apply_result = _run_kubectl(
        [kubectl_bin, "apply", "-f", str(manifest_path)],
        timeout=timeout,
    )
    
    if apply_result.success:
        logger.info(f"Successfully applied manifest")
        return K8sDeliveryResult(
            success=True,
            written_paths=written_paths,
            error_code=K8sErrorCode.SUCCESS,
        )
    
    # Phase 7: Rollback on failure
    if rollback_on_failure and previous_manifest:
        logger.warning(f"Apply failed, attempting rollback")
        rollback_result = _run_kubectl(
            [kubectl_bin, "apply", "-f", "-"],
            timeout=timeout,
            stdin=previous_manifest,
        )
        if not rollback_result.success:
            logger.error(f"Rollback failed: {rollback_result.stderr}")
            return K8sDeliveryResult(
                success=False,
                written_paths=written_paths,
                error_code=K8sErrorCode.ROLLBACK_FAILED,
                error_message=f"Apply failed + rollback failed: {apply_result.stderr}",
                rollback_manifest=previous_manifest,
            )
        logger.info(f"Rollback successful")
        return K8sDeliveryResult(
            success=False,
            written_paths=written_paths,
            error_code=K8sErrorCode.APPLY_FAILED,
            error_message=f"Apply failed (rolled back): {apply_result.stderr}",
        )
    
    # No rollback or no previous state
    logger.error(f"Apply failed, no rollback available")
    return K8sDeliveryResult(
        success=False,
        written_paths=written_paths,
        error_code=K8sErrorCode.APPLY_FAILED,
        error_message=apply_result.stderr,
    )

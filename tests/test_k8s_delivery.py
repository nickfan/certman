"""Unit tests for k8s delivery module."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import subprocess

from certman.delivery.k8s import (
    deliver_k8s_bundle,
    K8sErrorCode,
    _run_kubectl,
    _CmdResult,
    _check_rbac_permissions,
    _classify_dry_run_error,
)


def test_k8s_error_codes():
    """Test that all K8sErrorCode enum values are defined."""
    assert K8sErrorCode.DRY_RUN_FAILED.value == "dry_run_failed"
    assert K8sErrorCode.RBAC_DENIED.value == "rbac_denied"
    assert K8sErrorCode.APPLY_FAILED.value == "apply_failed"
    assert K8sErrorCode.ROLLBACK_FAILED.value == "rollback_failed"
    assert K8sErrorCode.CONNECT_TIMEOUT.value == "connect_timeout"


def test_run_kubectl_success():
    """Test successful kubectl command execution."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="success",
            stderr="",
        )
        result = _run_kubectl(["kubectl", "get", "pods"], timeout=30)
        assert result.success is True
        assert result.returncode == 0
        assert result.stdout == "success"


def test_run_kubectl_failure():
    """Test failed kubectl command execution."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error: not found",
        )
        result = _run_kubectl(["kubectl", "get", "pods"], timeout=30)
        assert result.success is False
        assert result.returncode == 1
        assert "error" in result.stderr


def test_run_kubectl_timeout():
    """Test kubectl command timeout."""
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)
        result = _run_kubectl(["kubectl", "get", "pods"], timeout=30)
        assert result.success is False
        assert result.returncode == -1
        assert "timeout" in result.stderr.lower()


def test_classify_dry_run_error_rbac():
    """Test error classification for RBAC errors."""
    error_code = _classify_dry_run_error("error: Forbidden (user=..., verb=apply, resource=secrets)")
    assert error_code == K8sErrorCode.RBAC_DENIED


def test_classify_dry_run_error_timeout():
    """Test error classification for timeout errors."""
    error_code = _classify_dry_run_error("error: connection timeout")
    assert error_code == K8sErrorCode.CONNECT_TIMEOUT


def test_classify_dry_run_error_invalid_manifest():
    """Test error classification for invalid manifest."""
    error_code = _classify_dry_run_error("error: could not parse manifest")
    assert error_code == K8sErrorCode.MANIFEST_INVALID


def test_deliver_k8s_bundle_render_mode(tmp_path):
    """Test k8s bundle delivery in render mode (no cluster interaction)."""
    result = deliver_k8s_bundle(
        files={"tls.crt": "CERT_DATA", "tls.key": "KEY_DATA"},
        target_dir=tmp_path,
        namespace="default",
        secret_name="test-tls",
        mode="render",
    )
    
    assert result.success is True
    assert len(result.written_paths) == 2
    assert (tmp_path / "tls.crt").exists()
    assert (tmp_path / "tls.key").exists()


def test_deliver_k8s_bundle_rbac_denied(tmp_path):
    """Test k8s bundle delivery when RBAC check fails."""
    with patch("certman.delivery.k8s._check_rbac_permissions") as mock_rbac:
        mock_rbac.return_value = MagicMock(
            has_required_permissions=False,
            missing_perms=["create secrets"],
            diagnostics={"create_secrets": False},
        )
        
        result = deliver_k8s_bundle(
            files={"tls.crt": "CERT_DATA", "tls.key": "KEY_DATA"},
            target_dir=tmp_path,
            namespace="default",
            secret_name="test-tls",
            mode="apply",
            enable_rbac_check=True,
        )
        
        assert result.success is False
        assert result.error_code == K8sErrorCode.RBAC_DENIED
        assert "RBAC" in result.error_message or "RBAC" in str(result.error_message)
        assert result.rbac_diagnostics is not None


def test_deliver_k8s_bundle_dry_run_failed(tmp_path):
    """Test k8s bundle delivery when dry-run fails."""
    with patch("certman.delivery.k8s._check_rbac_permissions") as mock_rbac:
        mock_rbac.return_value = MagicMock(
            has_required_permissions=True,
            missing_perms=[],
            diagnostics={"get_secrets": True, "create_secrets": True, "update_secrets": True},
        )
        with patch("certman.delivery.k8s._kubectl_dry_run") as mock_dry_run:
            mock_dry_run.return_value = MagicMock(
                success=False,
                returncode=1,
                stdout="",
                stderr="error: invalid manifest: unknown field xyz",
            )

            result = deliver_k8s_bundle(
                files={"tls.crt": "CERT_DATA", "tls.key": "KEY_DATA"},
                target_dir=tmp_path,
                namespace="default",
                secret_name="test-tls",
                mode="apply",
                enable_rbac_check=True,
                dry_run_validation=True,
            )

            assert result.success is False
            assert result.error_code == K8sErrorCode.MANIFEST_INVALID
            assert "invalid" in result.error_message.lower() or "unknown" in result.error_message.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

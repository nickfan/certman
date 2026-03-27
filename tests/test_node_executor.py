from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from certman.node_agent.executor import NodeExecutor
from certman.hooks.runner import HookResult


def test_node_executor_writes_files_and_runs_hooks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "certman.node_agent.executor.HookRunner.run",
        lambda self, **kwargs: HookResult(
            name=kwargs["name"],
            event=kwargs["event"],
            command=kwargs["command"],
            success=True,
            returncode=0,
            stdout="ok",
            stderr="",
            error=None,
        ),
    )

    executor = NodeExecutor()
    result = executor.execute(
        job_id="job-1",
        bundle={"files": {"cert.pem": "cert-data", "privkey.pem": "key-data"}},
        target_dir=tmp_path / "delivery",
        hooks=[{"name": "reload", "event": "certificate.updated", "command": "echo ok"}],
    )

    assert result.success is True
    assert result.status == "completed"
    assert (tmp_path / "delivery" / "cert.pem").read_text(encoding="utf-8") == "cert-data"
    assert len(result.delivered_paths) == 2


def test_node_executor_returns_failure_when_hook_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "certman.node_agent.executor.HookRunner.run",
        lambda self, **kwargs: HookResult(
            name=kwargs["name"],
            event=kwargs["event"],
            command=kwargs["command"],
            success=False,
            returncode=1,
            stdout="",
            stderr="hook failed",
            error="hook failed",
        ),
    )

    executor = NodeExecutor()
    result = executor.execute(
        job_id="job-2",
        bundle={"files": {"cert.pem": "cert-data"}},
        target_dir=tmp_path / "delivery",
        hooks=[{"name": "reload", "event": "certificate.updated", "command": "bad"}],
    )

    assert result.success is False
    assert result.status == "failed"
    assert result.error == "hook failed"


def test_node_executor_uses_k8s_ingress_adapter(tmp_path: Path) -> None:
    executor = NodeExecutor()
    result = executor.execute(
        job_id="job-3",
        bundle={
            "target_type": "k8s-ingress",
            "target_scope": "prod/web-tls",
            "files": {
                "fullchain.pem": "CERT",
                "privkey.pem": "KEY",
            },
        },
        target_dir=tmp_path / "delivery-k8s",
        hooks=[],
    )

    assert result.success is True
    manifest = tmp_path / "delivery-k8s" / "k8s-tls-secret.yaml"
    assert manifest.exists()
    content = manifest.read_text(encoding="utf-8")
    assert "namespace: prod" in content
    assert "name: web-tls" in content


def test_node_executor_k8s_apply_failure_rolls_back(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(args, capture_output, text, check, input=None):
        del capture_output, text, check
        calls.append(args)
        if args[:3] == ["kubectl", "get", "secret"]:
            return SimpleNamespace(returncode=0, stdout="apiVersion: v1\nkind: Secret\n", stderr="")
        if args[:3] == ["kubectl", "apply", "-f"] and args[-1] != "-":
            return SimpleNamespace(returncode=1, stdout="", stderr="apply failed")
        if args[:3] == ["kubectl", "apply", "-f"] and args[-1] == "-":
            return SimpleNamespace(returncode=0, stdout="rollback ok", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("certman.delivery.adapters.subprocess.run", fake_run)

    executor = NodeExecutor()
    result = executor.execute(
        job_id="job-4",
        bundle={
            "target_type": "k8s-ingress",
            "target_scope": "prod/web-tls",
            "delivery_options": {"mode": "apply", "rollback_on_failure": True},
            "files": {"fullchain.pem": "CERT", "privkey.pem": "KEY"},
        },
        target_dir=tmp_path / "delivery-k8s-apply",
        hooks=[],
    )

    assert result.success is False
    assert "rolled back" in (result.error or "")
    assert any(cmd[:3] == ["kubectl", "get", "secret"] for cmd in calls)
    assert any(cmd[:3] == ["kubectl", "apply", "-f"] and cmd[-1] == "-" for cmd in calls)

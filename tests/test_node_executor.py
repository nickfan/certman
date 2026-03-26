from __future__ import annotations

from pathlib import Path

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

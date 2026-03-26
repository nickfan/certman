from __future__ import annotations

from certman.hooks.runner import HookRunner


def test_hook_runner_returns_success_when_command_exits_zero(monkeypatch) -> None:
    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr("certman.hooks.runner.subprocess.run", lambda *args, **kwargs: Completed())

    runner = HookRunner()
    result = runner.run(name="reload", event="certificate.updated", command="echo ok")

    assert result.success is True
    assert result.returncode == 0
    assert result.stderr == ""


def test_hook_runner_returns_failure_when_command_exits_non_zero(monkeypatch) -> None:
    class Completed:
        returncode = 3
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr("certman.hooks.runner.subprocess.run", lambda *args, **kwargs: Completed())

    runner = HookRunner()
    result = runner.run(name="reload", event="certificate.updated", command="bad cmd")

    assert result.success is False
    assert result.returncode == 3
    assert result.error == "boom"
    assert result.name == "reload"


def test_hook_runner_includes_stderr_in_failure_result(monkeypatch) -> None:
    class Completed:
        returncode = 1
        stdout = ""
        stderr = "permission denied"

    monkeypatch.setattr("certman.hooks.runner.subprocess.run", lambda *args, **kwargs: Completed())

    runner = HookRunner()
    result = runner.run(name="deploy", event="certificate.updated", command="deploy-cmd")

    assert result.success is False
    assert "permission denied" in (result.error or "")
    assert result.stderr == "permission denied"

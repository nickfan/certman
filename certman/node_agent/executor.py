from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from certman.delivery.filesystem import deliver_filesystem_bundle
from certman.hooks.runner import HookRunner


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    status: str
    delivered_paths: list[Path]
    error: str | None = None


class NodeExecutor:
    def __init__(self, hook_runner: HookRunner | None = None):
        self._hook_runner = hook_runner or HookRunner()

    def execute(
        self,
        *,
        job_id: str,
        bundle: dict,
        target_dir: Path,
        hooks: list[dict] | None = None,
    ) -> ExecutionResult:
        files = bundle.get("files", {})
        delivered_paths = deliver_filesystem_bundle(files=files, target_dir=target_dir)

        for hook in hooks or []:
            result = self._hook_runner.run(
                name=hook["name"],
                event=hook["event"],
                command=hook["command"],
                shell=hook.get("shell", True),
            )
            if not result.success:
                return ExecutionResult(
                    success=False,
                    status="failed",
                    delivered_paths=delivered_paths,
                    error=result.error,
                )

        return ExecutionResult(success=True, status="completed", delivered_paths=delivered_paths)

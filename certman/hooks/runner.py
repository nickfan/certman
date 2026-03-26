from __future__ import annotations

from dataclasses import dataclass
import subprocess


@dataclass(frozen=True)
class HookResult:
    name: str
    event: str
    command: str
    success: bool
    returncode: int
    stdout: str
    stderr: str
    error: str | None = None


class HookRunner:
    def run(self, *, name: str, event: str, command: str, shell: bool = True) -> HookResult:
        completed = subprocess.run(command, shell=shell, capture_output=True, text=True)
        error = completed.stderr.strip() if completed.returncode != 0 else None
        return HookResult(
            name=name,
            event=event,
            command=command,
            success=completed.returncode == 0,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            error=error,
        )

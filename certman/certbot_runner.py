from __future__ import annotations

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess


@dataclass(frozen=True)
class CertbotPaths:
    config_dir: Path
    work_dir: Path
    logs_dir: Path


@dataclass(frozen=True)
class CertbotResult:
    cmd: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def is_admin_required_error(self) -> bool:
        msg = (self.stderr or "").lower()
        return "administrative rights" in msg or "administrator" in msg


def run_certbot(
    args: list[str],
    paths: CertbotPaths,
    *,
    passthrough: bool = False,
    env: dict[str, str | None] | None = None,
) -> CertbotResult:
    cmd = [
        "certbot",
        *args,
        "--config-dir",
        str(paths.config_dir),
        "--work-dir",
        str(paths.work_dir),
        "--logs-dir",
        str(paths.logs_dir),
        "--non-interactive",
    ]

    if not passthrough:
        proc_env = None
        if env:
            proc_env = dict(os.environ)
            for key, value in env.items():
                if value is None:
                    proc_env.pop(key, None)
                    continue
                proc_env[key] = value

        proc = subprocess.run(cmd, text=True, capture_output=True, env=proc_env)
        return CertbotResult(
            cmd=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    proc_env = None
    if env:
        proc_env = dict(os.environ)
        for key, value in env.items():
            if value is None:
                proc_env.pop(key, None)
                continue
            proc_env[key] = value

    proc = subprocess.run(cmd, text=True, env=proc_env)
    return CertbotResult(cmd=cmd, returncode=proc.returncode, stdout="", stderr="")

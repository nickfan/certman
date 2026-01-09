from __future__ import annotations

from datetime import datetime
from pathlib import Path


def ensure_log_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def new_run_logfile(log_dir: Path, command: str) -> Path:
    ensure_log_dir(log_dir)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_cmd = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in command
    )
    return log_dir / f"{ts}_{safe_cmd}.log"

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path


def cleanup_logs(log_dir: Path, keep_days: int) -> int:
    """Remove *.log older than keep_days under log_dir."""
    cutoff = datetime.now() - timedelta(days=keep_days)
    removed = 0
    if not log_dir.exists():
        return 0

    for path in log_dir.glob("*.log"):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass

    return removed

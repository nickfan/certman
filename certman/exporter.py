from __future__ import annotations

from pathlib import Path
import shutil


_EXPORT_FILES = [
    "cert.pem",
    "chain.pem",
    "fullchain.pem",
    "privkey.pem",
]


def export_entry(
    *, letsencrypt_live_dir: Path, output_entry_dir: Path, overwrite: bool
) -> list[Path]:
    """Copy certbot live files into output directory.

    Expects certbot structure: <letsencrypt>/live/<primary_domain>/<file>.
    """

    output_entry_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    for name in _EXPORT_FILES:
        src = letsencrypt_live_dir / name
        if not src.exists():
            continue

        dst = output_entry_dir / name
        if dst.exists() and not overwrite:
            continue

        shutil.copy2(src, dst)
        copied.append(dst)

    return copied

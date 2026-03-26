from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from certman.exporter import EXPORT_FILES, export_entry


@dataclass(frozen=True)
class ExportResult:
    success: bool
    copied_paths: list[Path]
    error: str | None = None


class ExportService:
    def export_from_live(
        self,
        *,
        letsencrypt_live_dir: Path,
        output_entry_dir: Path,
        overwrite: bool,
    ) -> ExportResult:
        missing_source_files = [name for name in EXPORT_FILES if not (letsencrypt_live_dir / name).exists()]
        if missing_source_files:
            return ExportResult(
                success=False,
                copied_paths=[],
                error=f"missing_source_files={','.join(missing_source_files)}",
            )

        copied = export_entry(
            letsencrypt_live_dir=letsencrypt_live_dir,
            output_entry_dir=output_entry_dir,
            overwrite=overwrite,
        )
        return ExportResult(success=True, copied_paths=copied)

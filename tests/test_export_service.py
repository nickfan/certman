from __future__ import annotations

from pathlib import Path

from certman.services.export_service import ExportService


def _write_live_files(live_dir: Path) -> None:
    live_dir.mkdir(parents=True, exist_ok=True)
    (live_dir / "cert.pem").write_text("cert", encoding="utf-8")
    (live_dir / "chain.pem").write_text("chain", encoding="utf-8")
    (live_dir / "fullchain.pem").write_text("fullchain", encoding="utf-8")
    (live_dir / "privkey.pem").write_text("privkey", encoding="utf-8")


def test_export_service_exports_all_expected_files_successfully(tmp_path: Path) -> None:
    service = ExportService()
    live_dir = tmp_path / "live" / "example.com"
    output_dir = tmp_path / "output" / "site-a"
    _write_live_files(live_dir)

    result = service.export_from_live(
        letsencrypt_live_dir=live_dir,
        output_entry_dir=output_dir,
        overwrite=True,
    )

    assert result.success is True
    assert result.error is None
    assert len(result.copied_paths) == 4
    assert (output_dir / "fullchain.pem").read_text(encoding="utf-8") == "fullchain"


def test_export_service_fails_when_any_source_file_is_missing(tmp_path: Path) -> None:
    service = ExportService()
    live_dir = tmp_path / "live" / "example.com"
    output_dir = tmp_path / "output" / "site-a"
    live_dir.mkdir(parents=True, exist_ok=True)
    (live_dir / "cert.pem").write_text("cert", encoding="utf-8")

    result = service.export_from_live(
        letsencrypt_live_dir=live_dir,
        output_entry_dir=output_dir,
        overwrite=True,
    )

    assert result.success is False
    assert result.error is not None
    assert "missing_source_files=" in result.error
    assert "chain.pem" in result.error


def test_export_service_keeps_existing_files_when_overwrite_disabled(tmp_path: Path) -> None:
    service = ExportService()
    live_dir = tmp_path / "live" / "example.com"
    output_dir = tmp_path / "output" / "site-a"
    _write_live_files(live_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cert.pem").write_text("old", encoding="utf-8")

    result = service.export_from_live(
        letsencrypt_live_dir=live_dir,
        output_entry_dir=output_dir,
        overwrite=False,
    )

    assert result.success is True
    assert result.error is None
    assert (output_dir / "cert.pem").read_text(encoding="utf-8") == "old"
    assert len(result.copied_paths) == 4

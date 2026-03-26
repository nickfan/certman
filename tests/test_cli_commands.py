from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from certman.cli import app
from certman.services.export_service import ExportResult


def test_new_command_delegates_to_service_and_export(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.yaml").write_text(
        """
run_mode: local
global:
  data_dir: data
  email: ops@example.com
entries:
  - name: site-a
    primary_domain: example.com
    dns_provider: aliyun
""".strip(),
        encoding="utf-8",
    )

    export_calls: list[tuple[bool, str | None, bool]] = []

    class FakeService:
        def issue(self, name, force=False, verbose=False):
            return type(
                "IssueResult",
                (),
                {
                    "success": True,
                    "entry_name": name,
                    "domains": ["example.com", "*.example.com"],
                    "log_path": Path("data/log/run.json"),
                    "admin_required": False,
                    "error": None,
                },
            )()

    monkeypatch.setattr("certman.cli._service", lambda ctx: FakeService())
    monkeypatch.setattr(
        "certman.cli.export",
        lambda ctx, all=False, name=None, overwrite=True: export_calls.append((all, name, overwrite)),
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "--config-file",
            "config.yaml",
            "new",
            "--name",
            "site-a",
        ],
    )

    assert result.exit_code == 0
    assert "ok: issued entry=site-a" in result.stdout
    assert export_calls == [(False, "site-a", True)]


def test_check_json_output_uses_expected_exit_code(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.yaml").write_text(
        """
run_mode: local
global:
  data_dir: data
  email: ops@example.com
entries:
  - name: site-a
    primary_domain: example.com
    dns_provider: aliyun
""".strip(),
        encoding="utf-8",
    )

    class FakeService:
        def check(self, warn_days=30, force_renew_days=7, name=None):
            return [
                {
                    "entry": "site-a",
                    "primary_domain": "example.com",
                    "status": "warn",
                    "days_left": 5,
                    "not_after": "2026-01-01T00:00:00+00:00",
                    "cert_path": "data/run/letsencrypt/live/example.com/cert.pem",
                }
            ]

    monkeypatch.setattr("certman.cli._service", lambda ctx: FakeService())

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "--config-file",
            "config.yaml",
            "check",
            "--json",
        ],
    )

    assert result.exit_code == 10
    assert '"status": "warn"' in result.stdout


def test_check_ambiguous_lineage_returns_exit_code_30(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.yaml").write_text(
        """
run_mode: local
global:
  data_dir: data
  email: ops@example.com
entries:
  - name: site-a
    primary_domain: example.com
    dns_provider: route53
""".strip(),
        encoding="utf-8",
    )

    class FakeService:
        def check(self, warn_days=30, force_renew_days=7, name=None):
            return [
                {
                    "entry": "site-a",
                    "primary_domain": "example.com",
                    "status": "missing",
                    "reason": "lineage-unresolved",
                    "error": "multiple certificate lineages match example.com; set entry.cert_name explicitly",
                    "cert_path": "data/run/letsencrypt/live/example.com/cert.pem",
                }
            ]

    monkeypatch.setattr("certman.cli._service", lambda ctx: FakeService())

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "--config-file",
            "config.yaml",
            "check",
        ],
    )

    assert result.exit_code == 30
    assert "lineage-unresolved" in result.stdout
    assert "multiple certificate lineages match example.com" in result.stdout


def test_check_fix_skips_unresolved_lineage(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.yaml").write_text(
        """
run_mode: local
global:
  data_dir: data
  email: ops@example.com
entries:
  - name: site-a
    primary_domain: example.com
    dns_provider: route53
""".strip(),
        encoding="utf-8",
    )

    calls: list[tuple[str, str]] = []

    class FakeService:
        def check(self, warn_days=30, force_renew_days=7, name=None):
            return [
                {
                    "entry": "site-a",
                    "primary_domain": "example.com",
                    "status": "missing",
                    "reason": "lineage-unresolved",
                    "error": "multiple certificate lineages match example.com; set entry.cert_name explicitly",
                    "cert_path": "data/run/letsencrypt/live/example.com/cert.pem",
                }
            ]

    monkeypatch.setattr("certman.cli._service", lambda ctx: FakeService())
    monkeypatch.setattr("certman.cli.new", lambda *args, **kwargs: calls.append(("new", kwargs["name"])))
    monkeypatch.setattr("certman.cli.renew", lambda *args, **kwargs: calls.append(("renew", kwargs["name"])))

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "--config-file",
            "config.yaml",
            "check",
            "--fix",
        ],
    )

    assert result.exit_code == 30
    assert calls == []


def test_check_fix_runs_new_for_cert_missing(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.yaml").write_text(
        """
run_mode: local
global:
  data_dir: data
  email: ops@example.com
entries:
  - name: site-a
    primary_domain: example.com
    dns_provider: route53
""".strip(),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, bool]] = []

    class FakeService:
        def check(self, warn_days=30, force_renew_days=7, name=None):
            return [
                {
                    "entry": "site-a",
                    "primary_domain": "example.com",
                    "status": "missing",
                    "reason": "cert-missing",
                    "cert_name": "example.com",
                    "cert_path": "data/run/letsencrypt/live/example.com/cert.pem",
                }
            ]

    monkeypatch.setattr("certman.cli._service", lambda ctx: FakeService())
    monkeypatch.setattr(
        "certman.cli.new",
        lambda *args, **kwargs: calls.append(("new", kwargs["name"], kwargs["force"])),
    )
    monkeypatch.setattr(
        "certman.cli.renew",
        lambda *args, **kwargs: calls.append(("renew", kwargs["name"], kwargs["force"])),
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "--config-file",
            "config.yaml",
            "check",
            "--fix",
        ],
    )

    assert result.exit_code == 30
    assert calls == [("new", "site-a", True)]
    assert "fix actions:" in result.stdout
    assert "- new --name site-a --force" in result.stdout


def test_check_fix_runs_renew_for_force_renew(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.yaml").write_text(
        """
run_mode: local
global:
  data_dir: data
  email: ops@example.com
entries:
  - name: site-a
    primary_domain: example.com
    dns_provider: route53
""".strip(),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, bool]] = []

    class FakeService:
        def check(self, warn_days=30, force_renew_days=7, name=None):
            return [
                {
                    "entry": "site-a",
                    "primary_domain": "example.com",
                    "status": "force-renew",
                    "days_left": 1,
                    "not_after": "2026-01-01T00:00:00+00:00",
                    "cert_path": "data/run/letsencrypt/live/example.com/cert.pem",
                }
            ]

    monkeypatch.setattr("certman.cli._service", lambda ctx: FakeService())
    monkeypatch.setattr(
        "certman.cli.new",
        lambda *args, **kwargs: calls.append(("new", kwargs["name"], kwargs["force"])),
    )
    monkeypatch.setattr(
        "certman.cli.renew",
        lambda *args, **kwargs: calls.append(("renew", kwargs["name"], kwargs["force"])),
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "--config-file",
            "config.yaml",
            "check",
            "--fix",
        ],
    )

    assert result.exit_code == 20
    assert calls == [("renew", "site-a", True)]
    assert "fix actions:" in result.stdout
    assert "- renew --name site-a --force" in result.stdout


def test_check_json_output_includes_missing_reason_and_error(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.yaml").write_text(
        """
run_mode: local
global:
  data_dir: data
  email: ops@example.com
entries:
  - name: site-a
    primary_domain: example.com
    dns_provider: route53
""".strip(),
        encoding="utf-8",
    )

    class FakeService:
        def check(self, warn_days=30, force_renew_days=7, name=None):
            return [
                {
                    "entry": "site-a",
                    "primary_domain": "example.com",
                    "status": "missing",
                    "reason": "lineage-unresolved",
                    "error": "multiple certificate lineages match example.com; set entry.cert_name explicitly",
                    "cert_path": "",
                }
            ]

    monkeypatch.setattr("certman.cli._service", lambda ctx: FakeService())

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "--config-file",
            "config.yaml",
            "check",
            "--json",
        ],
    )

    assert result.exit_code == 30
    assert '"reason": "lineage-unresolved"' in result.stdout
    assert '"error": "multiple certificate lineages match example.com; set entry.cert_name explicitly"' in result.stdout


def test_renew_all_does_not_export_on_partial_failure(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.yaml").write_text(
        """
run_mode: local
global:
  data_dir: data
  email: ops@example.com
entries:
  - name: site-a
    primary_domain: example.com
    dns_provider: aliyun
  - name: site-b
    primary_domain: example.org
    dns_provider: route53
""".strip(),
        encoding="utf-8",
    )

    export_calls: list[tuple[bool, str | None, bool]] = []

    class FakeService:
        def renew(self, all=False, name=None, force=False, dry_run=False, verbose=False):
            return [
                type(
                    "RenewResult",
                    (),
                    {
                        "success": True,
                        "entry_name": "site-a",
                        "renewed": True,
                        "log_path": Path("data/log/site-a.json"),
                        "dry_run": False,
                        "admin_required": False,
                        "error": None,
                    },
                )(),
                type(
                    "RenewResult",
                    (),
                    {
                        "success": False,
                        "entry_name": "site-b",
                        "renewed": False,
                        "log_path": Path("data/log/site-b.json"),
                        "dry_run": False,
                        "admin_required": False,
                        "error": "renew failed",
                    },
                )(),
            ]

    monkeypatch.setattr("certman.cli._service", lambda ctx: FakeService())
    monkeypatch.setattr(
        "certman.cli.export",
        lambda ctx, all=False, name=None, overwrite=True: export_calls.append((all, name, overwrite)),
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "--config-file",
            "config.yaml",
            "renew",
            "--all",
        ],
    )

    assert result.exit_code == 1
    assert "ok: renewed entry=site-a" in result.stdout
    assert "renew failed" in result.stdout
    assert export_calls == []


def test_export_uses_cert_name_override(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.yaml").write_text(
        """
run_mode: local
global:
  data_dir: data
  email: ops@example.com
entries:
  - name: site-a
    primary_domain: example.com
    cert_name: example.com-0001
    dns_provider: route53
""".strip(),
        encoding="utf-8",
    )

    captured: dict[str, Path] = {}

    def fake_export_from_live(*, letsencrypt_live_dir, output_entry_dir, overwrite):
        captured["live_dir"] = letsencrypt_live_dir
        captured["output_dir"] = output_entry_dir
        return ExportResult(success=True, copied_paths=[])

    monkeypatch.setattr("certman.cli._export_service.export_from_live", fake_export_from_live)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "--config-file",
            "config.yaml",
            "export",
            "--name",
            "site-a",
        ],
    )

    assert result.exit_code == 1
    assert "No certificate files were exported" in result.stdout
    assert captured["live_dir"].as_posix().endswith("run/letsencrypt/live/example.com-0001")


def test_export_succeeds_when_files_are_copied(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.yaml").write_text(
        """
run_mode: local
global:
  data_dir: data
  email: ops@example.com
entries:
  - name: site-a
    primary_domain: example.com
    cert_name: example.com-0001
    dns_provider: route53
""".strip(),
        encoding="utf-8",
    )

    renewal_dir = data_dir / "run" / "letsencrypt" / "renewal"
    renewal_dir.mkdir(parents=True, exist_ok=True)
    (renewal_dir / "example.com-0001.conf").write_text("x", encoding="utf-8")
    live_dir = data_dir / "run" / "letsencrypt" / "live" / "example.com-0001"
    live_dir.mkdir(parents=True, exist_ok=True)
    (live_dir / "cert.pem").write_text("dummy", encoding="utf-8")
    monkeypatch.setattr(
        "certman.cli._export_service.export_from_live",
        lambda **kwargs: ExportResult(success=True, copied_paths=[Path("data/output/site-a/cert.pem")]),
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "--config-file",
            "config.yaml",
            "export",
            "--name",
            "site-a",
        ],
    )

    assert result.exit_code == 0
    assert "Exported 1 file(s)" in result.stdout


def test_export_all_fails_when_any_entry_exports_no_files(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    conf_dir = data_dir / "conf"
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.yaml").write_text(
        """
run_mode: local
global:
  data_dir: data
  email: ops@example.com
entries:
  - name: site-a
    primary_domain: a.example.com
    cert_name: a.example.com-0001
    dns_provider: route53
  - name: site-b
    primary_domain: b.example.com
    cert_name: b.example.com-0001
    dns_provider: route53
""".strip(),
        encoding="utf-8",
    )

    renewal_dir = data_dir / "run" / "letsencrypt" / "renewal"
    renewal_dir.mkdir(parents=True, exist_ok=True)
    (renewal_dir / "a.example.com-0001.conf").write_text("x", encoding="utf-8")
    (renewal_dir / "b.example.com-0001.conf").write_text("x", encoding="utf-8")

    def fake_export_from_live(*, letsencrypt_live_dir, output_entry_dir, overwrite):
        if letsencrypt_live_dir.as_posix().endswith("a.example.com-0001"):
            return ExportResult(
                success=True,
                copied_paths=[Path("data/output/site-a/cert.pem"), Path("data/output/site-a/chain.pem")],
            )
        return ExportResult(success=True, copied_paths=[])

    for cert_name in ["a.example.com-0001", "b.example.com-0001"]:
        live_dir = data_dir / "run" / "letsencrypt" / "live" / cert_name
        live_dir.mkdir(parents=True, exist_ok=True)
        if cert_name == "a.example.com-0001":
            (live_dir / "cert.pem").write_text("dummy", encoding="utf-8")
            (live_dir / "chain.pem").write_text("dummy", encoding="utf-8")

    monkeypatch.setattr("certman.cli._export_service.export_from_live", fake_export_from_live)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "--config-file",
            "config.yaml",
            "export",
            "--all",
        ],
    )

    assert result.exit_code == 1
    assert "Exported 2 file(s)" in result.stdout
    assert "entry=site-b no files exported" in result.stdout


def test_export_no_overwrite_succeeds_when_output_already_exists(monkeypatch, tmp_path: Path) -> None:
    live_dir = tmp_path / "live"
    out_dir = tmp_path / "out"
    live_dir.mkdir(parents=True)
    out_dir.mkdir(parents=True)
    for name in ["cert.pem", "chain.pem", "fullchain.pem", "privkey.pem"]:
        (live_dir / name).write_text("src", encoding="utf-8")
        (out_dir / name).write_text("dst", encoding="utf-8")

    from certman.exporter import export_entry

    copied = export_entry(
        letsencrypt_live_dir=live_dir,
        output_entry_dir=out_dir,
        overwrite=False,
    )

    assert len(copied) == 4
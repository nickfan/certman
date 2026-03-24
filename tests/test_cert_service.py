from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from certman.config import AppConfig, Paths, Runtime
from certman.services.cert_service import CertService


def _runtime(tmp_path: Path) -> Runtime:
    data_dir = tmp_path / "data"
    paths = Paths(
        data_dir=data_dir,
        conf_dir=data_dir / "conf",
        run_dir=data_dir / "run",
        log_dir=data_dir / "log",
        output_dir=data_dir / "output",
    )
    config = AppConfig.model_validate(
        {
            "global": {"email": "ops@example.com"},
            "entries": [
                {
                    "name": "site-a",
                    "primary_domain": "example.com",
                    "dns_provider": "aliyun",
                }
            ],
        }
    )
    return Runtime(paths=paths, config=config, env={})


def test_issue_uses_entry_and_returns_domains(monkeypatch, tmp_path: Path) -> None:
    service = CertService(_runtime(tmp_path))

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""
        cmd = ["certbot"]

        @property
        def ok(self):
            return True

        def is_admin_required_error(self) -> bool:
            return False

    monkeypatch.setattr(
        "certman.services.cert_service.aliyun_credentials_for_entry",
        lambda entry: type("Creds", (), {"access_key_id": "ak", "access_key_secret": "sk"})(),
    )
    monkeypatch.setattr(
        "certman.services.cert_service.write_aliyun_credentials_ini",
        lambda path, creds: path.parent.mkdir(parents=True, exist_ok=True) or path.write_text("x", encoding="utf-8"),
    )
    monkeypatch.setattr(
        "certman.services.cert_service.run_certbot",
        lambda args, paths, passthrough=False, env=None: Result(),
    )

    result = service.issue("site-a")

    assert result.success is True
    assert result.entry_name == "site-a"
    assert result.domains == ["example.com", "*.example.com"]


def test_renew_single_entry_returns_success(monkeypatch, tmp_path: Path) -> None:
    service = CertService(_runtime(tmp_path))
    renewal_dir = service._runtime.paths.run_dir / service._runtime.config.global_.letsencrypt_dir / "renewal"
    renewal_dir.mkdir(parents=True, exist_ok=True)
    (renewal_dir / "example.com.conf").write_text("x", encoding="utf-8")

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""
        cmd = ["certbot", "renew"]

        @property
        def ok(self):
            return True

        def is_admin_required_error(self) -> bool:
            return False

    monkeypatch.setattr(
        "certman.services.cert_service.aliyun_credentials_for_entry",
        lambda entry: type("Creds", (), {"access_key_id": "ak", "access_key_secret": "sk"})(),
    )
    monkeypatch.setattr(
        "certman.services.cert_service.write_aliyun_credentials_ini",
        lambda path, creds: path.parent.mkdir(parents=True, exist_ok=True) or path.write_text("x", encoding="utf-8"),
    )
    monkeypatch.setattr(
        "certman.services.cert_service.run_certbot",
        lambda args, paths, passthrough=False, env=None: Result(),
    )

    results = service.renew(name="site-a")

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].entry_name == "site-a"


def test_renew_all_route53_runs_each_entry_with_isolated_env(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    paths = Paths(
        data_dir=data_dir,
        conf_dir=data_dir / "conf",
        run_dir=data_dir / "run",
        log_dir=data_dir / "log",
        output_dir=data_dir / "output",
    )
    config = AppConfig.model_validate(
        {
            "global": {"email": "ops@example.com"},
            "entries": [
                {
                    "name": "site-a",
                    "primary_domain": "example.com",
                    "dns_provider": "route53",
                    "account_id": "a",
                },
                {
                    "name": "site-b",
                    "primary_domain": "example.org",
                    "dns_provider": "route53",
                    "account_id": "b",
                },
            ],
        }
    )
    service = CertService(Runtime(paths=paths, config=config, env={}))
    renewal_dir = paths.run_dir / "letsencrypt" / "renewal"
    renewal_dir.mkdir(parents=True, exist_ok=True)
    (renewal_dir / "example.com.conf").write_text("x", encoding="utf-8")
    (renewal_dir / "example.org.conf").write_text("x", encoding="utf-8")
    calls: list[dict[str, object]] = []

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

        def __init__(self, cmd: list[str]):
            self.cmd = cmd

        @property
        def ok(self):
            return True

        def is_admin_required_error(self) -> bool:
            return False

    def fake_route53_credentials(entry):
        if entry.account_id == "a":
            return type(
                "Creds",
                (),
                {
                    "access_key_id": "aws-ak-a",
                    "secret_access_key": "aws-sk-a",
                    "region": "us-east-1",
                },
            )()
        return type(
            "Creds",
            (),
            {
                "access_key_id": "aws-ak-b",
                "secret_access_key": "aws-sk-b",
                "region": "us-west-2",
            },
        )()

    def fake_run_certbot(args, paths, passthrough=False, env=None):
        calls.append({"args": list(args), "env": dict(env or {})})
        return Result(["certbot", *args])

    monkeypatch.setattr(
        "certman.services.cert_service.route53_credentials_for_entry",
        fake_route53_credentials,
    )
    monkeypatch.setattr("certman.services.cert_service.run_certbot", fake_run_certbot)

    results = service.renew(all=True, dry_run=True, force=True)

    assert [result.entry_name for result in results] == ["site-a", "site-b"]
    assert len(calls) == 2
    assert calls[0]["args"] == [
        "renew",
        "--cert-name",
        "example.com",
        "--force-renewal",
        "--dry-run",
    ]
    assert calls[1]["args"] == [
        "renew",
        "--cert-name",
        "example.org",
        "--force-renewal",
        "--dry-run",
    ]
    assert calls[0]["env"]["AWS_ACCESS_KEY_ID"] == "aws-ak-a"
    assert calls[1]["env"]["AWS_ACCESS_KEY_ID"] == "aws-ak-b"
    assert calls[0]["env"]["AWS_PROFILE"] is None
    assert calls[1]["env"]["AWS_PROFILE"] is None


def test_renew_uses_cert_name_override_for_legacy_lineage(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    paths = Paths(
        data_dir=data_dir,
        conf_dir=data_dir / "conf",
        run_dir=data_dir / "run",
        log_dir=data_dir / "log",
        output_dir=data_dir / "output",
    )
    config = AppConfig.model_validate(
        {
            "global": {"email": "ops@example.com"},
            "entries": [
                {
                    "name": "site-a",
                    "primary_domain": "example.com",
                    "cert_name": "example.com-0001",
                    "dns_provider": "route53",
                    "account_id": "a",
                }
            ],
        }
    )
    service = CertService(Runtime(paths=paths, config=config, env={}))
    captured: dict[str, object] = {}

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""
        cmd = ["certbot", "renew"]

        @property
        def ok(self):
            return True

        def is_admin_required_error(self) -> bool:
            return False

    monkeypatch.setattr(
        "certman.services.cert_service.route53_credentials_for_entry",
        lambda entry: type(
            "Creds",
            (),
            {
                "access_key_id": "aws-ak",
                "secret_access_key": "aws-sk",
                "region": "us-east-1",
            },
        )(),
    )

    def fake_run_certbot(args, paths, passthrough=False, env=None):
        captured["args"] = list(args)
        return Result()

    monkeypatch.setattr("certman.services.cert_service.run_certbot", fake_run_certbot)

    results = service.renew(name="site-a")

    assert results[0].success is True
    assert captured["args"][:3] == ["renew", "--cert-name", "example.com-0001"]


def test_check_uses_cert_name_override_path(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    paths = Paths(
        data_dir=data_dir,
        conf_dir=data_dir / "conf",
        run_dir=data_dir / "run",
        log_dir=data_dir / "log",
        output_dir=data_dir / "output",
    )
    config = AppConfig.model_validate(
        {
            "global": {"email": "ops@example.com"},
            "entries": [
                {
                    "name": "site-a",
                    "primary_domain": "example.com",
                    "cert_name": "example.com-0001",
                    "dns_provider": "route53",
                }
            ],
        }
    )
    cert_path = paths.run_dir / "letsencrypt" / "live" / "example.com-0001"
    cert_path.mkdir(parents=True, exist_ok=True)
    (cert_path / "cert.pem").write_text("dummy", encoding="utf-8")
    service = CertService(Runtime(paths=paths, config=config, env={}))
    captured: dict[str, Path] = {}

    status = type(
        "Status",
        (),
        {"days_left": 40, "not_after": datetime(2026, 1, 1, tzinfo=timezone.utc)},
    )()

    def fake_get_cert_status(path: Path):
        captured["path"] = path
        return status

    monkeypatch.setattr("certman.services.cert_service.get_cert_status", fake_get_cert_status)

    results = service.check(name="site-a")

    assert results[0]["status"] == "ok"
    assert results[0]["cert_name"] == "example.com-0001"
    assert captured["path"] == cert_path / "cert.pem"


def test_check_returns_missing_for_ambiguous_lineage(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    paths = Paths(
        data_dir=data_dir,
        conf_dir=data_dir / "conf",
        run_dir=data_dir / "run",
        log_dir=data_dir / "log",
        output_dir=data_dir / "output",
    )
    renewal_dir = paths.run_dir / "letsencrypt" / "renewal"
    renewal_dir.mkdir(parents=True, exist_ok=True)
    (renewal_dir / "example.com.conf").write_text("x", encoding="utf-8")
    (renewal_dir / "example.com-0001.conf").write_text("x", encoding="utf-8")
    config = AppConfig.model_validate(
        {
            "global": {"email": "ops@example.com"},
            "entries": [
                {
                    "name": "site-a",
                    "primary_domain": "example.com",
                    "dns_provider": "route53",
                }
            ],
        }
    )
    service = CertService(Runtime(paths=paths, config=config, env={}))

    results = service.check(name="site-a")

    assert results[0]["status"] == "missing"
    assert results[0]["reason"] == "lineage-unresolved"
    assert "multiple certificate lineages match example.com" in results[0]["error"]


def test_renew_raises_for_ambiguous_lineage_candidates(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    paths = Paths(
        data_dir=data_dir,
        conf_dir=data_dir / "conf",
        run_dir=data_dir / "run",
        log_dir=data_dir / "log",
        output_dir=data_dir / "output",
    )
    renewal_dir = paths.run_dir / "letsencrypt" / "renewal"
    renewal_dir.mkdir(parents=True, exist_ok=True)
    (renewal_dir / "example.com-0001.conf").write_text("x", encoding="utf-8")
    (renewal_dir / "example.com-0002.conf").write_text("x", encoding="utf-8")
    config = AppConfig.model_validate(
        {
            "global": {"email": "ops@example.com"},
            "entries": [
                {
                    "name": "site-a",
                    "primary_domain": "example.com",
                    "dns_provider": "route53",
                    "account_id": "a",
                }
            ],
        }
    )
    service = CertService(Runtime(paths=paths, config=config, env={}))

    monkeypatch.setattr(
        "certman.services.cert_service.route53_credentials_for_entry",
        lambda entry: type(
            "Creds",
            (),
            {
                "access_key_id": "aws-ak",
                "secret_access_key": "aws-sk",
                "region": "us-east-1",
            },
        )(),
    )

    try:
        service.renew(name="site-a")
    except ValueError as exc:
        assert "multiple certificate lineages match example.com" in str(exc)
    else:
        raise AssertionError("expected ValueError for ambiguous lineage candidates")


def test_renew_raises_when_exact_and_suffix_lineages_coexist(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    paths = Paths(
        data_dir=data_dir,
        conf_dir=data_dir / "conf",
        run_dir=data_dir / "run",
        log_dir=data_dir / "log",
        output_dir=data_dir / "output",
    )
    renewal_dir = paths.run_dir / "letsencrypt" / "renewal"
    renewal_dir.mkdir(parents=True, exist_ok=True)
    (renewal_dir / "example.com.conf").write_text("x", encoding="utf-8")
    (renewal_dir / "example.com-0001.conf").write_text("x", encoding="utf-8")
    config = AppConfig.model_validate(
        {
            "global": {"email": "ops@example.com"},
            "entries": [
                {
                    "name": "site-a",
                    "primary_domain": "example.com",
                    "dns_provider": "route53",
                    "account_id": "a",
                }
            ],
        }
    )
    service = CertService(Runtime(paths=paths, config=config, env={}))

    monkeypatch.setattr(
        "certman.services.cert_service.route53_credentials_for_entry",
        lambda entry: type(
            "Creds",
            (),
            {
                "access_key_id": "aws-ak",
                "secret_access_key": "aws-sk",
                "region": "us-east-1",
            },
        )(),
    )

    try:
        service.renew(name="site-a")
    except ValueError as exc:
        assert "multiple certificate lineages match example.com" in str(exc)
    else:
        raise AssertionError("expected ValueError for mixed exact and suffix lineages")


def test_renew_all_preflights_all_entries_before_executing(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    paths = Paths(
        data_dir=data_dir,
        conf_dir=data_dir / "conf",
        run_dir=data_dir / "run",
        log_dir=data_dir / "log",
        output_dir=data_dir / "output",
    )
    renewal_dir = paths.run_dir / "letsencrypt" / "renewal"
    renewal_dir.mkdir(parents=True, exist_ok=True)
    (renewal_dir / "bad.example.com.conf").write_text("x", encoding="utf-8")
    (renewal_dir / "bad.example.com-0001.conf").write_text("x", encoding="utf-8")
    config = AppConfig.model_validate(
        {
            "global": {"email": "ops@example.com"},
            "entries": [
                {
                    "name": "site-a",
                    "primary_domain": "good.example.com",
                    "dns_provider": "route53",
                    "account_id": "a",
                    "cert_name": "good.example.com-0001",
                },
                {
                    "name": "site-b",
                    "primary_domain": "bad.example.com",
                    "dns_provider": "route53",
                    "account_id": "b",
                },
            ],
        }
    )
    service = CertService(Runtime(paths=paths, config=config, env={}))
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "certman.services.cert_service.route53_credentials_for_entry",
        lambda entry: type(
            "Creds",
            (),
            {
                "access_key_id": f"aws-ak-{entry.account_id}",
                "secret_access_key": f"aws-sk-{entry.account_id}",
                "region": "us-east-1",
            },
        )(),
    )
    monkeypatch.setattr(
        "certman.services.cert_service.run_certbot",
        lambda args, paths, passthrough=False, env=None: calls.append(list(args)),
    )

    try:
        service.renew(all=True)
    except ValueError as exc:
        assert "multiple certificate lineages match bad.example.com" in str(exc)
    else:
        raise AssertionError("expected ValueError for ambiguous batch renew")

    assert calls == []


def test_renew_all_fails_before_execution_when_lineage_missing(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    paths = Paths(
        data_dir=data_dir,
        conf_dir=data_dir / "conf",
        run_dir=data_dir / "run",
        log_dir=data_dir / "log",
        output_dir=data_dir / "output",
    )
    config = AppConfig.model_validate(
        {
            "global": {"email": "ops@example.com"},
            "entries": [
                {
                    "name": "site-a",
                    "primary_domain": "missing.example.com",
                    "dns_provider": "route53",
                    "account_id": "a",
                }
            ],
        }
    )
    service = CertService(Runtime(paths=paths, config=config, env={}))
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "certman.services.cert_service.route53_credentials_for_entry",
        lambda entry: type(
            "Creds",
            (),
            {
                "access_key_id": "aws-ak",
                "secret_access_key": "aws-sk",
                "region": "us-east-1",
            },
        )(),
    )
    monkeypatch.setattr(
        "certman.services.cert_service.run_certbot",
        lambda args, paths, passthrough=False, env=None: calls.append(list(args)),
    )

    try:
        service.renew(all=True)
    except ValueError as exc:
        assert "renewal config not found for missing.example.com" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing lineage during batch renew")

    assert calls == []


def test_check_returns_expiry_status(monkeypatch, tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    cert_path = runtime.paths.run_dir / runtime.config.global_.letsencrypt_dir / "live" / "example.com"
    cert_path.mkdir(parents=True, exist_ok=True)
    (cert_path / "cert.pem").write_text("dummy", encoding="utf-8")
    service = CertService(runtime)

    status = type(
        "Status",
        (),
        {"days_left": 15, "not_after": datetime(2026, 1, 1, tzinfo=timezone.utc)},
    )()
    monkeypatch.setattr("certman.services.cert_service.get_cert_status", lambda path: status)

    results = service.check(name="site-a")

    assert results[0]["status"] == "warn"
    assert results[0]["entry"] == "site-a"


def test_issue_route53_uses_aws_env_not_invalid_certbot_flag(monkeypatch, tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.config.entries[0].dns_provider = "route53"
    service = CertService(runtime)
    captured: dict[str, object] = {}

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""
        cmd = ["certbot"]

        @property
        def ok(self):
            return True

        def is_admin_required_error(self) -> bool:
            return False

    monkeypatch.setattr(
        "certman.services.cert_service.route53_credentials_for_entry",
        lambda entry: type(
            "Creds",
            (),
            {
                "access_key_id": "aws-ak",
                "secret_access_key": "aws-sk",
                "region": "ap-southeast-1",
            },
        )(),
    )

    def fake_run_certbot(args, paths, passthrough=False, env=None):
        captured["args"] = args
        captured["env"] = env
        return Result()

    monkeypatch.setattr("certman.services.cert_service.run_certbot", fake_run_certbot)

    result = service.issue("site-a")

    assert result.success is True
    assert "--dns-route53-config" not in captured["args"]
    assert captured["env"]["AWS_ACCESS_KEY_ID"] == "aws-ak"
    assert captured["env"]["AWS_SECRET_ACCESS_KEY"] == "aws-sk"
    assert captured["env"]["AWS_DEFAULT_REGION"] == "ap-southeast-1"
    assert captured["env"]["AWS_PROFILE"] is None
    assert captured["env"]["AWS_SHARED_CREDENTIALS_FILE"] is None


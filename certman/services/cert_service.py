from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from certman.certbot_runner import CertbotPaths, run_certbot
from certman.certs import get_cert_status
from certman.config import Runtime, entry_domains
from certman.providers import (
    aliyun_credentials_for_entry,
    cloudflare_credentials_for_entry,
    route53_credentials_for_entry,
    write_aliyun_credentials_ini,
    write_cloudflare_credentials_ini,
)
from certman.runtime_logging import new_run_logfile


@dataclass(frozen=True)
class IssueResult:
    success: bool
    entry_name: str
    domains: list[str]
    log_path: Path
    admin_required: bool = False
    error: str | None = None


@dataclass(frozen=True)
class RenewResult:
    success: bool
    entry_name: str
    renewed: bool
    log_path: Path
    dry_run: bool = False
    admin_required: bool = False
    error: str | None = None


@dataclass(frozen=True)
class RenewPlan:
    entry: object
    cert_name: str
    env_overrides: dict[str, str | None]


def _write_command_log(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_entry_cert_name(
    runtime: Runtime,
    entry,
    *,
    require_existing_lineage: bool = False,
    resolution_mode: Literal["latest", "strict"] = "latest",
) -> str:
    if entry.cert_name:
        return entry.cert_name

    renewal_dir = runtime.paths.run_dir / runtime.config.global_.letsencrypt_dir / "renewal"
    exact_path = renewal_dir / f"{entry.primary_domain}.conf"
    matches = sorted(renewal_dir.glob(f"{entry.primary_domain}-*.conf"))

    candidates: list[Path] = []
    if exact_path.exists():
        candidates.append(exact_path)
    candidates.extend(matches)

    if resolution_mode == "strict":
        if exact_path.exists() and matches:
            raise ValueError(
                f"multiple certificate lineages match {entry.primary_domain}; set entry.cert_name explicitly"
            )
        if exact_path.exists():
            return entry.primary_domain
        if len(matches) == 1:
            return matches[0].stem
        if len(matches) > 1:
            raise ValueError(
                f"multiple certificate lineages match {entry.primary_domain}; set entry.cert_name explicitly"
            )
    elif resolution_mode == "latest":
        if candidates:
            latest = max(candidates, key=lambda p: (p.stat().st_mtime_ns, p.name))
            return entry.primary_domain if latest == exact_path else latest.stem
    else:
        raise ValueError(f"unsupported lineage resolution_mode: {resolution_mode}")

    if require_existing_lineage:
        raise ValueError(
            f"renewal config not found for {entry.primary_domain}; issue the certificate first or set entry.cert_name explicitly"
        )

    return entry.primary_domain


class CertService:
    def __init__(self, runtime: Runtime):
        self._runtime = runtime

    def issue(self, name: str, *, force: bool = False, verbose: bool = False) -> IssueResult:
        entry = self._get_entry(name)
        paths = self._certbot_paths()
        provider = entry.dns_provider.lower()
        domains = entry_domains(entry)
        env_overrides: dict[str, str] = {}

        if provider == "aliyun":
            cred_file = self._prepare_aliyun_credentials_ini(entry)
            auth_args = [
                "--authenticator",
                "dns-aliyun",
                "--dns-aliyun-credentials",
                str(cred_file),
            ]
        elif provider == "cloudflare":
            cred_file = self._prepare_cloudflare_credentials_ini(entry)
            auth_args = [
                "--authenticator",
                "dns-cloudflare",
                "--dns-cloudflare-credentials",
                str(cred_file),
            ]
        elif provider == "route53":
            auth_args = [
                "--authenticator",
                "dns-route53",
            ]
            env_overrides = self._route53_env(entry)
        else:
            raise ValueError(f"unsupported dns_provider: {entry.dns_provider}")

        args: list[str] = [
            "certonly",
            *auth_args,
            "--agree-tos",
            "--email",
            self._runtime.config.global_.email,
        ]

        if self._runtime.config.global_.acme_server == "staging":
            args.append("--test-cert")

        if force:
            args.append("--force-renewal")

        for domain in domains:
            args.extend(["-d", domain])

        log_path = new_run_logfile(self._runtime.paths.log_dir, command="new")
        result = run_certbot(
            args,
            paths=paths,
            passthrough=verbose,
            env=env_overrides or None,
        )
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "command": "new",
            "entry": entry.name,
            "domains": domains,
            "provider": provider,
            "certbot": {
                "returncode": result.returncode,
                "cmd": result.cmd,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
        }
        _write_command_log(log_path, payload)

        return IssueResult(
            success=result.ok,
            entry_name=entry.name,
            domains=domains,
            log_path=log_path,
            admin_required=result.is_admin_required_error(),
            error=None if result.ok else (result.stderr or result.stdout or "certbot failed"),
        )

    def renew(
        self,
        *,
        all: bool = False,
        name: str | None = None,
        force: bool = False,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> list[RenewResult]:
        if not all and not name:
            raise ValueError("must provide --all or --name")
        targets = self._runtime.config.entries if all else [self._get_entry(name or "")]
        if not targets:
            raise ValueError("no entries configured")

        return [
            self._renew_entry(
                plan,
                force=force,
                dry_run=dry_run,
                verbose=verbose,
            )
            for plan in [self._build_renew_plan(entry) for entry in targets]
        ]

    def check(
        self,
        *,
        warn_days: int = 30,
        force_renew_days: int = 7,
        name: str | None = None,
    ) -> list[dict]:
        targets = self._runtime.config.entries
        if name:
            targets = [entry for entry in targets if entry.name == name]
            if not targets:
                return [
                    {
                        "entry": name,
                        "cert_name": None,
                        "primary_domain": None,
                        "status": "missing",
                        "reason": "entry-not-found",
                        "error": f"entry not found: {name}",
                        "cert_path": "",
                    }
                ]

        letsencrypt_dir = self._runtime.paths.run_dir / self._runtime.config.global_.letsencrypt_dir
        results: list[dict] = []
        for entry in targets:
            try:
                cert_name = resolve_entry_cert_name(self._runtime, entry)
            except ValueError as exc:
                results.append(
                    {
                        "entry": entry.name,
                        "cert_name": None,
                        "primary_domain": entry.primary_domain,
                        "status": "missing",
                        "reason": "lineage-unresolved",
                        "error": str(exc),
                        "cert_path": "",
                    }
                )
                continue

            cert_path = letsencrypt_dir / "live" / cert_name / "cert.pem"
            if not cert_path.exists():
                results.append(
                    {
                        "entry": entry.name,
                        "cert_name": cert_name,
                        "primary_domain": entry.primary_domain,
                        "status": "missing",
                        "reason": "cert-missing",
                        "cert_path": str(cert_path),
                    }
                )
                continue

            status = get_cert_status(cert_path)
            state = "ok"
            if status.days_left <= force_renew_days:
                state = "force-renew"
            elif status.days_left <= warn_days:
                state = "warn"

            results.append(
                {
                    "entry": entry.name,
                    "cert_name": cert_name,
                    "primary_domain": entry.primary_domain,
                    "status": state,
                    "days_left": status.days_left,
                    "not_after": status.not_after.isoformat(),
                    "cert_path": str(cert_path),
                }
            )
        return results

    def _get_entry(self, name: str):
        targets = [entry for entry in self._runtime.config.entries if entry.name == name]
        if not targets:
            raise ValueError(f"entry not found: {name}")
        return targets[0]

    def _certbot_paths(self) -> CertbotPaths:
        letsencrypt_dir = self._runtime.paths.run_dir / self._runtime.config.global_.letsencrypt_dir
        return CertbotPaths(
            config_dir=letsencrypt_dir,
            work_dir=self._runtime.paths.run_dir / "work",
            logs_dir=self._runtime.paths.log_dir,
        )

    def _prepare_credentials(self, entry) -> dict[str, str | None]:
        provider = entry.dns_provider.lower()
        if provider == "aliyun":
            self._prepare_aliyun_credentials_ini(entry)
            return {}
        elif provider == "cloudflare":
            self._prepare_cloudflare_credentials_ini(entry)
            return {}
        elif provider == "route53":
            return self._route53_env(entry)
        else:
            raise ValueError(f"unsupported dns_provider: {entry.dns_provider}")

    def _build_renew_plan(self, entry) -> RenewPlan:
        return RenewPlan(
            entry=entry,
            cert_name=resolve_entry_cert_name(
                self._runtime,
                entry,
                require_existing_lineage=True,
                resolution_mode="strict",
            ),
            env_overrides=self._prepare_credentials(entry),
        )

    def _renew_entry(
        self,
        plan: RenewPlan,
        *,
        force: bool,
        dry_run: bool,
        verbose: bool,
    ) -> RenewResult:
        args: list[str] = ["renew", "--cert-name", plan.cert_name]
        if force:
            args.append("--force-renewal")
        if dry_run:
            args.append("--dry-run")

        log_path = new_run_logfile(
            self._runtime.paths.log_dir,
            command=f"renew_{plan.entry.name}",
        )
        result = run_certbot(
            args,
            paths=self._certbot_paths(),
            passthrough=verbose,
            env=plan.env_overrides or None,
        )
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "command": "renew",
            "entry": plan.entry.name,
            "cert_name": plan.cert_name,
            "args": args,
            "certbot": {
                "returncode": result.returncode,
                "cmd": result.cmd,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
        }
        _write_command_log(log_path, payload)

        return RenewResult(
            success=result.ok,
            entry_name=plan.entry.name,
            renewed=result.ok,
            log_path=log_path,
            dry_run=dry_run,
            admin_required=result.is_admin_required_error(),
            error=None if result.ok else (result.stderr or result.stdout or "certbot renew failed"),
        )

    def _route53_env(self, entry) -> dict[str, str | None]:
        creds = route53_credentials_for_entry(entry)
        return {
            "AWS_ACCESS_KEY_ID": creds.access_key_id,
            "AWS_SECRET_ACCESS_KEY": creds.secret_access_key,
            "AWS_DEFAULT_REGION": creds.region,
            "AWS_SESSION_TOKEN": None,
            "AWS_PROFILE": None,
            "AWS_DEFAULT_PROFILE": None,
            "AWS_SHARED_CREDENTIALS_FILE": None,
            "AWS_CONFIG_FILE": None,
        }


    def _prepare_aliyun_credentials_ini(self, entry) -> Path:
        creds = aliyun_credentials_for_entry(entry)
        cred_dir = self._runtime.paths.run_dir / "credentials"
        cred_file = cred_dir / f"aliyun_{(entry.account_id or entry.name)}.ini"
        write_aliyun_credentials_ini(cred_file, creds)
        return cred_file

    def _prepare_cloudflare_credentials_ini(self, entry) -> Path:
        creds = cloudflare_credentials_for_entry(entry)
        cred_dir = self._runtime.paths.run_dir / "credentials"
        cred_file = cred_dir / f"cloudflare_{(entry.account_id or entry.name)}.ini"
        write_cloudflare_credentials_ini(cred_file, creds)
        return cred_file

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from certman.config import Runtime, entry_delivery_targets
from certman.delivery.adapters import (
    deliver_k8s_ingress_bundle,
    deliver_nginx_bundle,
    deliver_openresty_bundle,
)
from certman.delivery.aws_acm import deliver_aws_acm_bundle
from certman.delivery.filesystem import deliver_filesystem_bundle
from certman.services.cert_service import resolve_entry_cert_name


@dataclass(frozen=True)
class DeliveryExecution:
    type: str
    scope: str | None
    delivered_paths: list[Path]


@dataclass(frozen=True)
class DeliveryResult:
    success: bool
    entry_name: str
    executions: list[DeliveryExecution]
    error: str | None = None


class DeliveryService:
    def __init__(self, runtime: Runtime):
        self._runtime = runtime

    def deliver(self, entry_name: str) -> DeliveryResult:
        entry = next((item for item in self._runtime.config.entries if item.name == entry_name), None)
        if entry is None:
            raise ValueError(f"entry not found: {entry_name}")

        targets = entry_delivery_targets(entry)
        if not targets:
            return DeliveryResult(success=True, entry_name=entry_name, executions=[])

        files = self._load_live_files(entry)
        executions: list[DeliveryExecution] = []
        for index, target in enumerate(targets):
            target_type = target.type.strip().lower()
            target_scope = target.scope.strip() if target.scope else None
            target_dir = self._runtime.paths.output_dir / entry.name / f"{index:02d}-{target_type}"
            delivered = self._deliver_target(
                target_type=target_type,
                target_scope=target_scope,
                files=files,
                target_dir=target_dir,
                account_id=target.account_id,
                options=target.options,
                entry_name=entry.name,
                primary_domain=entry.primary_domain,
            )
            executions.append(
                DeliveryExecution(
                    type=target_type,
                    scope=target_scope,
                    delivered_paths=delivered,
                )
            )

        return DeliveryResult(success=True, entry_name=entry_name, executions=executions)

    def _load_live_files(self, entry) -> dict[str, str]:
        cert_name = resolve_entry_cert_name(
            self._runtime,
            entry,
            require_existing_lineage=True,
            resolution_mode="strict",
        )
        live_dir = self._runtime.paths.run_dir / self._runtime.config.global_.letsencrypt_dir / "live" / cert_name
        files: dict[str, str] = {}
        for filename in ("cert.pem", "chain.pem", "fullchain.pem", "privkey.pem"):
            path = live_dir / filename
            if path.exists():
                files[filename] = path.read_text(encoding="utf-8")
        if "privkey.pem" not in files or ("cert.pem" not in files and "fullchain.pem" not in files):
            raise ValueError(f"incomplete live certificate files for entry={entry.name}")
        return files

    def _deliver_target(
        self,
        *,
        target_type: str,
        target_scope: str | None,
        files: dict[str, str],
        target_dir: Path,
        account_id: str | None,
        options: dict[str, Any],
        entry_name: str,
        primary_domain: str,
    ) -> list[Path]:
        if target_type == "generic":
            return deliver_filesystem_bundle(files=files, target_dir=target_dir)
        if target_type == "nginx":
            return deliver_nginx_bundle(files=files, target_dir=target_dir)
        if target_type == "openresty":
            return deliver_openresty_bundle(files=files, target_dir=target_dir)
        if target_type == "k8s-ingress":
            namespace, secret_name = _parse_k8s_scope(target_scope or "")
            return deliver_k8s_ingress_bundle(
                files=files,
                target_dir=target_dir,
                namespace=namespace,
                secret_name=secret_name,
                mode=str(options.get("mode", "apply")),
                rollback_on_failure=bool(options.get("rollback_on_failure", True)),
                kubectl_bin=str(options.get("kubectl_bin", "kubectl")),
            )
        if target_type == "aws-acm":
            regions = _normalize_regions(options.get("regions"), fallback=target_scope)
            tags = options.get("tags") if isinstance(options.get("tags"), dict) else {}
            return deliver_aws_acm_bundle(
                files=files,
                target_dir=target_dir,
                entry_name=entry_name,
                primary_domain=primary_domain,
                account_id=account_id,
                regions=regions,
                tags=tags,
            )
        raise ValueError(f"unsupported delivery target_type: {target_type}")


def _parse_k8s_scope(scope: str) -> tuple[str, str]:
    normalized = scope.strip()
    if not normalized:
        return "default", "certman-tls"
    if "/" not in normalized:
        return normalized, "certman-tls"
    namespace, secret_name = normalized.split("/", 1)
    return namespace or "default", secret_name or "certman-tls"


def _normalize_regions(raw: Any, *, fallback: str | None) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str) and raw.strip():
        return [item.strip() for item in raw.split(",") if item.strip()]
    if fallback:
        return [item.strip() for item in fallback.split(",") if item.strip()]
    return ["us-east-1"]

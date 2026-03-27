from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from certman.delivery.adapters import deliver_k8s_ingress_bundle, deliver_nginx_bundle, deliver_openresty_bundle
from certman.delivery.filesystem import deliver_filesystem_bundle
from certman.hooks.runner import HookRunner


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    status: str
    delivered_paths: list[Path]
    error: str | None = None


class NodeExecutor:
    def __init__(self, hook_runner: HookRunner | None = None):
        self._hook_runner = hook_runner or HookRunner()

    def execute(
        self,
        *,
        job_id: str,
        bundle: dict,
        target_dir: Path,
        hooks: list[dict] | None = None,
    ) -> ExecutionResult:
        files = bundle.get("files", {})
        target_type = str(bundle.get("target_type", "generic")).strip().lower()
        options = bundle.get("delivery_options") if isinstance(bundle.get("delivery_options"), dict) else {}
        try:
            if target_type == "nginx":
                delivered_paths = deliver_nginx_bundle(files=files, target_dir=target_dir)
            elif target_type == "openresty":
                delivered_paths = deliver_openresty_bundle(files=files, target_dir=target_dir)
            elif target_type == "k8s-ingress":
                namespace, secret_name = _parse_k8s_scope(str(bundle.get("target_scope", "")))
                delivered_paths = deliver_k8s_ingress_bundle(
                    files=files,
                    target_dir=target_dir,
                    namespace=namespace,
                    secret_name=secret_name,
                    mode=str(options.get("mode", "render")),
                    rollback_on_failure=bool(options.get("rollback_on_failure", True)),
                    kubectl_bin=str(options.get("kubectl_bin", "kubectl")),
                )
            else:
                delivered_paths = deliver_filesystem_bundle(files=files, target_dir=target_dir)
        except Exception as exc:
            return ExecutionResult(success=False, status="failed", delivered_paths=[], error=str(exc))

        for hook in hooks or []:
            result = self._hook_runner.run(
                name=hook["name"],
                event=hook["event"],
                command=hook["command"],
                shell=hook.get("shell", True),
            )
            if not result.success:
                return ExecutionResult(
                    success=False,
                    status="failed",
                    delivered_paths=delivered_paths,
                    error=result.error,
                )

        return ExecutionResult(success=True, status="completed", delivered_paths=delivered_paths)


def _parse_k8s_scope(scope: str) -> tuple[str, str]:
    normalized = scope.strip()
    if not normalized:
        return "default", "certman-tls"
    if "/" not in normalized:
        return normalized, "certman-tls"
    namespace, secret_name = normalized.split("/", 1)
    return namespace or "default", secret_name or "certman-tls"

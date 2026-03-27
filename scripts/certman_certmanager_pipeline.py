#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""One-click local validation pipeline for CertMan + cert-manager.

Pipeline stages:
1) Baseline: kind + cert-manager install and smoke check
2) CertMan k8s e2e: existing scripts/e2e-test.py --k8s-only
3) CertMan direct issue/renew validation in docker local-linuxfs profile

Examples:
    uv run scripts/certman_certmanager_pipeline.py baseline
    uv run scripts/certman_certmanager_pipeline.py certman --entry kumaxiong
    uv run scripts/certman_certmanager_pipeline.py full --entry kumaxiong
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT_JSON = PROJECT_ROOT / "docs" / "notes" / "certman-certmanager-pipeline-report.json"
DEFAULT_REPORT_MD = PROJECT_ROOT / "docs" / "notes" / "certman-certmanager-pipeline-report.md"


@dataclass(frozen=True)
class StepResult:
    name: str
    command: str
    ok: bool
    returncode: int
    started_at: str
    ended_at: str
    error_hint: str | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_failure(command: str, output: str) -> str:
    lowered = output.lower()
    if "unicodeencodeerror" in lowered or "gbk" in lowered:
        return "终端编码问题：请使用 UTF-8 终端或更新脚本为安全输出模式"
    if "admin" in lowered and "windows" in lowered:
        return "Windows 权限限制：请改用 Docker profile local-linuxfs 或管理员终端"
    if "symlink" in lowered:
        return "Windows bind mount 符号链接问题：请使用 certman-linuxfs profile"
    if "helm" in lowered and "repo" in lowered and "update" in lowered:
        return "Helm 仓库更新失败：建议只更新 jetstack 或清理失效 repo"
    if "context deadline exceeded" in lowered:
        return "网络超时：请检查网络或重试"
    if "not found" in lowered and "kind" in lowered:
        return "kind 未安装或不在 PATH"
    if "command failed" in lowered:
        return "子命令执行失败，请查看对应输出"
    if "no such host" in lowered or "connection" in lowered:
        return "网络连接异常，请检查 Docker/k8s 网络"
    return f"步骤失败：{command}"


def run_step(name: str, cmd: list[str]) -> StepResult:
    started = now_iso()
    printable = " ".join(cmd)
    print(f"\n==> [{name}] {printable}")
    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)

    ok = proc.returncode == 0
    hint = None
    if not ok:
        hint = classify_failure(printable, f"{proc.stdout}\n{proc.stderr}")
    return StepResult(
        name=name,
        command=printable,
        ok=ok,
        returncode=proc.returncode,
        started_at=started,
        ended_at=now_iso(),
        error_hint=hint,
    )


def run_baseline() -> list[StepResult]:
    return [
        run_step("cert-manager up", ["uv", "run", "scripts/cert_manager_lab.py", "up"]),
        run_step("cert-manager smoke", ["uv", "run", "scripts/cert_manager_lab.py", "smoke"]),
    ]


def run_certman(entry: str) -> list[StepResult]:
    return [
        run_step(
            "certman config-validate",
            [
                "docker",
                "compose",
                "--profile",
                "local-linuxfs",
                "run",
                "--rm",
                "certman-linuxfs",
                "config-validate",
                "--name",
                entry,
            ],
        ),
        run_step(
            "certman new",
            [
                "docker",
                "compose",
                "--profile",
                "local-linuxfs",
                "run",
                "--rm",
                "certman-linuxfs",
                "new",
                "--name",
                entry,
                "--no-export",
            ],
        ),
        run_step(
            "certman renew dry-run",
            [
                "docker",
                "compose",
                "--profile",
                "local-linuxfs",
                "run",
                "--rm",
                "certman-linuxfs",
                "renew",
                "--name",
                entry,
                "--dry-run",
                "--no-export",
            ],
        ),
    ]


def run_k8s_e2e() -> list[StepResult]:
    return [run_step("certman k8s e2e", ["uv", "run", "scripts/e2e-test.py", "--k8s-only", "--no-cleanup"])]


def write_reports(mode: str, entry: str, steps: list[StepResult], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": now_iso(),
        "mode": mode,
        "entry": entry,
        "summary": {
            "total": len(steps),
            "passed": sum(1 for s in steps if s.ok),
            "failed": sum(1 for s in steps if not s.ok),
        },
        "steps": [asdict(s) for s in steps],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# CertMan + cert-manager Pipeline Report",
        "",
        f"- 时间: {payload['timestamp']}",
        f"- 模式: {mode}",
        f"- 条目: {entry}",
        f"- 总计: {payload['summary']['total']}",
        f"- 成功: {payload['summary']['passed']}",
        f"- 失败: {payload['summary']['failed']}",
        "",
        "## 步骤结果",
        "",
    ]
    for s in steps:
        status = "PASS" if s.ok else "FAIL"
        lines.append(f"1. {status} | {s.name}")
        lines.append(f"1. command: {s.command}")
        lines.append(f"1. returncode: {s.returncode}")
        if s.error_hint:
            lines.append(f"1. hint: {s.error_hint}")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local CertMan + cert-manager validation pipeline")
    parser.add_argument("mode", choices=["baseline", "certman", "full"], help="Pipeline mode")
    parser.add_argument("--entry", default="kumaxiong", help="CertMan entry name")
    parser.add_argument("--skip-k8s-e2e", action="store_true", help="Skip k8s e2e stage in full mode")
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON), help="JSON report output path")
    parser.add_argument("--report-md", default=str(DEFAULT_REPORT_MD), help="Markdown report output path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    steps: list[StepResult] = []

    if args.mode == "baseline":
        steps.extend(run_baseline())
    elif args.mode == "certman":
        steps.extend(run_certman(args.entry))
    else:
        steps.extend(run_baseline())
        if not args.skip_k8s_e2e:
            steps.extend(run_k8s_e2e())
        steps.extend(run_certman(args.entry))

    write_reports(
        mode=args.mode,
        entry=args.entry,
        steps=steps,
        json_path=Path(args.report_json),
        md_path=Path(args.report_md),
    )

    failed = [s for s in steps if not s.ok]
    print("\n==> Pipeline summary")
    print(f"total={len(steps)} passed={len(steps) - len(failed)} failed={len(failed)}")
    print(f"report_json={Path(args.report_json)}")
    print(f"report_md={Path(args.report_md)}")

    if failed:
        print("\nFailed steps:")
        for f in failed:
            print(f"- {f.name}: {f.error_hint or 'unknown error'}")
        sys.exit(1)


if __name__ == "__main__":
    main()

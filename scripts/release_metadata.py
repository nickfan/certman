from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import tomllib


SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
TAG_PATTERN = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


@dataclass(frozen=True)
class ReleasePlan:
    version: str
    tag: str
    release_required: bool
    latest_released_version: str | None


def parse_version(version: str) -> tuple[int, int, int]:
    match = SEMVER_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError(f"project version must use MAJOR.MINOR.PATCH syntax: {version}")
    return tuple(int(part) for part in match.groups())


def read_project_version(pyproject_path: Path) -> str:
    with pyproject_path.open("rb") as handle:
        data = tomllib.load(handle)
    try:
        version = data["project"]["version"]
    except KeyError as exc:
        raise ValueError(f"missing [project].version in {pyproject_path}") from exc
    if not isinstance(version, str):
        raise ValueError(f"[project].version must be a string in {pyproject_path}")
    parse_version(version)
    return version


def release_versions(tags: list[str]) -> list[tuple[int, int, int]]:
    versions: list[tuple[int, int, int]] = []
    for tag in tags:
        match = TAG_PATTERN.fullmatch(tag)
        if match is not None:
            versions.append(tuple(int(part) for part in match.groups()))
    return sorted(set(versions))


def format_version(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


def plan_release(version: str, tags: list[str]) -> ReleasePlan:
    current_version = parse_version(version)
    current_tag = f"v{version}"
    released_versions = release_versions(tags)
    latest_version = released_versions[-1] if released_versions else None

    if current_tag in tags:
        return ReleasePlan(
            version=version,
            tag=current_tag,
            release_required=False,
            latest_released_version=format_version(latest_version) if latest_version else None,
        )

    if latest_version is not None and current_version <= latest_version:
        raise ValueError(
            f"unreleased project version {version} must be greater than latest tag "
            f"v{format_version(latest_version)}"
        )

    return ReleasePlan(
        version=version,
        tag=current_tag,
        release_required=True,
        latest_released_version=format_version(latest_version) if latest_version else None,
    )


def git_tags() -> list[str]:
    result = subprocess.run(
        ["git", "tag", "--list", "v*"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def write_github_output(path: Path, plan: ReleasePlan) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"version={plan.version}\n")
        handle.write(f"tag={plan.tag}\n")
        handle.write(f"release_required={str(plan.release_required).lower()}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve CertMan release metadata from pyproject.toml and git tags.")
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    version = read_project_version(args.pyproject)
    plan = plan_release(version, git_tags())
    if args.github_output is not None:
        write_github_output(args.github_output, plan)

    print(
        json.dumps(
            {
                "version": plan.version,
                "tag": plan.tag,
                "release_required": plan.release_required,
                "latest_released_version": plan.latest_released_version,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

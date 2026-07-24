from __future__ import annotations

from pathlib import Path

import pytest

from scripts.release_metadata import plan_release, read_project_version, release_versions


def test_plan_release_requires_new_tag_for_higher_version() -> None:
    plan = plan_release("0.2.2", ["v0.1.3", "v0.2.0", "v0.2.1"])

    assert plan.version == "0.2.2"
    assert plan.tag == "v0.2.2"
    assert plan.release_required is True
    assert plan.latest_released_version == "0.2.1"


def test_plan_release_skips_existing_version_tag() -> None:
    plan = plan_release("0.2.2", ["v0.2.1", "v0.2.2"])

    assert plan.release_required is False
    assert plan.latest_released_version == "0.2.2"


def test_plan_release_rejects_version_regression() -> None:
    with pytest.raises(ValueError, match="must be greater than latest tag v0.2.2"):
        plan_release("0.2.1", ["v0.2.2"])


def test_plan_release_requires_strict_semver() -> None:
    with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
        plan_release("0.2", [])


def test_release_versions_ignores_non_release_tags() -> None:
    assert release_versions(["v0.2.0", "latest", "v0.2.1-rc1", "v1.0.0"]) == [
        (0, 2, 0),
        (1, 0, 0),
    ]


def test_read_project_version(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "certman"\nversion = "1.2.3"\n', encoding="utf-8")

    assert read_project_version(pyproject) == "1.2.3"

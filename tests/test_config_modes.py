from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from certman.config import AppConfig, create_runtime


def test_local_mode_config_loads_from_yaml(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir(parents=True)
    config_path = conf_dir / "config.yaml"
    config_path.write_text(
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

    runtime = create_runtime(str(tmp_path), "config.yaml")

    assert runtime.config.run_mode == "local"
    assert runtime.config.entries[0].name == "site-a"


def test_agent_mode_requires_control_plane_endpoint() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate(
            {
                "run_mode": "agent",
                "global": {"email": "ops@example.com"},
                "entries": [],
                "node_identity": {
                    "node_id": "node-a",
                    "private_key_path": "keys/node-a.pem",
                },
            }
        )


def test_agent_mode_requires_private_key_path() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate(
            {
                "run_mode": "agent",
                "global": {"email": "ops@example.com"},
                "entries": [],
                "control_plane": {
                    "endpoint": "https://certman.example.com"
                },
                "node_identity": {"node_id": "node-a"},
            }
        )


def test_agent_mode_round_trips_through_merged_runtime(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir(parents=True)
    config_path = conf_dir / "config.toml"
    config_path.write_text(
        """
run_mode = "agent"

[global]
data_dir = "data"
email = "ops@example.com"

[control_plane]
endpoint = "https://certman.example.com"
poll_interval_seconds = 45

[node_identity]
node_id = "node-a"
private_key_path = "keys/node-a.pem"

[[hooks]]
name = "reload-nginx"
event = "certificate.updated"
command = "nginx -s reload"
""".strip(),
        encoding="utf-8",
    )
    item_path = conf_dir / "item_site_a.toml"
    item_path.write_text(
        """
primary_domain = "example.com"
dns_provider = "aliyun"
""".strip(),
        encoding="utf-8",
    )

    runtime = create_runtime(str(tmp_path), None)

    assert runtime.config.run_mode == "agent"
    assert runtime.config.control_plane is not None
    assert runtime.config.control_plane.endpoint == "https://certman.example.com"
    assert runtime.config.node_identity is not None
    assert runtime.config.node_identity.private_key_path == "keys/node-a.pem"
    assert runtime.config.hooks[0].event == "certificate.updated"
    assert runtime.config.entries[0].name == "site_a"


def test_relative_global_data_dir_does_not_override_cli_data_dir(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
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

    runtime = create_runtime(str(tmp_path), "config.yaml")

    assert runtime.paths.data_dir == tmp_path


def test_non_default_relative_global_data_dir_overrides_cli_base(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.yaml").write_text(
        """
run_mode: local
global:
  data_dir: custom-data
  email: ops@example.com
entries:
  - name: site-a
    primary_domain: example.com
    dns_provider: aliyun
""".strip(),
        encoding="utf-8",
    )

    runtime = create_runtime(str(tmp_path), "config.yaml")

    assert runtime.paths.data_dir == tmp_path.parent / "custom-data"

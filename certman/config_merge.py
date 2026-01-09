from __future__ import annotations

from pathlib import Path

from certman.config import AppConfig, GlobalOnlyConfig, load_config


def load_merged_config(global_config_path: Path) -> AppConfig:
    """Load global config and merge item configs under same directory.

    Default convention:
    - Global config: data/conf/config.toml
      - can provide scan_items_glob (default: item_*.toml)
    - Item configs:  data/conf/item_*.toml
      - When an item file contains no entries, it is treated as a single-entry file.
      - For a single-entry file, entry.name defaults from filename: item_<name>.toml -> <name>

    This supports:
    - portable: one item file with embedded creds
    - ops: use .env and account_id references
    """

    base_cfg = load_config(global_config_path)
    global_only = GlobalOnlyConfig.model_validate(load_config_dict(global_config_path))

    scan_glob = global_only.scan_items_glob
    conf_dir = global_config_path.parent

    merged_entries: list[dict] = []
    merged_entries.extend([e.model_dump() for e in base_cfg.entries])

    for item_path in sorted(conf_dir.glob(scan_glob)):
        if item_path.name == global_config_path.name:
            continue
        if item_path.name.endswith(".example.toml"):
            continue

        item_dict = load_config_dict(item_path)
        default_name = _default_name_from_item(item_path)

        # item file can be:
        # 1) a full AppConfig with entries
        # 2) a single entry dict (portable one-file)
        if "entries" in item_dict or "global" in item_dict:
            item_cfg = AppConfig.model_validate(item_dict)
            for e in item_cfg.entries:
                merged_entries.append(e.model_dump())
        else:
            item_entry = dict(item_dict)
            item_entry.setdefault("name", default_name)
            merged_entries.append(item_entry)

    merged_dict = {
        "global": base_cfg.global_.model_dump(),
        "entries": merged_entries,
    }

    return AppConfig.model_validate(merged_dict)


def load_config_dict(path: Path) -> dict:
    # Re-use the same parser used by load_config, but return raw dict.
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")

    if suffix == ".toml":
        import tomllib

        return tomllib.loads(text)

    if suffix in {".yaml", ".yml"}:
        import yaml

        return yaml.safe_load(text)

    raise ValueError(f"unsupported config format: {suffix}")


def _default_name_from_item(item_path: Path) -> str:
    stem = item_path.stem
    if stem.startswith("item_"):
        return stem[len("item_") :]
    return stem

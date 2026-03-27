from __future__ import annotations

from pathlib import Path
import re

from dotenv import dotenv_values, set_key, unset_key
import tomli_w

from certman.config import EntryConfig
from certman.config_merge import load_config_dict


def default_config_filename() -> str:
    return "config.toml"


def _slugify_entry_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", name.strip())
    slug = slug.strip("-")
    if not slug:
        raise ValueError("entry name cannot be empty")
    return slug


def item_path_for_entry(conf_dir: Path, entry_name: str) -> Path:
    return conf_dir / f"item_{_slugify_entry_name(entry_name)}.toml"


def _clean_dict(value):
    if isinstance(value, dict):
        output = {}
        for key, val in value.items():
            cleaned = _clean_dict(val)
            if cleaned is None:
                continue
            if cleaned == {}:
                continue
            output[key] = cleaned
        return output
    if isinstance(value, list):
        return [_clean_dict(v) for v in value]
    return value


def entry_to_item_dict(entry: EntryConfig) -> dict:
    dumped = entry.model_dump(exclude_none=True)
    return _clean_dict(dumped)


def write_item_entry(conf_dir: Path, entry: EntryConfig) -> Path:
    conf_dir.mkdir(parents=True, exist_ok=True)
    path = item_path_for_entry(conf_dir, entry.name)
    path.write_text(tomli_w.dumps(entry_to_item_dict(entry)), encoding="utf-8")
    return path


def remove_item_entry(conf_dir: Path, entry_name: str) -> bool:
    path = item_path_for_entry(conf_dir, entry_name)
    if not path.exists():
        return False
    path.unlink()
    return True


def load_global_config_dict(conf_dir: Path, config_filename: str) -> tuple[Path, dict]:
    path = conf_dir / config_filename
    if not path.exists():
        raise FileNotFoundError(f"global config file not found: {path}")
    return path, load_config_dict(path)


def _entries_from_global(raw_cfg: dict) -> list[dict]:
    entries = raw_cfg.get("entries")
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise ValueError("config entries must be a list")
    return entries


def upsert_global_entry(conf_dir: Path, config_filename: str, entry: EntryConfig) -> tuple[Path, bool]:
    path, raw_cfg = load_global_config_dict(conf_dir, config_filename)
    entries = _entries_from_global(raw_cfg)
    entry_dict = entry.model_dump(exclude_none=True)

    replaced = False
    for idx, existing in enumerate(entries):
        if isinstance(existing, dict) and existing.get("name") == entry.name:
            entries[idx] = entry_dict
            replaced = True
            break
    if not replaced:
        entries.append(entry_dict)

    raw_cfg["entries"] = entries
    path.write_text(tomli_w.dumps(raw_cfg), encoding="utf-8")
    return path, (not replaced)


def remove_global_entry(conf_dir: Path, config_filename: str, entry_name: str) -> tuple[Path, bool]:
    path, raw_cfg = load_global_config_dict(conf_dir, config_filename)
    entries = _entries_from_global(raw_cfg)

    original_count = len(entries)
    entries = [entry for entry in entries if not (isinstance(entry, dict) and entry.get("name") == entry_name)]
    removed = len(entries) != original_count

    raw_cfg["entries"] = entries
    path.write_text(tomli_w.dumps(raw_cfg), encoding="utf-8")
    return path, removed


def read_env_file(conf_dir: Path) -> tuple[Path, dict[str, str]]:
    env_path = conf_dir / ".env"
    values = dotenv_values(env_path)
    typed_values = {str(k): str(v) for k, v in values.items() if k is not None and v is not None}
    return env_path, typed_values


def set_env_value(conf_dir: Path, key: str, value: str) -> Path:
    env_path = conf_dir / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if not env_path.exists():
        env_path.write_text("", encoding="utf-8")
    set_key(str(env_path), key, value)
    return env_path


def unset_env_value(conf_dir: Path, key: str) -> tuple[Path, bool]:
    env_path = conf_dir / ".env"
    if not env_path.exists():
        return env_path, False
    result = unset_key(str(env_path), key)
    if isinstance(result, tuple):
        return env_path, bool(result[0])
    return env_path, bool(result)


def ensure_default_global_config(conf_dir: Path, *, overwrite: bool = False) -> Path:
    conf_dir.mkdir(parents=True, exist_ok=True)
    path = conf_dir / default_config_filename()
    if path.exists() and not overwrite:
        return path

    content = {
        "run_mode": "local",
        "global": {
            "data_dir": "data",
            "conf_dir": "conf",
            "run_dir": "run",
            "log_dir": "log",
            "output_dir": "output",
            "letsencrypt_dir": "letsencrypt",
            "acme_server": "staging",
            "email": "admin@example.com",
            "scan_items_glob": "item_*.toml",
        },
    }
    path.write_text(tomli_w.dumps(content), encoding="utf-8")
    return path

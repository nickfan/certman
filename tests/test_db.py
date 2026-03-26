from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from certman.db.engine import make_engine


def _alembic_config(tmp_path: Path) -> Config:
    repo_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'certman.db'}")
    return cfg


def test_initial_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    cfg = _alembic_config(tmp_path)
    command.upgrade(cfg, "head")

    db_path = tmp_path / "certman.db"
    engine = make_engine(db_path)
    tables_after_create = set(inspect(engine).get_table_names())

    assert {"certificate", "job", "node", "audit_event"}.issubset(tables_after_create)

    command.downgrade(cfg, "base")
    tables_after_drop = set(inspect(engine).get_table_names())

    assert "certificate" not in tables_after_drop
    assert "job" not in tables_after_drop
    assert "node" not in tables_after_drop
    assert "audit_event" not in tables_after_drop

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


# Python 3.12 deprecates sqlite3 default datetime adapter; register explicit adapters.
sqlite3.register_adapter(datetime, lambda value: value.isoformat(sep=" "))
sqlite3.register_adapter(date, lambda value: value.isoformat())


def _normalize_db_path(db_path: str | Path) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.resolve()


@lru_cache(maxsize=64)
def _make_engine_cached(db_url: str) -> Engine:
    return create_engine(db_url, future=True)


@lru_cache(maxsize=64)
def _make_session_factory_cached(db_url: str) -> sessionmaker[Session]:
    engine = _make_engine_cached(db_url)
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def make_engine(db_path: str | Path) -> Engine:
    path = _normalize_db_path(db_path)
    return _make_engine_cached(f"sqlite+pysqlite:///{path}")


def make_session_factory(db_path: str | Path) -> sessionmaker[Session]:
    path = _normalize_db_path(db_path)
    return _make_session_factory_cached(f"sqlite+pysqlite:///{path}")

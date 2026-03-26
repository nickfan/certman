from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from certman.db.engine import make_session_factory
from certman.db.models import NodeORM


@dataclass(frozen=True)
class NodeRegisterResult:
    node_id: str
    status: str
    created: bool


class NodeService:
    def __init__(self, *, db_path):
        self._session_factory = make_session_factory(db_path)

    def register_node(self, *, node_id: str, node_type: str, public_key: str) -> NodeRegisterResult:
        now = datetime.now(timezone.utc)
        normalized_key = public_key.strip()
        with self._session_factory() as session:
            existing = session.query(NodeORM).filter(NodeORM.node_id == node_id).first()
            if existing is None:
                session.add(
                    NodeORM(
                        node_id=node_id,
                        node_type=node_type,
                        public_key=normalized_key,
                        status="active",
                        last_seen=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
                try:
                    session.commit()
                    return NodeRegisterResult(node_id=node_id, status="active", created=True)
                except IntegrityError:
                    session.rollback()
                    existing = session.query(NodeORM).filter(NodeORM.node_id == node_id).first()
                    if existing is None:
                        raise

                    same_key_after_race = (existing.public_key or "").strip() == normalized_key
                    if same_key_after_race:
                        return NodeRegisterResult(node_id=node_id, status=existing.status, created=False)
                    raise ValueError("node already registered with another key")

            same_key = (existing.public_key or "").strip() == normalized_key
            if same_key:
                if existing.status != "active" or existing.node_type != node_type:
                    existing.status = "active"
                    existing.node_type = node_type
                    existing.updated_at = now
                    session.commit()
                return NodeRegisterResult(node_id=node_id, status="active", created=False)

            if existing.status == "active":
                raise ValueError("node already registered with another key")

            existing.public_key = normalized_key
            existing.node_type = node_type
            existing.status = "active"
            existing.updated_at = now
            session.commit()
            return NodeRegisterResult(node_id=node_id, status="active", created=False)

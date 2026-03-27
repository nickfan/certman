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

    def register_node(
        self,
        *,
        node_id: str,
        node_type: str,
        public_key: str,
        encryption_public_key: str | None = None,
    ) -> NodeRegisterResult:
        now = datetime.now(timezone.utc)
        normalized_key = public_key.strip()
        normalized_enc_key = encryption_public_key.strip() if encryption_public_key else None
        with self._session_factory() as session:
            existing = session.query(NodeORM).filter(NodeORM.node_id == node_id).first()
            if existing is None:
                session.add(
                    NodeORM(
                        node_id=node_id,
                        node_type=node_type,
                        public_key=normalized_key,
                        encryption_public_key=normalized_enc_key,
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
                changed = existing.status != "active" or existing.node_type != node_type
                enc_changed = normalized_enc_key is not None and (existing.encryption_public_key or "").strip() != normalized_enc_key
                if changed or enc_changed:
                    existing.status = "active"
                    existing.node_type = node_type
                    if enc_changed:
                        existing.encryption_public_key = normalized_enc_key
                    existing.updated_at = now
                    session.commit()
                return NodeRegisterResult(node_id=node_id, status="active", created=False)

            if existing.status == "active":
                raise ValueError("node already registered with another key")

            existing.public_key = normalized_key
            existing.node_type = node_type
            existing.status = "active"
            if normalized_enc_key is not None:
                existing.encryption_public_key = normalized_enc_key
            existing.updated_at = now
            session.commit()
            return NodeRegisterResult(node_id=node_id, status="active", created=False)

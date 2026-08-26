"""Shell-private persisted authentication for process-boundary session recovery."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .contracts import ConversationTurn, RevisionConversationContext
from .conversation import BoundedConversationProjection


@dataclass(frozen=True)
class SessionRecoveryCredential:
    session_id: str
    expires_at: datetime


class SessionRecoveryRegistry(Protocol):
    async def register(
        self,
        session_id: str,
        session_key: str,
        expires_at: datetime,
    ) -> None: ...

    async def authenticate(
        self,
        session_id: str,
        session_key: str,
    ) -> SessionRecoveryCredential | None: ...

    async def load_projection(
        self,
        session_id: str,
    ) -> BoundedConversationProjection: ...

    async def save_projection(
        self,
        session_id: str,
        projection: BoundedConversationProjection,
    ) -> None: ...

    async def revoke(self, session_id: str) -> None: ...


@dataclass(frozen=True)
class SQLiteSessionRecoveryRegistry:
    """Persist a salted verifier and TTL, never a reusable session key."""

    path: Path

    def __post_init__(self) -> None:
        path = Path(self.path)
        if not str(path).strip() or path.name in {"", ".", ".."}:
            raise ValueError("session recovery registry path is invalid")
        object.__setattr__(self, "path", path)

    async def register(
        self,
        session_id: str,
        session_key: str,
        expires_at: datetime,
    ) -> None:
        if not session_id.strip() or not session_key.strip() or expires_at.tzinfo is None:
            raise ValueError("session recovery credential is invalid")
        salt = secrets.token_bytes(32)
        verifier = _verifier(salt, session_key)
        await asyncio.to_thread(
            self._register,
            session_id,
            salt.hex(),
            verifier,
            expires_at.astimezone(UTC).isoformat(),
            _serialize_projection(BoundedConversationProjection()),
        )

    async def authenticate(
        self,
        session_id: str,
        session_key: str,
    ) -> SessionRecoveryCredential | None:
        if not session_id.strip() or not session_key.strip():
            return None
        row = await asyncio.to_thread(self._load, session_id)
        if row is None:
            return None
        salt_hex, expected, raw_expiry = row
        try:
            salt = bytes.fromhex(salt_hex)
            expires_at = datetime.fromisoformat(raw_expiry)
        except ValueError:
            return None
        if expires_at.tzinfo is None or not secrets.compare_digest(
            expected,
            _verifier(salt, session_key),
        ):
            return None
        return SessionRecoveryCredential(session_id, expires_at.astimezone(UTC))

    async def load_projection(
        self,
        session_id: str,
    ) -> BoundedConversationProjection:
        raw = await asyncio.to_thread(self._load_projection, session_id)
        if raw is None:
            raise LookupError("session recovery projection is unavailable")
        return _deserialize_projection(raw)

    async def save_projection(
        self,
        session_id: str,
        projection: BoundedConversationProjection,
    ) -> None:
        if not isinstance(projection, BoundedConversationProjection):
            raise TypeError("session recovery requires a typed conversation projection")
        await asyncio.to_thread(
            self._save_projection,
            session_id,
            _serialize_projection(projection),
        )

    async def revoke(self, session_id: str) -> None:
        await asyncio.to_thread(self._revoke, session_id)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.executescript(_SCHEMA)
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(shell_session_recovery)")
        }
        if "projection_json" not in columns:
            try:
                connection.execute(
                    "ALTER TABLE shell_session_recovery ADD COLUMN projection_json TEXT"
                )
                connection.commit()
            except sqlite3.OperationalError:
                migrated_columns = {
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(shell_session_recovery)")
                }
                if "projection_json" not in migrated_columns:
                    connection.close()
                    raise
        return connection

    def _register(
        self,
        session_id: str,
        salt: str,
        verifier: str,
        expires_at: str,
        projection_json: str,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO shell_session_recovery "
                "(session_id, salt, verifier, expires_at, projection_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, salt, verifier, expires_at, projection_json),
            )
            connection.commit()
        finally:
            connection.close()

    def _load(self, session_id: str) -> tuple[str, str, str] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT salt, verifier, expires_at FROM shell_session_recovery "
                "WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return str(row[0]), str(row[1]), str(row[2])

    def _load_projection(self, session_id: str) -> str | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT projection_json FROM shell_session_recovery WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        if row[0] is None:
            return _serialize_projection(BoundedConversationProjection())
        return str(row[0])

    def _save_projection(self, session_id: str, projection_json: str) -> None:
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE shell_session_recovery SET projection_json = ? WHERE session_id = ?",
                (projection_json, session_id),
            )
            if cursor.rowcount != 1:
                raise LookupError("session recovery projection is unavailable")
            connection.commit()
        finally:
            connection.close()

    def _revoke(self, session_id: str) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "DELETE FROM shell_session_recovery WHERE session_id = ?",
                (session_id,),
            )
            connection.commit()
        finally:
            connection.close()


def _verifier(salt: bytes, session_key: str) -> str:
    return hashlib.sha256(salt + session_key.encode()).hexdigest()


def _serialize_projection(projection: BoundedConversationProjection) -> str:
    payload = {
        "revision_contexts": [
            context.model_dump(mode="json") for context in projection.revision_contexts
        ],
        "turns": [turn.model_dump(mode="json") for turn in projection.turns],
        "version": 1,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _deserialize_projection(raw: str) -> BoundedConversationProjection:
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("unsupported session recovery projection version")
        if set(payload) != {"revision_contexts", "turns", "version"}:
            raise ValueError("session recovery projection shape is invalid")
        raw_turns = payload["turns"]
        raw_contexts = payload["revision_contexts"]
        if not isinstance(raw_turns, list) or not isinstance(raw_contexts, list):
            raise TypeError("session recovery projection collections are invalid")
        return BoundedConversationProjection(
            turns=tuple(ConversationTurn.model_validate(turn) for turn in raw_turns),
            revision_contexts=tuple(
                RevisionConversationContext.model_validate(context) for context in raw_contexts
            ),
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("session recovery projection is invalid") from exc


_SCHEMA = """
CREATE TABLE IF NOT EXISTS shell_session_recovery (
    session_id TEXT PRIMARY KEY,
    salt TEXT NOT NULL,
    verifier TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    projection_json TEXT
);
"""

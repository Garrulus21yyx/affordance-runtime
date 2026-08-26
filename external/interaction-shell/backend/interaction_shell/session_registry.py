"""Shell-private persisted authentication for process-boundary session recovery."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol


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

    async def revoke(self, session_id: str) -> None:
        await asyncio.to_thread(self._revoke, session_id)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.executescript(_SCHEMA)
        return connection

    def _register(
        self,
        session_id: str,
        salt: str,
        verifier: str,
        expires_at: str,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO shell_session_recovery "
                "(session_id, salt, verifier, expires_at) VALUES (?, ?, ?, ?)",
                (session_id, salt, verifier, expires_at),
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


_SCHEMA = """
CREATE TABLE IF NOT EXISTS shell_session_recovery (
    session_id TEXT PRIMARY KEY,
    salt TEXT NOT NULL,
    verifier TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""

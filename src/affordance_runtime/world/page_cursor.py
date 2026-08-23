"""Opaque stateless cursors bound to an exact Runtime action-page filter."""

from __future__ import annotations

import hashlib
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode


def cursor_fingerprint(
    action_space_id: str,
    query: str,
    objective_digest: str,
    limit: int,
    allowed_action_ids: tuple[str, ...] = (),
    public_route_byte_allocation: int = 0,
) -> str:
    payload = (
        action_space_id,
        query,
        objective_digest,
        limit,
        allowed_action_ids,
        public_route_byte_allocation,
    )
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()[:24]


def encode_cursor(offset: int, fingerprint: str) -> str:
    payload = json.dumps((offset, fingerprint), separators=(",", ":")).encode()
    return "cursor:" + urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str, expected_fingerprint: str) -> int:
    if not cursor.startswith("cursor:"):
        raise ValueError("action page cursor is malformed")
    encoded = cursor.removeprefix("cursor:")
    try:
        payload = urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        offset, fingerprint = json.loads(payload)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("action page cursor is malformed") from exc
    if not isinstance(offset, int) or offset < 0 or fingerprint != expected_fingerprint:
        raise ValueError("action page cursor does not match the active filter")
    return offset

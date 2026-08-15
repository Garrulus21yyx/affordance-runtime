"""Opaque stateless cursors bound to an exact Runtime action-page filter."""

from __future__ import annotations

import hashlib
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode

from affordance_runtime.actions.relevance import ActionRelevanceRole


def cursor_fingerprint(
    action_space_id: str,
    query: str,
    target_id: str,
    role: ActionRelevanceRole | None,
    objective_digest: str,
    limit: int,
    max_destinations: int,
    max_targets: int,
    allowed_action_ids: tuple[str, ...] = (),
) -> str:
    payload = (
        action_space_id,
        query,
        target_id,
        role.value if role else "",
        objective_digest,
        limit,
        max_destinations,
        max_targets,
        allowed_action_ids,
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

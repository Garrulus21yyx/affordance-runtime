"""Opaque stateless cursors bound to an exact Runtime action-page filter."""

from __future__ import annotations

import hashlib
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from enum import StrEnum
from typing import cast


class DeliveryCursorMode(StrEnum):
    ITEMS = "items"
    DETAIL = "detail"


@dataclass(frozen=True)
class DeliveryCursorPosition:
    """Typed position in one bounded Delivery stream."""

    mode: DeliveryCursorMode
    item_offset: int
    detail_index: int = 0
    detail_offset: int = 0
    leaf_prefix_chars: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.mode, DeliveryCursorMode):
            raise TypeError("delivery cursor mode must be typed")
        values = (self.item_offset, self.detail_index, self.detail_offset, self.leaf_prefix_chars)
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("delivery cursor positions must be non-negative integers")
        if self.mode is DeliveryCursorMode.ITEMS and any(values[1:]):
            raise ValueError("item cursor cannot carry detail state")


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


def encode_delivery_cursor(position: DeliveryCursorPosition, fingerprint: str) -> str:
    payload = json.dumps(
        {
            "mode": position.mode.value,
            "item_offset": position.item_offset,
            "detail_index": position.detail_index,
            "detail_offset": position.detail_offset,
            "leaf_prefix_chars": position.leaf_prefix_chars,
            "fingerprint": fingerprint,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return "cursor:" + urlsafe_b64encode(payload).decode().rstrip("=")


def decode_delivery_cursor(cursor: str, expected_fingerprint: str) -> DeliveryCursorPosition:
    if not cursor:
        return DeliveryCursorPosition(DeliveryCursorMode.ITEMS, 0)
    if not cursor.startswith("cursor:"):
        raise ValueError("delivery cursor is malformed")
    encoded = cursor.removeprefix("cursor:")
    try:
        payload = json.loads(urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if not isinstance(payload, dict) or payload.get("fingerprint") != expected_fingerprint:
            raise ValueError("delivery cursor does not match the active stream")
        positions = (
            payload.get("item_offset"),
            payload.get("detail_index", 0),
            payload.get("detail_offset", 0),
            payload.get("leaf_prefix_chars", 0),
        )
        if any(type(value) is not int for value in positions):
            raise ValueError("delivery cursor positions are invalid")
        typed_positions = cast(tuple[int, int, int, int], positions)
        return DeliveryCursorPosition(
            DeliveryCursorMode(str(payload.get("mode", ""))),
            typed_positions[0],
            typed_positions[1],
            typed_positions[2],
            typed_positions[3],
        )
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("delivery cursor is malformed") from exc

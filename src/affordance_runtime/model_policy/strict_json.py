"""Hostile-shape limits for structured model decision JSON."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from affordance_runtime.model_policy.contracts import MAX_MODEL_RESPONSE_BYTES

MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 2_048


class StrictJsonError(ValueError):
    """A bounded public classification for invalid structured JSON."""


def strict_json_loads(raw_payload: str) -> dict[str, Any]:
    if not isinstance(raw_payload, str):
        raise StrictJsonError("structured JSON exceeds its byte bound")
    try:
        if len(raw_payload.encode()) > MAX_MODEL_RESPONSE_BYTES:
            raise StrictJsonError("structured JSON exceeds its byte bound")
        value = json.loads(
            raw_payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, UnicodeError, RecursionError, OverflowError, StrictJsonError) as exc:
        raise StrictJsonError("structured JSON is invalid") from exc
    if not isinstance(value, dict):
        raise StrictJsonError("structured JSON top level must be an object")
    validate_json_tree(value)
    return value


def validate_json_tree(value: object) -> None:
    nodes = 0
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise StrictJsonError("structured JSON exceeds shape limits")
        if isinstance(item, float) and not math.isfinite(item):
            raise StrictJsonError("structured JSON contains a non-finite number")
        if item is None or isinstance(item, str | bool | int | float):
            continue
        if isinstance(item, Mapping):
            if any(not isinstance(key, str) for key in item):
                raise StrictJsonError("structured JSON object keys must be strings")
            stack.extend((child, depth + 1) for child in item.values())
            continue
        if isinstance(item, Sequence) and not isinstance(item, str | bytes | bytearray):
            stack.extend((child, depth + 1) for child in item)
            continue
        raise StrictJsonError("structured JSON contains an unsupported value")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError("structured JSON contains duplicate object keys")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise StrictJsonError(f"structured JSON contains non-standard constant {value}")

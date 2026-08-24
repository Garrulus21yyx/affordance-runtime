"""Small public-value predicates shared by World projections."""

from __future__ import annotations

import math

_MAX_VALUE_CHARS = 2_000


def is_public_scalar(value: object) -> bool:
    if isinstance(value, bool | int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, str) and len(value) <= _MAX_VALUE_CHARS

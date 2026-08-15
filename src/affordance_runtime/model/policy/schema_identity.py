"""Deterministic identity for the canonical provider decision schema."""

from __future__ import annotations

import hashlib
import json


def decision_schema_digest() -> str:
    from affordance_runtime.model.policy.spec import decision_response_schema

    encoded = json.dumps(
        decision_response_schema(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def grounding_guide_digest(serialized_guide: str) -> str:
    value = json.loads(serialized_guide)
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

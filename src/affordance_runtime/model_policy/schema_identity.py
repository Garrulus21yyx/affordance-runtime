"""Deterministic identity for the canonical provider decision schema."""

from __future__ import annotations

import hashlib
import json


def decision_schema_digest() -> str:
    from affordance_runtime.model_policy.spec import decision_response_schema

    encoded = json.dumps(
        decision_response_schema(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

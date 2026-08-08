"""Canonical digest for finite semantic parameter schemas."""

from __future__ import annotations

import hashlib
import json

from affordance_runtime.immutable import to_json_compatible


def schema_digest(schema: object) -> str:
    encoded = json.dumps(to_json_compatible(schema), sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()

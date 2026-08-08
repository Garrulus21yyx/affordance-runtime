"""Canonical, value-free evidence identities for public world projection."""

from __future__ import annotations

import hashlib
import re

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,180}$")
_SAFE_FACT = re.compile(r"^fact:[A-Za-z0-9][A-Za-z0-9._:-]{0,506}$")


def canonical_fact_ref(fact_id: str) -> str:
    candidate = fact_id if fact_id.startswith("fact:") else f"fact:{fact_id}"
    if _SAFE_FACT.fullmatch(candidate):
        return candidate
    return f"fact:id-{_digest(fact_id)}"


def canonical_artifact_ref(source_id: str, artifact_key: str) -> str:
    if _SAFE_COMPONENT.fullmatch(source_id) and _SAFE_COMPONENT.fullmatch(artifact_key):
        return f"artifact:{source_id}:{artifact_key}"
    return f"artifact:source-{_digest(source_id)}:key-{_digest(artifact_key)}"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

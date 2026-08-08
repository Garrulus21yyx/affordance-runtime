"""Secret-free conformance report primitives."""

from __future__ import annotations

from dataclasses import asdict

from .contracts import ConformanceAttempt


def public_attempt_payload(attempt: ConformanceAttempt) -> dict[str, object]:
    return asdict(attempt)


"""Bounded execution diagnostics created where an exception is first observed."""

from __future__ import annotations

import hashlib
import re
import traceback
from time import perf_counter

from affordance_runtime.execution.contracts import (
    ExecutionDiagnostic,
    ExecutionDiagnosticPhase,
    SessionHealth,
)

_URL = re.compile(r"(?i)\b(?:https?|wss?)://[^\s]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|token|secret|credential|api[_-]?key)\s*[:=]\s*[^\s,;]+"
)


def execution_diagnostic_from_exception(
    exc: BaseException,
    *,
    phase: ExecutionDiagnosticPhase,
    started_at: float,
    dispatch_crossed: bool,
    health: SessionHealth | None = None,
) -> ExecutionDiagnostic:
    """Project one exception without exposing traceback text or secret-bearing values."""

    traceback_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    traceback_digest = hashlib.sha256(traceback_text.encode("utf-8", errors="replace")).hexdigest()
    exception_type = _safe_identifier(type(exc).__name__, "Exception", 128)
    exception_module = _safe_module(type(exc).__module__)
    safe_message = _safe_exception_message(str(exc))
    elapsed_ms = round(max(0.0, (perf_counter() - started_at) * 1_000), 3)
    identity_material = "\0".join((
        phase.value,
        exception_module,
        exception_type,
        safe_message,
        traceback_digest,
        repr(started_at),
    ))
    diagnostic_ref = "execution-diagnostic:" + hashlib.sha256(
        identity_material.encode("utf-8"),
    ).hexdigest()[:24]
    return ExecutionDiagnostic(
        diagnostic_ref,
        phase,
        exception_type,
        exception_module,
        safe_message,
        elapsed_ms,
        dispatch_crossed,
        health.page_closed if health is not None else None,
        health.browser_connected if health is not None else None,
        f"traceback:sha256:{traceback_digest}",
    )


def _safe_exception_message(value: str) -> str:
    normalized = " ".join(value.split())
    normalized = _URL.sub("<redacted-url>", normalized)
    normalized = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=<redacted>", normalized)
    return normalized[:500]


def _safe_identifier(value: str, fallback: str, limit: int) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", value)[:limit]
    if not normalized or not re.match(r"[A-Za-z_]", normalized):
        normalized = f"_{normalized}" if normalized else fallback
    return normalized[:limit]


def _safe_module(value: str) -> str:
    parts = tuple(
        _safe_identifier(part, "unknown", 64)
        for part in value.split(".")
        if part
    )
    return ".".join(parts)[:200] or "builtins"

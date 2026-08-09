"""Atomic, secret-free progress reports for a running decision matrix."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .contracts import ModelProfileIdentity

PROGRESS_SCHEMA_VERSION = "compact-decision-matrix-progress.v1"


def write_matrix_progress(
    path: Path,
    *,
    identity: ModelProfileIdentity,
    repetitions: int,
    planned_attempt_count: int,
    attempts: Sequence[Any],
    complete: bool,
) -> None:
    """Atomically publish only completed, already-redacted attempts."""

    write_json_report(path, {
        "schema_version": PROGRESS_SCHEMA_VERSION,
        "identity": asdict(identity),
        "repetitions": repetitions,
        "planned_attempt_count": planned_attempt_count,
        "completed_attempt_count": len(attempts),
        "complete": complete,
        "attempts": [asdict(attempt) for attempt in attempts],
    })


def write_json_report(path: Path, value: Any) -> None:
    """Replace a JSON report atomically so readers never see partial JSON."""

    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)

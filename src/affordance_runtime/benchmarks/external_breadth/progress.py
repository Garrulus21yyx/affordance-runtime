"""Atomic observer-only campaign progress; never resume or replay authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from affordance_runtime.benchmarks.external_smoke.adapter_reporting import _atomic_json
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation


def case_progress_digest(result: object) -> str:
    """Bind observer progress to the final public case disposition."""

    payload = (
        getattr(result, "case_id", ""),
        getattr(result, "status", ""),
        getattr(result, "case_failure_code", ""),
        getattr(result, "terminal_reason_code", None),
    )
    encoded = json.dumps(payload, default=str, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass
class ProgressEventObserver:
    instrumentation: BenchmarkInstrumentation
    previous: tuple[tuple[str, str, str], ...] = ()

    def __call__(self, context: object) -> None:
        progress = getattr(context, "progress", None)
        section = getattr(progress, "events", None)
        items = tuple(getattr(section, "items", ()))
        current = tuple(
            (str(item.event_type), str(item.attempt_key_digest), str(item.observed_change))
            for item in items
        )
        overlap = _overlap(self.previous, current)
        for event_type, _digest, _effect in current[overlap:]:
            if event_type == "already_satisfied_selection":
                self.instrumentation.increment("already_satisfied_suppressions")
        self.previous = current


@dataclass
class CampaignProgressWriter:
    path: Path
    campaign_id: str
    run_id: str
    git_sha: str
    manifest_digest: str
    planned_cases: int
    completed_cases: int = 0
    success_count: int = 0
    failure_category_counts: dict[str, int] = field(default_factory=dict)
    provider_attempts: int = 0
    total_tokens: int = 0
    model_latency_ms: float = 0.0
    last_completed_case_digest: str = ""

    def write(self, *, current_case_id: str = "", complete: bool = False) -> None:
        _atomic_json(self.path, {
            "schema_version": "miniwob-breadth-progress.v1",
            "campaign_id": self.campaign_id,
            "run_id": self.run_id,
            "git_sha": self.git_sha,
            "manifest_digest": self.manifest_digest,
            "planned_cases": self.planned_cases,
            "completed_cases": self.completed_cases,
            "current_case_id": current_case_id,
            "complete": complete,
            "success_count": self.success_count,
            "failure_category_counts": self.failure_category_counts,
            "provider_attempts": self.provider_attempts,
            "total_tokens": self.total_tokens,
            "model_latency_ms": self.model_latency_ms,
            "last_completed_case_digest": self.last_completed_case_digest,
        })


def _overlap(previous: tuple[object, ...], current: tuple[object, ...]) -> int:
    maximum = min(len(previous), len(current))
    for size in range(maximum, -1, -1):
        if previous[-size:] == current[:size] if size else True:
            return size
    return 0

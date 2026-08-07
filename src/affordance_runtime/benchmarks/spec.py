"""Benchmark task contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BenchmarkTask:
    suite: str
    task_id: str
    start_url: str
    goal: str
    max_steps: int = 20
    tags: list[str] = field(default_factory=list)
    oracle: dict[str, Any] = field(default_factory=dict)
    perturbations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BenchmarkRun:
    task_id: str
    success: bool
    steps: int
    latency_ms: float
    stale_actions_blocked: int = 0
    effect_receipts: int = 0
    verifier_false_accepts: int = 0
    unsafe_side_effects: int = 0
    recovery_attempts: int = 0
    recovery_successes: int = 0
    recovery_incidents: int = 0
    recovery_cascade_depth: int = 0
    repeated_recovery_failures: int = 0
    recovery_loop_aborts: int = 0
    effective_recovery_actions: int = 0
    duplicate_effect_risks: int = 0
    semantic_replay_success: bool = False
    regression_delta: float = 0.0
    cost: float = 0.0
    failure_reason: str = ""
    variant: str = "full_runtime"
    seed: int = 0
    evaluated_constraints: int = 0
    constraint_violations: int = 0
    stale_action_opportunities: int = 0
    effectful_actions: int = 0
    failed_outcomes: int = 0
    side_effect_opportunities: int = 0
    trace_path: str = ""
    fixture_variant: str = ""

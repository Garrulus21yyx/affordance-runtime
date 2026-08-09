"""Aggregate report contracts for exact two-stage profile runs."""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import ModelProfileIdentity
from .contracts import PacingConfiguration, TwoStageMatrixResult
from .qualification import TwoStageQualification


@dataclass(frozen=True)
class SingleStageBaselineSummary:
    success_count: int
    attempt_count: int
    provider_calls: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    failure_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class TwoStageSuiteReport:
    schema_version: str
    run_id: str
    profile_identity: ModelProfileIdentity
    mode: str
    repetitions: int
    pacing: PacingConfiguration
    baseline: SingleStageBaselineSummary
    routing: TwoStageMatrixResult
    payload: TwoStageMatrixResult
    end_to_end: TwoStageMatrixResult
    critical: TwoStageMatrixResult
    qualification: TwoStageQualification

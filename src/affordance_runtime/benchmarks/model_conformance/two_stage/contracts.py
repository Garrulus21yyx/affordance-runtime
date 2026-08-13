"""Benchmark-owned contracts for two-stage decision diagnostics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_PUBLIC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,239}$")


class DecisionKind(StrEnum):
    SELECT_ACTION = "select_action"
    REQUEST_OBSERVATION = "request_observation"
    REQUEST_ACTION_PAGE = "request_action_page"
    ASK_USER = "ask_user"
    PROPOSE_DONE = "propose_done"
    WAIT = "wait"
    ABORT = "abort"


@dataclass(frozen=True)
class DecisionKindRoute:
    context_id: str
    decision_type: DecisionKind

    def __post_init__(self) -> None:
        _require_public_id(self.context_id, "route context_id")
        object.__setattr__(self, "decision_type", DecisionKind(self.decision_type))


@dataclass(frozen=True)
class TwoStageDecisionIdentity:
    logical_decision_id: str
    context_id: str
    routing_attempt_id: str
    payload_attempt_id: str

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            _require_public_id(value, name)


@dataclass(frozen=True)
class StageCallCounts:
    routing_attempts: int
    payload_attempts: int
    retry_count: int = 0
    fallback_count: int = 0

    def __post_init__(self) -> None:
        if self.routing_attempts not in {0, 1} or self.payload_attempts not in {0, 1}:
            raise ValueError("a logical decision allows at most one call per stage")
        if self.payload_attempts and not self.routing_attempts:
            raise ValueError("payload stage requires a routing stage")
        if self.retry_count or self.fallback_count:
            raise ValueError("two-stage diagnostics forbid retry and fallback")

    @property
    def total_provider_attempts(self) -> int:
        return self.routing_attempts + self.payload_attempts


@dataclass(frozen=True)
class PacingConfiguration:
    inter_stage_delay_s: float = 0.0
    inter_attempt_delay_s: float = 0.0

    def __post_init__(self) -> None:
        if not 0 <= self.inter_stage_delay_s <= 120:
            raise ValueError("inter-stage delay must be in [0, 120]")
        if not 0 <= self.inter_attempt_delay_s <= 120:
            raise ValueError("inter-attempt delay must be in [0, 120]")


class TwoStageRunMode(StrEnum):
    ROUTING_ONLY = "routing_only"
    PAYLOAD_ONLY = "payload_only"
    END_TO_END = "end_to_end"


@dataclass(frozen=True)
class TwoStageAttemptResult:
    logical_decision_id: str
    case_id: str
    mode: TwoStageRunMode
    expected_kind: DecisionKind
    routed_kind: DecisionKind | None
    routing_correct: bool
    payload_correct: bool
    runtime_correct: bool
    success: bool
    failure_category: str
    routing_provider_attempts: int
    payload_provider_attempts: int
    provider_calls: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float


@dataclass(frozen=True)
class TwoStageMatrixResult:
    schema_version: str
    run_id: str
    mode: TwoStageRunMode
    repetitions: int
    pacing: PacingConfiguration
    attempts: tuple[TwoStageAttemptResult, ...]
    success_count: int
    provider_calls: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    retry_count: int
    fallback_count: int
    runtime_control_success_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", TwoStageRunMode(self.mode))
        if self.retry_count or self.fallback_count:
            raise ValueError("two-stage result cannot admit retry or fallback")


def _require_public_id(value: str, name: str) -> None:
    if _PUBLIC_ID.fullmatch(value) is None or "://" in value:
        raise ValueError(f"{name} must be a bounded public identifier")

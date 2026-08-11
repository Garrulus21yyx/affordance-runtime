"""Canonical typed Runtime terminal-failure truth."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.agent.result_code import AgentFailureCode
from affordance_runtime.model_boundary.failures import ModelFailureKind

_CODE = re.compile(r"[a-z][a-z0-9_.:-]{0,95}")
_EXCEPTION = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
_ROOT_ID = re.compile(r"transition:[1-9][0-9]{0,9}:[0-9a-f]{20}")
_ATTEMPT_ID = re.compile(r"attempt:[1-9][0-9]{0,9}")


class FailureStage(StrEnum):
    CONTROL = "control"
    POLICY = "policy"
    ACQUISITION = "acquisition"
    EXECUTION = "execution"
    EVALUATION = "evaluation"
    SESSION = "session"


class FailureKind(StrEnum):
    CALL_FAILED = "call_failed"
    INVALID_OUTPUT = "invalid_output"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    NO_PROGRESS = "no_progress"
    INTERNAL = "internal"


_SUPPORTED_STAGE_KINDS = {
    FailureStage.CONTROL: {FailureKind.REJECTED, FailureKind.NO_PROGRESS},
    FailureStage.POLICY: {FailureKind.CALL_FAILED, FailureKind.INVALID_OUTPUT},
    FailureStage.ACQUISITION: {
        FailureKind.CALL_FAILED,
        FailureKind.INVALID_OUTPUT,
        FailureKind.CAPABILITY_UNAVAILABLE,
    },
    FailureStage.EXECUTION: {FailureKind.CALL_FAILED, FailureKind.INVALID_OUTPUT},
    FailureStage.EVALUATION: {FailureKind.CALL_FAILED, FailureKind.INVALID_OUTPUT},
    FailureStage.SESSION: {
        FailureKind.CALL_FAILED,
        FailureKind.CANCELLED,
        FailureKind.INTERNAL,
    },
}
SUPPORTED_RUNTIME_FAILURE_PAIRS = frozenset(
    (stage, kind)
    for stage, kinds in _SUPPORTED_STAGE_KINDS.items()
    for kind in kinds
)


@dataclass(frozen=True)
class RuntimeFailure:
    stage: FailureStage
    kind: FailureKind
    code: str
    root_id: str = ""
    attempt_id: str = ""
    exception_class: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.stage, FailureStage):
            raise TypeError("RuntimeFailure stage must be typed")
        if not isinstance(self.kind, FailureKind):
            raise TypeError("RuntimeFailure kind must be typed")
        if self.kind not in _SUPPORTED_STAGE_KINDS[self.stage]:
            raise ValueError("RuntimeFailure stage and kind are inconsistent")
        if _CODE.fullmatch(self.code) is None:
            raise ValueError("RuntimeFailure code must be a bounded namespaced token")
        if self.root_id and _ROOT_ID.fullmatch(self.root_id) is None:
            raise ValueError("RuntimeFailure root identity is invalid")
        if self.attempt_id and _ATTEMPT_ID.fullmatch(self.attempt_id) is None:
            raise ValueError("RuntimeFailure attempt identity is invalid")
        if self.attempt_id and not self.root_id:
            raise ValueError("RuntimeFailure attempt identity requires its root")
        if self.exception_class and _EXCEPTION.fullmatch(self.exception_class) is None:
            raise ValueError("RuntimeFailure exception class must be bounded")


_ACQUISITION_CODES = {
    AgentFailureCode.OBSERVATION_ACQUISITION_FAILED,
    AgentFailureCode.OBSERVATION_FRESHNESS_INVALID,
    AgentFailureCode.OBSERVATION_ORIGIN_INVALID,
    AgentFailureCode.POST_ACTION_ACQUISITION_FAILED,
    AgentFailureCode.POST_ACTION_FRESHNESS_INVALID,
    AgentFailureCode.POST_ACTION_ORIGIN_INVALID,
}
_CAPABILITY_CODES = {
    AgentFailureCode.OBSERVATION_CAPABILITY_UNAVAILABLE,
    AgentFailureCode.POST_ACTION_CAPABILITY_UNAVAILABLE,
}
_INVALID_POLICY_OUTPUTS = {
    ModelFailureKind.INVALID_RESPONSE,
    ModelFailureKind.SCHEMA_ERROR,
}


def runtime_failure_from_outcome(
    outcome, *, root_id: str = "", attempt_id: str = "",
) -> RuntimeFailure | None:
    """Convert typed terminal outcome fields without inspecting display text or code prefixes."""

    status = outcome.status
    if str(status) in {"done", "waiting_user", "waiting_confirmation"}:
        return None
    if outcome.failure_stage is not None:
        return RuntimeFailure(
            outcome.failure_stage,
            outcome.failure_kind,
            outcome.reason_code,
            root_id,
            attempt_id,
            outcome.exception_class,
        )
    if outcome.policy_failure is not None:
        policy_kind = outcome.policy_failure.kind
        kind = (
            FailureKind.INVALID_OUTPUT
            if policy_kind in _INVALID_POLICY_OUTPUTS
            else FailureKind.CALL_FAILED
        )
        return RuntimeFailure(FailureStage.POLICY, kind, str(policy_kind))
    if outcome.failure_code is AgentFailureCode.NO_PROGRESS_REPETITION:
        return RuntimeFailure(
            FailureStage.CONTROL,
            FailureKind.NO_PROGRESS,
            str(outcome.failure_code),
            root_id,
            attempt_id,
        )
    if outcome.failure_code in _CAPABILITY_CODES:
        return RuntimeFailure(
            FailureStage.ACQUISITION,
            FailureKind.CAPABILITY_UNAVAILABLE,
            str(outcome.failure_code),
            root_id,
            attempt_id,
        )
    if outcome.failure_code in _ACQUISITION_CODES:
        return RuntimeFailure(
            FailureStage.ACQUISITION,
            FailureKind.CALL_FAILED,
            str(outcome.failure_code),
            root_id,
            attempt_id,
        )
    if str(status) == "cancelled":
        return RuntimeFailure(
            FailureStage.SESSION, FailureKind.CANCELLED, outcome.reason_code,
            root_id, attempt_id,
        )
    if str(status) == "failed":
        return RuntimeFailure(FailureStage.SESSION, FailureKind.CALL_FAILED, outcome.reason_code)
    return RuntimeFailure(FailureStage.CONTROL, FailureKind.REJECTED, outcome.reason_code)

"""Closed count-free control dispositions used inside the AgentLoop."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.result_code import AgentFailureCode
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage

if TYPE_CHECKING:
    from affordance_runtime.agent.state import AgentLoopStatus

_CODE = re.compile(r"[a-z][a-z0-9_]{0,95}")


@dataclass(frozen=True)
class Continue:
    reason_code: str = "continued"

    def __post_init__(self) -> None:
        _validate(self.reason_code)


@dataclass(frozen=True)
class Pause:
    status: AgentLoopStatus
    reason_code: str
    message: str = ""
    failure_code: AgentFailureCode | None = None
    policy_failure: PolicyFailure | None = None

    def __post_init__(self) -> None:
        from affordance_runtime.agent.state import AgentLoopStatus

        if not isinstance(self.status, AgentLoopStatus):
            raise TypeError("Pause status must be typed")
        if str(self.status) not in {"waiting_user", "waiting_confirmation"}:
            raise ValueError("Pause requires a nonterminal waiting status")
        _validate(self.reason_code)


@dataclass(frozen=True)
class Terminate:
    status: AgentLoopStatus
    reason_code: str
    message: str = ""
    failure_code: AgentFailureCode | None = None
    policy_failure: PolicyFailure | None = None
    failure_stage: FailureStage | None = None
    failure_kind: FailureKind | None = None
    exception_class: str = ""

    def __post_init__(self) -> None:
        from affordance_runtime.agent.state import AgentLoopStatus

        if not isinstance(self.status, AgentLoopStatus):
            raise TypeError("Terminate status must be typed")
        if str(self.status) not in {"done", "blocked", "cancelled", "failed"}:
            raise ValueError("Terminate requires a terminal status")
        if (self.failure_stage is None) != (self.failure_kind is None):
            raise ValueError("terminal failure stage and kind must be present together")
        if self.failure_stage is not None and not isinstance(self.failure_stage, FailureStage):
            raise TypeError("terminal failure stage must be typed")
        if self.failure_kind is not None and not isinstance(self.failure_kind, FailureKind):
            raise TypeError("terminal failure kind must be typed")
        _validate(self.reason_code)


LoopDirective: TypeAlias = Continue | Pause | Terminate


def directive(
    status: AgentLoopStatus,
    reason_code: str,
    message: str = "",
    *,
    failure_code: AgentFailureCode | None = None,
    policy_failure: PolicyFailure | None = None,
    failure_stage: FailureStage | None = None,
    failure_kind: FailureKind | None = None,
) -> LoopDirective:
    if str(status) in {"waiting_user", "waiting_confirmation"}:
        return Pause(status, reason_code, message, failure_code, policy_failure)
    return Terminate(
        status, reason_code, message, failure_code, policy_failure,
        failure_stage, failure_kind,
    )


def _validate(value: str) -> None:
    if _CODE.fullmatch(value) is None:
        raise ValueError("control reason code must be bounded stable snake-case")

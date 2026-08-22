"""Typed operational recovery signals owned by the single agent loop."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.agent.attempt_signature import PublicAttemptSignature
from affordance_runtime.immutable import freeze_json


class EpisodeMonitorEvent(StrEnum):
    STATE_CHANGED = "state_changed"
    NO_OBSERVED_CHANGE = "no_observed_change"
    REPEATED_ACTION = "repeated_action"
    OSCILLATION = "oscillation"
    ROUTE_REGRESSION = "route_regression"
    FORMAL_CRITERION_CHANGED = "formal_criterion_changed"
    PROVIDER_FAILURE = "provider_failure"
    ENVIRONMENT_FAILURE = "environment_failure"
    CAPABILITY_GAP = "capability_gap"


class EpisodeMonitorRecommendation(StrEnum):
    CONTINUE = "continue"
    RECOVER = "recover"
    BLOCK = "block"


class RecoveryKind(StrEnum):
    GROUNDING_STALL = "grounding_stall"
    EFFECT_STALL = "effect_stall"
    UNCERTAIN_EFFECT = "uncertain_effect"
    STATE_OSCILLATION = "state_oscillation"
    ROUTE_REGRESSION = "route_regression"
    CONTROL_STALL = "control_stall"
    STRATEGY_STALL = "strategy_stall"
    CAPABILITY_GAP = "capability_gap"


@dataclass(frozen=True)
class RecoverySignal:
    kind: RecoveryKind
    stable_signature: str
    observed_evidence: Mapping[str, object]
    attempted_modes: tuple[str, ...] = ()
    prohibited_attempt_signature: PublicAttemptSignature | None = None
    human_instruction: str = ""
    recovery_attempt: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RecoveryKind):
            object.__setattr__(self, "kind", RecoveryKind(self.kind))
        if not self.stable_signature.strip() or len(self.stable_signature) > 1_000:
            raise ValueError("recovery signature must be bounded")
        object.__setattr__(self, "observed_evidence", freeze_json(dict(self.observed_evidence)))
        object.__setattr__(self, "attempted_modes", tuple(self.attempted_modes))
        if len(self.attempted_modes) > 32 or len(set(self.attempted_modes)) != len(self.attempted_modes):
            raise ValueError("attempted recovery modes must be bounded and unique")
        if self.prohibited_attempt_signature is not None and not isinstance(
            self.prohibited_attempt_signature, PublicAttemptSignature
        ):
            raise TypeError("prohibited attempt signature must be typed")
        if len(self.human_instruction) > 1_000 or not 1 <= self.recovery_attempt <= 3:
            raise ValueError("recovery signal exceeds bounds")


@dataclass(frozen=True)
class EpisodeMonitorTransition:
    events: tuple[EpisodeMonitorEvent, ...]
    recommendation: EpisodeMonitorRecommendation
    reason: str = ""
    recovery_signal: RecoverySignal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))
        if any(not isinstance(item, EpisodeMonitorEvent) for item in self.events):
            raise TypeError("episode monitor events must be typed")
        if not isinstance(self.recommendation, EpisodeMonitorRecommendation):
            raise TypeError("episode monitor recommendation must be typed")
        if self.recovery_signal is not None and not isinstance(self.recovery_signal, RecoverySignal):
            raise TypeError("episode monitor recovery signal must be typed")

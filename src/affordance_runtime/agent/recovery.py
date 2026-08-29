"""Typed operational recovery signals owned by the single agent loop."""

from __future__ import annotations

import hashlib
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
    ROUTE_REVIEW = "route_review"
    FORMAL_CRITERION_CHANGED = "formal_criterion_changed"
    PROVIDER_FAILURE = "provider_failure"
    ENVIRONMENT_FAILURE = "environment_failure"
    CAPABILITY_GAP = "capability_gap"


class EpisodeMonitorRecommendation(StrEnum):
    CONTINUE = "continue"
    RECOVER = "recover"
    BLOCK = "block"


class RecoveryLifecycleTransition(StrEnum):
    """Describe the authoritative lifecycle change produced by EpisodeMonitor."""

    NONE = "none"
    STARTED = "started"
    CONTINUED = "continued"
    CLOSED = "closed"


class RecoveryKind(StrEnum):
    GROUNDING_STALL = "grounding_stall"
    EFFECT_STALL = "effect_stall"
    UNCERTAIN_EFFECT = "uncertain_effect"
    STATE_OSCILLATION = "state_oscillation"
    STRATEGY_REVIEW = "strategy_review"
    CONTROL_STALL = "control_stall"
    CAPABILITY_GAP = "capability_gap"


@dataclass(frozen=True)
class RecoverySignal:
    kind: RecoveryKind
    stable_signature: str
    observed_evidence: Mapping[str, object]
    attempted_modes: tuple[str, ...] = ()
    prohibited_attempt_signatures: tuple[PublicAttemptSignature, ...] = ()
    human_instruction: str = ""
    recovery_attempt: int = 1
    epoch_id: str = ""
    evidence_revision: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RecoveryKind):
            object.__setattr__(self, "kind", RecoveryKind(self.kind))
        if not self.stable_signature.strip() or len(self.stable_signature) > 1_000:
            raise ValueError("recovery signature must be bounded")
        if not self.epoch_id:
            digest = hashlib.sha256(self.stable_signature.encode()).hexdigest()
            object.__setattr__(self, "epoch_id", f"recovery:sha256:{digest}")
        if not self.epoch_id.startswith("recovery:") or len(self.epoch_id) > 200:
            raise ValueError("recovery epoch identity must be bounded")
        if not 1 <= self.evidence_revision <= 10_000:
            raise ValueError("recovery evidence revision must be bounded")
        object.__setattr__(self, "observed_evidence", freeze_json(dict(self.observed_evidence)))
        object.__setattr__(self, "attempted_modes", tuple(self.attempted_modes))
        if len(self.attempted_modes) > 32 or len(set(self.attempted_modes)) != len(self.attempted_modes):
            raise ValueError("attempted recovery modes must be bounded and unique")
        prohibited = tuple(self.prohibited_attempt_signatures)
        if len(prohibited) > 16 or len(set(prohibited)) != len(prohibited):
            raise ValueError("prohibited attempt signatures must be bounded and unique")
        if any(not isinstance(item, PublicAttemptSignature) for item in prohibited):
            raise TypeError("prohibited attempt signatures must be typed")
        object.__setattr__(self, "prohibited_attempt_signatures", prohibited)
        if len(self.human_instruction) > 1_000 or not 1 <= self.recovery_attempt <= 3:
            raise ValueError("recovery signal exceeds bounds")

    @property
    def prohibited_attempt_signature(self) -> PublicAttemptSignature | None:
        """Compatibility projection while consumers migrate to the bounded set."""

        return self.prohibited_attempt_signatures[-1] if self.prohibited_attempt_signatures else None


@dataclass(frozen=True)
class EpisodeMonitorTransition:
    events: tuple[EpisodeMonitorEvent, ...]
    recommendation: EpisodeMonitorRecommendation
    reason: str = ""
    recovery_signal: RecoverySignal | None = None
    recovery_lifecycle: RecoveryLifecycleTransition = RecoveryLifecycleTransition.NONE

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))
        if any(not isinstance(item, EpisodeMonitorEvent) for item in self.events):
            raise TypeError("episode monitor events must be typed")
        if not isinstance(self.recommendation, EpisodeMonitorRecommendation):
            raise TypeError("episode monitor recommendation must be typed")
        if self.recovery_signal is not None and not isinstance(self.recovery_signal, RecoverySignal):
            raise TypeError("episode monitor recovery signal must be typed")
        if not isinstance(self.recovery_lifecycle, RecoveryLifecycleTransition):
            raise TypeError("episode monitor recovery lifecycle must be typed")
        if self.recovery_lifecycle in {
            RecoveryLifecycleTransition.STARTED,
            RecoveryLifecycleTransition.CONTINUED,
        } and self.recovery_signal is None:
            raise ValueError("active recovery lifecycle requires its signal")
        if self.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED and self.recovery_signal is not None:
            raise ValueError("closed recovery lifecycle cannot retain a signal")

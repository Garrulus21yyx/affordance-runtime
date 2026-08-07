"""Freshness-bound cache of verified route hints.

The cache stores no executable authority. Recall succeeds only when the caller
supplies a newly grounded candidate with matching source/executor/fingerprint
that is current for the supplied observation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time

from affordance_runtime.contracts import Observation
from affordance_runtime.grounding import GroundingCandidate, GroundingSource
from affordance_runtime.route_calibration import RouteOutcome, RouteOutcomeStatus


@dataclass(frozen=True)
class BindingCacheKey:
    task_signature: str
    semantic_target_id: str
    action_kind: str
    environment_scope: str

    def __post_init__(self) -> None:
        if not all(
            (
                self.task_signature,
                self.semantic_target_id,
                self.action_kind,
                self.environment_scope,
            )
        ):
            raise ValueError("binding cache key fields cannot be blank")


@dataclass(frozen=True)
class BindingHint:
    source: GroundingSource
    executor: str
    target_fingerprint: str
    verified_outcome_id: str
    remembered_at_s: float = field(default_factory=time)


@dataclass
class BindingCache:
    entries: dict[BindingCacheKey, BindingHint] = field(default_factory=dict)

    def remember(
        self,
        key: BindingCacheKey,
        candidate: GroundingCandidate,
        outcome: RouteOutcome,
    ) -> None:
        if outcome.status != RouteOutcomeStatus.VERIFIED_SUCCESS:
            raise ValueError("binding hints require independently verified success")
        if outcome.semantic_target_id != key.semantic_target_id:
            raise ValueError("verified outcome target does not match binding cache key")
        if outcome.candidate_id != candidate.candidate_id:
            raise ValueError("verified outcome candidate does not match binding hint")
        if not candidate.target_fingerprint:
            raise ValueError("binding hints require a target fingerprint")
        self.entries[key] = BindingHint(
            source=candidate.source,
            executor=candidate.compatible_executor,
            target_fingerprint=candidate.target_fingerprint,
            verified_outcome_id=outcome.outcome_id,
        )

    def recall(
        self,
        key: BindingCacheKey,
        candidates: tuple[GroundingCandidate, ...],
        observation: Observation,
    ) -> GroundingCandidate | None:
        hint = self.entries.get(key)
        if hint is None:
            return None
        matches = tuple(
            candidate
            for candidate in candidates
            if candidate.semantic_target_id == key.semantic_target_id
            and candidate.source == hint.source
            and candidate.compatible_executor == hint.executor
            and candidate.target_fingerprint == hint.target_fingerprint
            and candidate.is_current(observation)
            and (not candidate.expires_at_s or time() <= candidate.expires_at_s)
        )
        return matches[0] if len(matches) == 1 else None

    def forget(self, key: BindingCacheKey) -> None:
        self.entries.pop(key, None)

    def clear_environment(self, environment_scope: str) -> None:
        for key in tuple(self.entries):
            if key.environment_scope == environment_scope:
                del self.entries[key]

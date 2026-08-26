"""BrowserGym-native task outcome evaluation with current World lineage."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol, cast

from affordance_runtime.evaluation.contracts import (
    TaskEvaluation,
    TaskEvaluationStatus,
    TaskOutcomeFact,
    TaskOutcomeKind,
)
from affordance_runtime.surfaces.browsergym.task_state import (
    BROWSERGYM_TASK_STATE_EVIDENCE_KEY,
    BrowserGymTaskStateSnapshot,
    BrowserGymTaskStateSource,
)
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.evidence_refs import canonical_artifact_ref

_MISSING = object()


class BrowserGymTaskStatus(StrEnum):
    SUCCESS = "success"
    INCOMPLETE = "incomplete"
    TERMINAL_FAILURE = "terminal_failure"
    UNAVAILABLE = "unavailable"


class BrowserGymTaskReason(StrEnum):
    VERIFIED_SUCCESS = "verified_success"
    VERIFIED_RUNNING = "verified_running"
    VERIFIED_TERMINAL_FAILURE = "verified_terminal_task_failure"
    MISSING_FACTS = "missing_facts"
    INVALID_FACTS = "invalid_facts"
    NON_FINITE_FACTS = "non_finite_facts"
    INCONSISTENT_FACTS = "inconsistent_facts"
    SOURCE_INSUFFICIENT = "source_insufficient"
    UNSUPPORTED_STATE = "unsupported_state"


@dataclass(frozen=True)
class BrowserGymTaskAssessment:
    task_run_id: str
    observation_id: str
    source_observation_id: str
    source: BrowserGymTaskStateSource
    status: BrowserGymTaskStatus
    reason: BrowserGymTaskReason
    evidence_refs: tuple[str, ...] = ()


class BrowserGymTaskStatePort(Protocol):
    def current_task_state(self) -> BrowserGymTaskStateSnapshot: ...


@dataclass(frozen=True)
class BrowserGymTaskEvaluator:
    """Terminate only from the current provider-native BrowserGym task facts."""

    source: BrowserGymTaskStatePort

    async def evaluate(self, task, observation: WorldObservation) -> TaskEvaluation:
        assessment = assess_browsergym_task_state(self.source.current_task_state())
        current_source_ids = {item.observation_id for item in observation.sources}
        lineage = {assessment.observation_id, assessment.source_observation_id}
        if not (
            lineage == {observation.observation_id}
            or len(lineage) == 1
            and assessment.source_observation_id in current_source_ids
        ):
            assessment = replace(
                assessment,
                observation_id=observation.observation_id,
                source_observation_id=observation.observation_id,
                status=BrowserGymTaskStatus.UNAVAILABLE,
                reason=BrowserGymTaskReason.SOURCE_INSUFFICIENT,
                evidence_refs=(),
            )
        task_status = {
            BrowserGymTaskStatus.SUCCESS: TaskEvaluationStatus.COMPLETE,
            BrowserGymTaskStatus.INCOMPLETE: TaskEvaluationStatus.INCOMPLETE,
            BrowserGymTaskStatus.TERMINAL_FAILURE: TaskEvaluationStatus.BLOCKED,
            BrowserGymTaskStatus.UNAVAILABLE: TaskEvaluationStatus.UNKNOWN,
        }[assessment.status]
        outcome_kind = {
            BrowserGymTaskStatus.SUCCESS: TaskOutcomeKind.TERMINAL_SUCCESS,
            BrowserGymTaskStatus.INCOMPLETE: TaskOutcomeKind.RUNNING_INCOMPLETE,
            BrowserGymTaskStatus.TERMINAL_FAILURE: TaskOutcomeKind.TERMINAL_FAILURE,
            BrowserGymTaskStatus.UNAVAILABLE: TaskOutcomeKind.VERIFIER_UNAVAILABLE,
        }[assessment.status]
        refs = assessment.evidence_refs
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            task_status,
            f"BrowserGym native task state: {assessment.reason.value}",
            completion_evidence_refs=(refs if outcome_kind is TaskOutcomeKind.TERMINAL_SUCCESS else ()),
            outcome=TaskOutcomeFact(outcome_kind, assessment.reason.value, refs),
        )


def assess_browsergym_task_state(snapshot: BrowserGymTaskStateSnapshot) -> BrowserGymTaskAssessment:
    source = snapshot.source
    values = {
        name: snapshot.value(name, _MISSING)
        for name in ("reward", "raw_reward", "terminated", "truncated", "done", "ready")
    }
    required_names = (
        ("raw_reward", "done", "ready")
        if source is BrowserGymTaskStateSource.READ_ONLY_PROBE
        else ("reward", "raw_reward", "terminated", "truncated", "done", "ready")
    )
    required = tuple(values[name] for name in required_names)
    if any(value is _MISSING for value in required):
        return _assessment(snapshot, BrowserGymTaskStatus.UNAVAILABLE, BrowserGymTaskReason.MISSING_FACTS)

    numeric_names = ("raw_reward",) if source is BrowserGymTaskStateSource.READ_ONLY_PROBE else ("reward", "raw_reward")
    numeric = tuple(values[name] for name in numeric_names)
    if any(type(value) not in {int, float} for value in numeric):
        return _assessment(snapshot, BrowserGymTaskStatus.UNAVAILABLE, BrowserGymTaskReason.INVALID_FACTS)
    if any(isinstance(value, float) and not math.isfinite(value) for value in numeric):
        return _assessment(
            snapshot,
            BrowserGymTaskStatus.UNAVAILABLE,
            BrowserGymTaskReason.NON_FINITE_FACTS,
        )

    boolean_names = (
        ("done", "ready")
        if source is BrowserGymTaskStateSource.READ_ONLY_PROBE
        else ("terminated", "truncated", "done", "ready")
    )
    if any(type(values[name]) is not bool for name in boolean_names):
        return _assessment(snapshot, BrowserGymTaskStatus.UNAVAILABLE, BrowserGymTaskReason.INVALID_FACTS)

    reward = cast(int | float, values["reward"]) if source is not BrowserGymTaskStateSource.READ_ONLY_PROBE else 0
    raw_reward = cast(int | float, values["raw_reward"])
    terminated = values["terminated"]
    truncated = values["truncated"]
    done = values["done"]
    ready = values["ready"]
    if source is BrowserGymTaskStateSource.RESET:
        if reward == raw_reward == 0 and terminated is truncated is done is False and ready is True:
            return _assessment(
                snapshot,
                BrowserGymTaskStatus.INCOMPLETE,
                BrowserGymTaskReason.VERIFIED_RUNNING,
            )
        return _assessment(
            snapshot,
            BrowserGymTaskStatus.UNAVAILABLE,
            BrowserGymTaskReason.UNSUPPORTED_STATE,
        )
    if source is BrowserGymTaskStateSource.READ_ONLY_PROBE:
        if ready is True and done is False and raw_reward == 0:
            return _assessment(
                snapshot,
                BrowserGymTaskStatus.INCOMPLETE,
                BrowserGymTaskReason.VERIFIED_RUNNING,
            )
        if ready is True and done is True:
            return _assessment(
                snapshot,
                BrowserGymTaskStatus.SUCCESS if raw_reward > 0 else BrowserGymTaskStatus.TERMINAL_FAILURE,
                (
                    BrowserGymTaskReason.VERIFIED_SUCCESS
                    if raw_reward > 0
                    else BrowserGymTaskReason.VERIFIED_TERMINAL_FAILURE
                ),
            )
        return _assessment(
            snapshot,
            BrowserGymTaskStatus.UNAVAILABLE,
            BrowserGymTaskReason.INCONSISTENT_FACTS,
        )
    if truncated is True:
        return _assessment(
            snapshot,
            BrowserGymTaskStatus.UNAVAILABLE,
            BrowserGymTaskReason.UNSUPPORTED_STATE,
        )
    if terminated is True and done is True and ready is True:
        if reward > 0 and raw_reward > 0:
            return _assessment(
                snapshot,
                BrowserGymTaskStatus.SUCCESS,
                BrowserGymTaskReason.VERIFIED_SUCCESS,
            )
        if reward == 0 and raw_reward <= 0:
            return _assessment(
                snapshot,
                BrowserGymTaskStatus.TERMINAL_FAILURE,
                BrowserGymTaskReason.VERIFIED_TERMINAL_FAILURE,
            )
    if reward == raw_reward == 0 and terminated is done is False and ready is True:
        return _assessment(
            snapshot,
            BrowserGymTaskStatus.INCOMPLETE,
            BrowserGymTaskReason.VERIFIED_RUNNING,
        )
    return _assessment(
        snapshot,
        BrowserGymTaskStatus.UNAVAILABLE,
        BrowserGymTaskReason.INCONSISTENT_FACTS,
    )


def _assessment(
    snapshot: BrowserGymTaskStateSnapshot,
    status: BrowserGymTaskStatus,
    reason: BrowserGymTaskReason,
) -> BrowserGymTaskAssessment:
    refs = (
        (
            canonical_artifact_ref(
                snapshot.source_observation_id,
                BROWSERGYM_TASK_STATE_EVIDENCE_KEY,
            ),
        )
        if status in {BrowserGymTaskStatus.SUCCESS, BrowserGymTaskStatus.TERMINAL_FAILURE}
        else ()
    )
    return BrowserGymTaskAssessment(
        snapshot.task_run_id,
        snapshot.observation_id,
        snapshot.source_observation_id,
        snapshot.source,
        status,
        reason,
        refs,
    )

"""Run-scoped containment for mechanically verified repeated selections."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from affordance_runtime.evaluation.contracts import (
    ActionEvaluation,
    ActionEvaluationStatus,
    CriterionEvaluationStatus,
    TaskEvaluation,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import (
    AdmittedActionSelection,
    CoverageState,
    WorldObservation,
)
from affordance_runtime.world.source_profile import ObservationAssurance, assurance_satisfies

if TYPE_CHECKING:
    from affordance_runtime.agent.control_outcome import LoopDirective
    from affordance_runtime.agent.session import AgentRunSession


class SelectionProgressDisposition(StrEnum):
    EXECUTE = "execute"
    ALREADY_SATISFIED = "already_satisfied"
    TERMINATE_NO_PROGRESS = "terminate_no_progress"


@dataclass(frozen=True)
class SemanticAttemptKey:
    semantic_action: str
    semantic_target_id: str
    semantic_destination_id: str
    canonical_parameter_digest: str

    @classmethod
    def from_selection(cls, selection: AdmittedActionSelection) -> SemanticAttemptKey:
        encoded = json.dumps(
            to_json_compatible(selection.parameters),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return cls(
            selection.semantic_action,
            selection.target_id,
            selection.destination_id,
            f"sha256:{hashlib.sha256(encoded).hexdigest()}",
        )

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            (
                self.semantic_action,
                self.semantic_target_id,
                self.semantic_destination_id,
                self.canonical_parameter_digest,
            ),
            separators=(",", ":"),
        ).encode()
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


@dataclass(frozen=True)
class ProgressEvent:
    event_type: str
    semantic_action: str
    target_id: str
    attempt_key_digest: str
    effect_status: str
    task_status: str
    strategy_transition_required: bool


@dataclass(frozen=True)
class SelectionProgressResult:
    disposition: SelectionProgressDisposition
    event: ProgressEvent | None = None
    terminal_result: LoopDirective | None = None


@dataclass
class ProgressController:
    """Contain exact semantic repeats without retaining selected parameter values."""

    latest_attempt_key: SemanticAttemptKey | None = None
    latest_progress_fingerprint: str = ""
    same_attempt_streak: int = 0
    no_progress_count: int = 0
    def assess(
        self,
        selection: AdmittedActionSelection,
        observation: WorldObservation,
        evaluation: TaskEvaluation,
    ) -> SelectionProgressResult:
        key = SemanticAttemptKey.from_selection(selection)
        fingerprint = _progress_fingerprint(selection, observation, evaluation)
        if not _postcondition_is_satisfied(selection, observation):
            if key != self.latest_attempt_key:
                self.reset()
            return SelectionProgressResult(SelectionProgressDisposition.EXECUTE)
        repeated = key == self.latest_attempt_key and fingerprint == self.latest_progress_fingerprint
        if repeated:
            self.same_attempt_streak += 1
            self.no_progress_count += 1
        else:
            self.latest_attempt_key = key
            self.latest_progress_fingerprint = fingerprint
            self.same_attempt_streak = 1
            self.no_progress_count = 1
        event = _already_satisfied_event(key, selection, evaluation)
        disposition = (
            SelectionProgressDisposition.TERMINATE_NO_PROGRESS
            if repeated
            else SelectionProgressDisposition.ALREADY_SATISFIED
        )
        return SelectionProgressResult(disposition, event)

    def record_action_outcome(
        self,
        selection: AdmittedActionSelection,
        status: ActionEvaluationStatus,
        observation: WorldObservation,
        evaluation: TaskEvaluation,
    ) -> ProgressEvent | None:
        key = SemanticAttemptKey.from_selection(selection)
        if status == ActionEvaluationStatus.EFFECT_CONFIRMED:
            self.reset()
            return _outcome_event(key, selection, evaluation, status, False)
        if status == ActionEvaluationStatus.NO_EFFECT_CONFIRMED or (
            status == ActionEvaluationStatus.UNKNOWN
            and _postcondition_is_satisfied(selection, observation)
        ):
            self.latest_attempt_key = key
            self.latest_progress_fingerprint = _progress_fingerprint(
                selection, observation, evaluation
            )
            self.same_attempt_streak = 1
            self.no_progress_count += 1
            return _outcome_event(key, selection, evaluation, status, True)
        return None

    def reset(self) -> None:
        self.latest_attempt_key = None
        self.latest_progress_fingerprint = ""
        self.same_attempt_streak = 0
        self.no_progress_count = 0


def apply_selection_progress(
    session: AgentRunSession,
    selection: AdmittedActionSelection,
) -> SelectionProgressResult:
    """Apply zero-call containment after admission and before binding."""

    from affordance_runtime.agent.control_outcome import Terminate
    from affordance_runtime.agent.result_code import AgentFailureCode
    from affordance_runtime.agent.state import AgentLoopStatus

    evaluation = session.state.current_task_evaluation
    if evaluation is None:
        terminal = Terminate(
            AgentLoopStatus.FAILED, "task_evaluation_unavailable",
            "validated task evaluation is unavailable",
        )
        return SelectionProgressResult(SelectionProgressDisposition.TERMINATE_NO_PROGRESS, terminal_result=terminal)
    progress = session.progress_controller.assess(
        selection,
        session.state.current_observation,
        evaluation,
    )
    if progress.disposition == SelectionProgressDisposition.EXECUTE:
        return progress
    assert progress.event is not None
    session.state._append_progress_event(progress.event)
    if progress.disposition == SelectionProgressDisposition.ALREADY_SATISFIED:
        from affordance_runtime.agent.control_outcome import Continue

        return SelectionProgressResult(
            progress.disposition,
            progress.event,
            Continue("already_satisfied"),
        )
    terminal = Terminate(
        AgentLoopStatus.FAILED,
        "no_progress_repetition",
        "same semantic selection repeated without verified progress",
        failure_code=AgentFailureCode.NO_PROGRESS_REPETITION,
    )
    return SelectionProgressResult(progress.disposition, progress.event, terminal)


def record_execution_progress(
    session: AgentRunSession,
    selection: AdmittedActionSelection,
    action_evaluation: ActionEvaluation,
    observation: WorldObservation,
    evaluation: TaskEvaluation,
) -> ProgressEvent | None:
    event = session.progress_controller.record_action_outcome(
        selection,
        action_evaluation.status,
        observation,
        evaluation,
    )
    if event is not None:
        session.state._append_progress_event(event)
    return event

def _postcondition_is_satisfied(
    selection: AdmittedActionSelection,
    observation: WorldObservation,
) -> bool:
    if selection.semantic_action not in {"fill", "select"}:
        return False
    requested = selection.parameters.get("value")
    if not isinstance(requested, str):
        return False
    target = next((item for item in observation.targets if item.target_id == selection.target_id), None)
    if target is None or target.state.get("value") != requested:
        return False
    if any(
        item.subject_id == selection.target_id and item.predicate in {"value", "selected"}
        for item in observation.conflicts
    ):
        return False
    facts = tuple(
        item
        for item in observation.facts
        if item.subject_id == selection.target_id
        and item.predicate in {"value", "selected"}
        and item.value == requested
    )
    return bool(facts) and any(_fact_has_complete_structural_source(item.source_id, observation) for item in facts)


def _fact_has_complete_structural_source(source_id: str, observation: WorldObservation) -> bool:
    source = next(
        (item for item in observation.sources if source_id in {item.observation_id, item.surface}),
        None,
    )
    return bool(
        source
        and source.coverage == CoverageState.COMPLETE
        and observation.coverage.get(source.surface) == CoverageState.COMPLETE
        and assurance_satisfies(source.source_profile.assurance, ObservationAssurance.STRUCTURAL)
    )


def _progress_fingerprint(
    selection: AdmittedActionSelection,
    observation: WorldObservation,
    evaluation: TaskEvaluation,
) -> str:
    target = next((item for item in observation.targets if item.target_id == selection.target_id), None)
    public_value = target.state.get("value") if target else None
    value_digest = hashlib.sha256(
        json.dumps(to_json_compatible(public_value), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    satisfied = sorted(
        item.criterion_id
        for item in evaluation.criteria
        if item.status == CriterionEvaluationStatus.SATISFIED
    )
    outputs = sorted((item.output_id, tuple(sorted(item.evidence_refs))) for item in evaluation.outputs)
    payload = (
        str(evaluation.status),
        satisfied,
        sorted(evaluation.completion_evidence_refs),
        outputs,
        selection.target_id,
        "value",
        value_digest,
    )
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _already_satisfied_event(
    key: SemanticAttemptKey,
    selection: AdmittedActionSelection,
    evaluation: TaskEvaluation,
) -> ProgressEvent:
    return ProgressEvent(
        "already_satisfied_selection",
        selection.semantic_action,
        selection.target_id,
        key.digest,
        "already_satisfied",
        str(evaluation.status),
        True,
    )


def _outcome_event(
    key: SemanticAttemptKey,
    selection: AdmittedActionSelection,
    evaluation: TaskEvaluation,
    status: ActionEvaluationStatus,
    transition_required: bool,
) -> ProgressEvent:
    return ProgressEvent(
        "action_effect_evaluated",
        selection.semantic_action,
        selection.target_id,
        key.digest,
        str(status),
        str(evaluation.status),
        transition_required,
    )

import pytest

from affordance_runtime.evaluation import (
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
    TaskOutcomeFact,
    TaskOutcomeKind,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.validation import validate_task_evaluation
from tests.support.agent.core_loop_support import _task, _world


def _evaluation(status=TaskEvaluationStatus.COMPLETE, **changes) -> TaskEvaluation:
    values = dict(
        task_id="enable-shared",
        observation_id="after",
        status=status,
        reason="proposal",
        criteria=(
            CriterionEvaluation(
                "criterion:enabled",
                CriterionEvaluationStatus.SATISFIED,
                ("fact:after:enabled",),
                "enabled is true",
            ),
        ),
        completion_evidence_refs=("fact:after:enabled",),
    )
    values.update(changes)
    return TaskEvaluation(**values)


def _criterion_task():
    return _task().__class__(
        "enable-shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        success_criteria=({"id": "criterion:enabled", "target_id": "shared-toggle", "enabled": True},),
        risk_profile=_task().risk_profile,
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"task_id": "wrong"}, "task identity"),
        ({"observation_id": "wrong"}, "observation identity"),
        (
            {
                "criteria": (
                    CriterionEvaluation(
                        "criterion:invented",
                        CriterionEvaluationStatus.SATISFIED,
                        ("fact:after:enabled",),
                        "invented",
                    ),
                )
            },
            "criterion",
        ),
        ({"completion_evidence_refs": ("fact:invented",)}, "evidence"),
        ({"criteria": ()}, "criteria"),
    ),
)
def test_task_evaluation_validator_rejects_untrusted_complete(changes, message) -> None:
    observation = _world("after", True)
    with pytest.raises(ValueError, match=message):
        validate_task_evaluation(
            _evaluation(**changes),
            _criterion_task(),
            observation,
            WorldEvidenceIndex.from_observation(observation),
        )


def test_incomplete_cannot_claim_every_required_criterion_satisfied() -> None:
    observation = _world("after", True)
    with pytest.raises(ValueError, match="INCOMPLETE"):
        validate_task_evaluation(
            _evaluation(TaskEvaluationStatus.INCOMPLETE),
            _criterion_task(),
            observation,
            WorldEvidenceIndex.from_observation(observation),
        )


@pytest.mark.parametrize(
    ("kind", "status"),
    (
        (TaskOutcomeKind.TERMINAL_SUCCESS, TaskEvaluationStatus.INCOMPLETE),
        (TaskOutcomeKind.RUNNING_INCOMPLETE, TaskEvaluationStatus.UNKNOWN),
        (TaskOutcomeKind.TERMINAL_FAILURE, TaskEvaluationStatus.COMPLETE),
        (TaskOutcomeKind.VERIFIER_UNAVAILABLE, TaskEvaluationStatus.BLOCKED),
    ),
)
def test_task_outcome_status_matrix_rejects_every_cross_kind(kind, status) -> None:
    refs = (
        ("fact:after:enabled",)
        if kind
        in {
            TaskOutcomeKind.TERMINAL_SUCCESS,
            TaskOutcomeKind.TERMINAL_FAILURE,
        }
        else ()
    )
    with pytest.raises(ValueError, match="contradicts"):
        TaskEvaluation(
            "enable-shared",
            "after",
            status,
            "invalid matrix",
            completion_evidence_refs=refs if status is TaskEvaluationStatus.COMPLETE else (),
            outcome=TaskOutcomeFact(kind, "typed_outcome", refs),
        )


def test_task_outcome_evidence_must_resolve_in_current_observation() -> None:
    observation = _world("after", True)
    evaluation = TaskEvaluation(
        "enable-shared",
        "after",
        TaskEvaluationStatus.BLOCKED,
        "terminal task failure",
        outcome=TaskOutcomeFact(
            TaskOutcomeKind.TERMINAL_FAILURE,
            "verified_terminal_task_failure",
            ("fact:stale:status",),
        ),
    )
    with pytest.raises(ValueError, match="task outcome evidence"):
        validate_task_evaluation(
            evaluation,
            _criterion_task(),
            observation,
            WorldEvidenceIndex.from_observation(observation),
        )

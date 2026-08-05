from types import SimpleNamespace

from affordance_runtime.progress_phase import (
    ActionEffectEvaluationStatus,
    ActiveStepEvaluationStatus,
    PostActionEvaluation,
    ProgressStage,
    TaskCompletionEvaluationStatus,
)
from affordance_runtime.stage_protocol import RuntimeEventBuffer
from affordance_runtime.verification.mechanical import VerificationEvidence, VerificationReport, VerificationStatus


def test_post_action_evaluation_is_typed_and_projects_one_canonical_event() -> None:
    events = RuntimeEventBuffer()
    report = VerificationReport(
        VerificationStatus.PASSED,
        evidence=[
            VerificationEvidence(
                verifier_kind="control_state",
                target="generic-control",
                passed=True,
                source="post_action_observation",
                evidence_id="evidence:generic-control",
                criterion_ids=("criterion:active",),
                requirement_ids=("requirement:active",),
            )
        ],
    )

    evaluation = ProgressStage._record_post_action_evaluation(
        events,
        SimpleNamespace(phase="verifying"),
        report,
        contract_id="contract:generic",
        active_step_status=ActiveStepEvaluationStatus.COMPLETED,
        task_completion_status=TaskCompletionEvaluationStatus.NOT_EVALUATED,
        progress_committed=True,
        liveness_decision="advance_step",
    )

    assert evaluation == PostActionEvaluation(
        contract_id="contract:generic",
        action_effect=ActionEffectEvaluationStatus.PASSED,
        active_step=ActiveStepEvaluationStatus.COMPLETED,
        task_completion=TaskCompletionEvaluationStatus.NOT_EVALUATED,
        criterion_ids=("criterion:active",),
        requirement_ids=("requirement:active",),
        evidence_refs=("evidence:generic-control",),
        progress_committed=True,
        liveness_decision="advance_step",
    )
    assert events.events[0].kind == "PostActionEvaluated"
    assert events.events[0].payload["active_step_status"] == "completed"

from __future__ import annotations

import hashlib
import json

import pytest

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.canonical_observation_builder import CanonicalObservationBuilder
from affordance_runtime.contracts import (
    ExecutionReceipt,
    Observation,
    ProgressEvidenceScope,
    VerifierSpec,
)
from affordance_runtime.criteria import (
    PredicateExpr,
    PredicateOperator,
    SubjectExpr,
)
from affordance_runtime.grounding import GroundingSource
from affordance_runtime.output_materialization import OutputMaterializer
from affordance_runtime.perception_session import PerceptionCapture
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.runtime_committer import RuntimeCommitter
from affordance_runtime.simplified_runtime_contracts import ElementIntent, SourceReference, StepSpec
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    OperationClass,
    TaskRequirement,
    TaskSemanticPayload,
    TaskSpec,
)
from affordance_runtime.task_plan_contracts import (
    InitialTaskPlanRequest,
    PlanProposal,
    TaskPlanAuthority,
    TaskPlanDecisionStatus,
    TaskPlanGeneratorSource,
    TaskRequirementProjection,
)
from affordance_runtime.trace import TraceDag
from affordance_runtime.verification.contracts import (
    CriterionEvaluation,
    CriterionPolicy,
    CriterionStatus,
    OutputMaterialization,
    OutputSpec,
    PredicateEvidenceContext,
    SuccessExpression,
    TaskCompletionEvaluation,
    criterion_policy_digest,
)
from affordance_runtime.verification.mechanical import VerifierLadder
from affordance_runtime.verification.task_completion import TaskCompletionEvaluator
from affordance_runtime.verification_report_adapter import admit_completion_evidence


def test_candidate_presence_never_synthesizes_complete_coverage() -> None:
    observation = Observation(
        environment_revision="env-1",
        snapshot_id="epoch-1",
        page_revision="page-1",
    )

    class _Model:
        affordances = ()

    capture = PerceptionCapture.from_browser_snapshot(BrowserSnapshot(observation, _Model()))
    assert capture.source_coverage
    assert all(item.completeness.value == "unknown" for item in capture.source_coverage)


def test_output_policy_refs_are_closed_and_completion_trace_redacts_values() -> None:
    with pytest.raises(ValueError, match="redaction_policy_ref"):
        OutputSpec(
            output_id="record",
            materialization_criterion_id="criterion:output",
            redaction_policy_ref="unregistered-policy",
        )

    state = StateKernel("task:privacy", "return private record")
    state.phase = RuntimeStep.VERIFYING.value
    trace = TraceDag("task:privacy")
    parent = trace.add("root", {})
    completion = TaskCompletionEvaluation(
        CriterionStatus.SATISFIED,
        "criterion:output",
        result_payload={"email": "alice@example.test"},
    )
    node = RuntimeCommitter.commit_task_completion(state, trace, parent, completion)
    assert state.final_result == {"email": "alice@example.test"}
    assert "alice@example.test" not in repr(node.payload)
    assert node.payload["result"]["redacted"] is True


def test_coverage_from_another_epoch_is_rejected() -> None:
    from affordance_runtime.unified_observation import SourceCoverage

    capture = PerceptionCapture(
        observation=Observation(
            environment_revision="env-1",
            snapshot_id="epoch-new",
            page_revision="page-1",
        ),
        source_coverage=(
            SourceCoverage.complete(
                GroundingSource.DOM,
                captured_item_count=0,
                acquisition_epoch_ref="epoch-old",
            ),
        ),
    )
    with pytest.raises(ValueError, match="different capture epoch"):
        CanonicalObservationBuilder().build(capture)


def _output_task() -> TaskSpec:
    policy = CriterionPolicy()
    return TaskSpec(
        task_id="task:output",
        revision=1,
        objective="return record",
        operation_class=OperationClass.READ_ONLY,
        requirements=(
            TaskRequirement(
                requirement_id="requirement:read",
                payload=TaskSemanticPayload(
                    kind="effect",
                    subject="record",
                    target_identity="record",
                    operation_class=OperationClass.READ_ONLY,
                ),
                source_anchor_refs=("request:output",),
            ),
            TaskRequirement(
                requirement_id="requirement:output",
                payload=TaskSemanticPayload(kind="output", subject="record"),
                source_anchor_refs=("request:output",),
            ),
        ),
        allowed_effect_refs=("requirement:read",),
        success=SuccessExpression(
            expression_id="success:read",
            operator="criterion",
            criterion_id="criterion:read",
            requirement_refs=("requirement:read",),
            policy=policy,
        ),
        required_outputs=(
            OutputSpec(
                output_id="record",
                requirement_ref="requirement:output",
                materialization_criterion_id="criterion:output",
            ),
        ),
        source_request_ref="request:output",
    )


def test_output_metadata_is_not_a_result_but_actual_materialization_is() -> None:
    task = _output_task()
    read = CriterionEvaluation(
        "criterion:read",
        CriterionStatus.SATISFIED,
        evidence_refs=("evidence:read",),
        policy_digest=criterion_policy_digest("criterion:read", CriterionPolicy()),
    )
    output = CriterionEvaluation(
        "criterion:output",
        CriterionStatus.SATISFIED,
        observed_value={"id": "record:1"},
        evidence_refs=("evidence:record:1",),
        source_binding_refs=("source:record:1",),
    )
    declaration = {"record": {"output_id": "record", "materialization_criterion_id": "criterion:output"}}
    denied = TaskCompletionEvaluator().evaluate(
        task_spec=task,
        criterion_results=(read, output),
        result_payload=declaration,
    )
    assert not denied.completed

    materialized = OutputMaterializer().from_evaluation(
        task_spec=task,
        output_spec=task.required_outputs[0],
        evaluation=output,
        observation_ref="epoch-1",
    )
    assert materialized is not None
    allowed = TaskCompletionEvaluator().evaluate(
        task_spec=task,
        criterion_results=(read, output),
        result_payload=declaration,
        output_materializations=(materialized,),
    )
    assert allowed.completed
    assert allowed.result_payload["record"] == {"id": "record:1"}
    assert materialized.schema_digest.startswith("sha256:")
    assert materialized.content_digest.startswith("sha256:")


def _artifact_completion(task: TaskSpec, artifact_ref: str, content_digest: str):
    read = CriterionEvaluation(
        "criterion:read",
        CriterionStatus.SATISFIED,
        evidence_refs=("evidence:read",),
        policy_digest=criterion_policy_digest("criterion:read", CriterionPolicy()),
    )
    output = CriterionEvaluation(
        "criterion:output",
        CriterionStatus.SATISFIED,
        observed_value={"artifact_ref": artifact_ref},
        evidence_refs=("evidence:artifact",),
        source_binding_refs=("source:artifact",),
    )
    schema_payload = json.dumps(
        {"schema_id": task.required_outputs[0].schema_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    materialization = OutputMaterialization(
        output_id="record",
        materialization_criterion_id="criterion:output",
        schema_digest=f"sha256:{hashlib.sha256(schema_payload).hexdigest()}",
        content_digest=content_digest,
        task_id=task.task_id,
        task_revision=task.revision,
        observation_ref="epoch-1",
        source_refs=("evidence:artifact",),
        source_binding_refs=("source:artifact",),
        artifact_ref=artifact_ref,
    )
    return TaskCompletionEvaluator().evaluate(
        task_spec=task,
        criterion_results=(read, output),
        result_payload={},
        output_source_bindings={"record": ("source:artifact",)},
        output_materializations=(materialization,),
    )


@pytest.mark.parametrize(
    ("case", "reason"),
    (
        ("missing", "required_output_artifact_missing"),
        ("digest_mismatch", "output_artifact_content_mismatch"),
    ),
)
def test_required_artifact_must_exist_and_match_its_digest(tmp_path, case: str, reason: str) -> None:
    artifact = tmp_path / "record.json"
    expected_bytes = b'{"id":"record:1"}'
    if case == "digest_mismatch":
        artifact.write_bytes(b'{"id":"different"}')
    completion = _artifact_completion(
        _output_task(),
        str(artifact),
        f"sha256:{hashlib.sha256(expected_bytes).hexdigest()}",
    )

    assert not completion.completed
    assert completion.required_output_results[0].reason_code == reason
    assert "record" not in completion.result_payload


@pytest.mark.parametrize("digest_prefix", ("", "sha256:"))
def test_matching_required_artifact_can_complete(tmp_path, digest_prefix: str) -> None:
    artifact = tmp_path / "record.json"
    content = b'{"id":"record:1"}'
    artifact.write_bytes(content)

    completion = _artifact_completion(
        _output_task(),
        str(artifact),
        f"{digest_prefix}{hashlib.sha256(content).hexdigest()}",
    )

    assert completion.completed
    assert completion.result_payload["record"] == {"artifact_ref": str(artifact)}


def test_receipt_terminal_flag_alone_cannot_complete_a_task() -> None:
    task = TaskSpec(
        task_id="task:receipt-only",
        revision=1,
        objective="observe saved state",
        operation_class=OperationClass.READ_ONLY,
        requirements=(
            TaskRequirement(
                requirement_id="requirement:read",
                payload=TaskSemanticPayload(
                    kind="effect",
                    subject="saved state",
                    target_identity="saved state",
                    operation_class=OperationClass.READ_ONLY,
                ),
                source_anchor_refs=("request:receipt-only",),
            ),
        ),
        allowed_effect_refs=("requirement:read",),
        success=SuccessExpression(
            expression_id="success:receipt-only",
            operator="criterion",
            criterion_id="criterion:saved",
            requirement_refs=("requirement:read",),
        ),
        source_request_ref="request:receipt-only",
    )
    observation = Observation("env-1", snapshot_id="epoch-1", page_revision="page-1")
    report = VerifierLadder().verify_report(
        [
            VerifierSpec(
                "state_delta_or_terminal",
                "saved state",
                True,
                criterion_ids=("criterion:saved",),
                requirement_ids=("requirement:read",),
                progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
            )
        ],
        ExecutionReceipt(
            "contract:receipt-only",
            "test",
            True,
            "env-1",
            "env-1",
            1.0,
            evidence={"terminal_success": True},
        ),
        observation,
    )
    admitted = admit_completion_evidence(
        task_spec=task,
        observation=observation,
        evidence_context=PredicateEvidenceContext(observation.snapshot_id),
        report=report,
    )
    completion = TaskCompletionEvaluator().evaluate(
        task_spec=task,
        criterion_results=admitted,
        result_payload={},
    )

    assert report.passed
    assert report.evidence[0].source == "execution_receipt"
    assert report.evidence[0].strength == "weak"
    assert not completion.completed


def test_output_materializer_rejects_secret_bearing_values() -> None:
    task = _output_task()
    output = CriterionEvaluation(
        "criterion:output",
        CriterionStatus.SATISFIED,
        observed_value={"token": "secret-value"},
        evidence_refs=("evidence:record",),
    )

    with pytest.raises(ValueError, match="secret-bearing"):
        OutputMaterialization(
            output_id="record",
            materialization_criterion_id="criterion:output",
            schema_digest="sha256:schema",
            content_digest="sha256:forged",
            task_id=task.task_id,
            task_revision=task.revision,
            observation_ref="epoch-1",
            source_refs=("evidence:record",),
            value={"token": "secret-value"},
        )

    with pytest.raises(ValueError, match="content digest mismatch"):
        OutputMaterialization(
            output_id="record",
            materialization_criterion_id="criterion:output",
            schema_digest="sha256:schema",
            content_digest="sha256:forged",
            task_id=task.task_id,
            task_revision=task.revision,
            observation_ref="epoch-1",
            source_refs=("evidence:record",),
            value={"id": "record:1"},
        )
    assert (
        OutputMaterializer().from_evaluation(
            task_spec=task,
            output_spec=task.required_outputs[0],
            evaluation=output,
            observation_ref="epoch-1",
        )
        is None
    )


def test_read_requirement_id_cannot_launder_an_effectful_step() -> None:
    source = (SourceReference("request", "request:1"),)
    step = StepSpec(
        step_id="step:delete",
        objective="delete record",
        interaction=ElementIntent("record", source),
        completion_criteria=(
            PredicateExpr(
                "criterion:delete",
                SubjectExpr("target", "record"),
                PredicateOperator.CHANGED,
                CriterionPolicy(),
            ),
        ),
        source_refs=source,
        requirement_refs=("requirement:read",),
        effect_authorization_refs=("requirement:read",),
        effectful=True,
        operation_class=OperationClass.IRREVERSIBLE.value,
    )
    request = InitialTaskPlanRequest(
        task_spec_identity="task:read@1",
        task_revision=1,
        evaluated_at_state_version=0,
        objective="read record",
        observation_refs=("epoch-1",),
        remaining_budget_steps=1,
        allowed_requirement_ids=("requirement:read",),
        allowed_effect_ids=("requirement:read",),
        operation_class=OperationClass.READ_ONLY,
        requirement_projections=(
            TaskRequirementProjection(
                requirement_id="requirement:read",
                kind="effect",
                subject="record",
                target_identity="record",
                operation_class=OperationClass.READ_ONLY.value,
            ),
        ),
    )
    proposal = PlanProposal(
        task_spec_identity=request.task_spec_identity,
        task_revision=1,
        generated_by=TaskPlanGeneratorSource.LLM,
        generator_id="malicious-planner",
        steps=(step,),
        based_on_observation_ref="epoch-1",
        based_on_state_version=0,
        source_refs=source,
    )
    decision = TaskPlanAuthority().admit_initial(request, proposal)
    assert decision.status == TaskPlanDecisionStatus.REJECTED
    assert any(item.code == "semantic_operation_exceeds_requirement" for item in decision.issues)


def _plan_request(*, destination: str = "") -> InitialTaskPlanRequest:
    return InitialTaskPlanRequest(
        task_spec_identity="task:semantic@1",
        task_revision=1,
        evaluated_at_state_version=0,
        objective="apply one semantic action",
        observation_refs=("epoch-1",),
        remaining_budget_steps=1,
        allowed_requirement_ids=("requirement:effect",),
        allowed_effect_ids=("requirement:effect",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirement_projections=(
            TaskRequirementProjection(
                requirement_id="requirement:effect",
                kind="effect",
                subject="Alice" if destination else "Save",
                target_identity="Alice" if destination else "Save",
                destination_identity=destination,
                operation_class=OperationClass.REVERSIBLE_WRITE.value,
            ),
        ),
    )


def _element_plan(request: InitialTaskPlanRequest, target: str) -> PlanProposal:
    source = (SourceReference("request", "request:semantic"),)
    step = StepSpec(
        step_id="step:semantic",
        objective=request.objective,
        interaction=ElementIntent(target, source),
        completion_criteria=(
            PredicateExpr(
                "criterion:semantic",
                SubjectExpr("target", target),
                PredicateOperator.CHANGED,
                CriterionPolicy(),
            ),
        ),
        source_refs=source,
        requirement_refs=("requirement:effect",),
        effect_authorization_refs=("requirement:effect",),
        effectful=True,
    )
    return PlanProposal(
        task_spec_identity=request.task_spec_identity,
        task_revision=request.task_revision,
        generated_by=TaskPlanGeneratorSource.RULE,
        generator_id="minimal-semantic-test",
        steps=(step,),
        based_on_observation_ref=request.observation_refs[0],
        based_on_state_version=request.evaluated_at_state_version,
        source_refs=source,
    )


def test_plain_element_action_does_not_require_unrelated_semantic_fields() -> None:
    request = _plan_request()
    decision = TaskPlanAuthority().admit_initial(request, _element_plan(request, "Save"))

    assert decision.status == TaskPlanDecisionStatus.ACCEPTED


def test_relational_effect_requires_its_declared_destination() -> None:
    request = _plan_request(destination="Approved")
    decision = TaskPlanAuthority().admit_initial(request, _element_plan(request, "Alice"))

    assert decision.status == TaskPlanDecisionStatus.REJECTED
    assert any(item.code == "semantic_destination_missing" for item in decision.issues)

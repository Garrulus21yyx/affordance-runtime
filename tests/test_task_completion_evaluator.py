from __future__ import annotations

import hashlib
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from affordance_runtime.contracts import ExecutionReceipt, Observation
from affordance_runtime.execution_context import digest_payload
from affordance_runtime.output_materialization import OutputMaterializer
from affordance_runtime.progress_evaluation import ProgressEvaluationService
from affordance_runtime.runtime_evidence import (
    DurableEvidenceStore,
    RecentActionFact,
    RecentActionOutcomeEvidence,
    RecentActionOutcomeEvidenceIndex,
)
from affordance_runtime.task_intake import (
    OperationClass,
    TaskRequirement,
    TaskSemanticPayload,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.unified_observation import UnifiedObservation, UnifiedObservationTarget
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionEvaluation,
    CriterionPolicy,
    CriterionStatus,
    EvidenceSourceKind,
    EvidenceValidityMode,
    OutputMaterialization,
    OutputSpec,
    PredicateEvidenceContext,
    SatisfactionMode,
    SuccessExpression,
    TaskCompletionEvaluation,
    criterion_policy_digest,
)
from affordance_runtime.verification.mechanical import (
    VerificationEvidence,
    VerificationReport,
    VerificationStatus,
)
from affordance_runtime.verification.task_completion import TaskCompletionEvaluator
from affordance_runtime.verification_report_adapter import admit_completion_evidence


def _leaf(criterion_id: str) -> SuccessExpression:
    return SuccessExpression(
        expression_id=f"expr:{criterion_id}",
        operator="criterion",
        criterion_id=criterion_id,
        requirement_refs=("requirement:effect:1",),
    )


def _output_task() -> TaskSpec:
    return TaskSpec(
        task_id="task:output",
        revision=1,
        objective="return observed output",
        operation_class=OperationClass.READ_ONLY,
        requirements=(
            TaskRequirement(
                requirement_id="requirement:output",
                payload=TaskSemanticPayload(kind="output", subject="record"),
                source_anchor_refs=("request:output",),
            ),
        ),
        success=SuccessExpression(
            expression_id="success:output",
            operator="criterion",
            criterion_id="criterion:output",
            requirement_refs=("requirement:output",),
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


def _output_criterion() -> CriterionEvaluation:
    return CriterionEvaluation(
        "criterion:output",
        CriterionStatus.SATISFIED,
        evidence_refs=("resource:record:1",),
        source_binding_refs=("resource:record:1",),
    )


def _external_effect_leaf(criterion_id: str = "criterion:external") -> SuccessExpression:
    return SuccessExpression(
        expression_id=f"expr:{criterion_id}",
        operator="criterion",
        criterion_id=criterion_id,
        requirement_refs=("requirement:effect:1",),
        policy=CriterionPolicy(
            satisfaction=SatisfactionMode.ACTION_CAUSED,
            validity=EvidenceValidityMode.RECENT_ACTION,
            causal_lineage_required=True,
        ),
    )


def _final_recheck_leaf(criterion_id: str = "criterion:recheck") -> SuccessExpression:
    return SuccessExpression(
        expression_id=f"expr:{criterion_id}",
        operator="criterion",
        criterion_id=criterion_id,
        requirement_refs=("requirement:effect:1",),
        policy=CriterionPolicy(
            validity=EvidenceValidityMode.FINAL_RECHECK,
            minimum_assurance=AssuranceLevel.AUTHORITATIVE,
        ),
    )


def _bind_success_evaluations(
    task: TaskSpec,
    evaluations: tuple[CriterionEvaluation, ...],
) -> tuple[CriterionEvaluation, ...]:
    policies = {child.criterion_id: child.policy for child in task.success.children if child.operator == "criterion"}
    if task.success.operator == "criterion":
        policies[task.success.criterion_id] = task.success.policy
    return tuple(
        replace(
            evaluation,
            policy_digest=criterion_policy_digest(evaluation.criterion_id, policies[evaluation.criterion_id]),
        )
        if evaluation.criterion_id in policies and policies[evaluation.criterion_id] is not None
        else evaluation
        for evaluation in evaluations
    )


def test_typed_completion_contracts_are_immutable_and_task_bound() -> None:
    success = SuccessExpression(
        expression_id="success:root",
        operator="all_of",
        children=(_leaf("criterion:saved"), _leaf("criterion:dialog-absent")),
    )
    task = TaskSpec(
        task_id="task:save",
        revision=1,
        objective="save settings",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=(
            *canonical_effect_requirements(("settings",), OperationClass.REVERSIBLE_WRITE, "request:save", ()),
            TaskRequirement(
                requirement_id="requirement:output:1",
                payload=TaskSemanticPayload(kind="output", subject="saved_record"),
                source_anchor_refs=("request:save",),
            ),
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("settings",)),
        success=success,
        required_outputs=(
            OutputSpec(
                output_id="saved_record",
                requirement_ref="requirement:output:1",
                materialization_criterion_id="criterion:output",
                source_binding_requirement=("source:any",),
            ),
        ),
        source_request_ref="request:save",
    )
    evaluation = TaskCompletionEvaluation(
        status=CriterionStatus.SATISFIED,
        root_criterion_id=task.success.expression_id,
        criterion_results=(CriterionEvaluation("criterion:saved", CriterionStatus.SATISFIED),),
        result_payload={"saved_record": {"id": "record:1"}},
    )

    assert task.success == success
    assert evaluation.result_payload == {"saved_record": {"id": "record:1"}}
    with pytest.raises((AttributeError, TypeError)):
        evaluation.result_payload["saved_record"] = {}  # type: ignore[index]


@pytest.mark.parametrize(
    "value",
    (
        "Bearer TOPSECRET",
        "https://example.test/export?X-Amz-Signature=secret",
    ),
)
def test_output_materializer_rejects_secret_bearing_values(value: str) -> None:
    task = _output_task()
    materialized = OutputMaterializer().from_evaluation(
        task_spec=task,
        output_spec=task.required_outputs[0],
        evaluation=CriterionEvaluation(
            "criterion:output",
            CriterionStatus.SATISFIED,
            observed_value=value,
            evidence_refs=("evidence:observed",),
            source_binding_refs=("source:record",),
        ),
        observation_ref="observation:1",
    )
    assert materialized is None


def test_artifact_materializer_binds_download_receipt_to_authoritative_final_evidence(
    tmp_path,
) -> None:
    artifact = tmp_path / "report.csv"
    artifact.write_bytes(b"name,value\nalpha,1\n")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    task = _output_task()
    output = task.required_outputs[0].model_copy(update={"schema_id": "artifact:file@v1"})
    criterion = CriterionEvaluation(
        "criterion:output",
        CriterionStatus.SATISFIED,
        observed_value={"effect": "report.export", "sha256": digest},
        evidence_refs=("evidence:api-final",),
        source_binding_refs=("api:report-export",),
        authoritative_final_recheck=True,
    )
    receipt = ExecutionReceipt(
        contract_id="contract:export",
        backend="dom",
        success=True,
        started_revision="revision:1",
        ended_revision="revision:2",
        latency_ms=1.0,
        evidence={"path": str(artifact), "sha256": digest},
    )

    materialized = OutputMaterializer().from_artifact_receipt(
        task_spec=task,
        output_spec=output,
        evaluation=criterion,
        receipt=receipt,
        observation_ref="observation:final",
        contract_id="contract:export",
    )

    assert materialized is not None
    assert materialized.artifact_ref == str(artifact)
    assert materialized.content_digest == f"sha256:{digest}"

    artifact.write_bytes(b"tampered")
    assert (
        OutputMaterializer().from_artifact_receipt(
            task_spec=task,
            output_spec=output,
            evaluation=criterion,
            receipt=receipt,
            observation_ref="observation:final",
            contract_id="contract:export",
        )
        is None
    )


def test_output_materialization_cannot_forge_criterion_or_owner_lineage() -> None:
    task = _output_task()
    criterion = CriterionEvaluation(
        "criterion:output",
        CriterionStatus.SATISFIED,
        observed_value={"id": "record:1"},
        evidence_refs=("evidence:real",),
        source_binding_refs=("source:real",),
    )
    honest = OutputMaterializer().from_evaluation(
        task_spec=task,
        output_spec=task.required_outputs[0],
        evaluation=criterion,
        observation_ref="observation:1",
    )
    assert honest is not None
    forged = replace(
        honest,
        source_refs=("evidence:forged",),
        source_binding_refs=("source:forged",),
    )
    result = TaskCompletionEvaluator().evaluate(
        task_spec=task,
        criterion_results=_bind_success_evaluations(task, (criterion,)),
        result_payload={"record": {"id": "record:1"}},
        output_source_bindings={"record": ("source:real",)},
        output_materializations=(forged,),
    )
    assert result.status == CriterionStatus.UNSATISFIED
    assert result.required_output_results[0].reason_code == "output_materialization_source_lineage_mismatch"


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: SuccessExpression(expression_id="root", operator="criterion"), "criterion_id"),
        (
            lambda: SuccessExpression(
                expression_id="root",
                operator="not",
                children=(_leaf("one"), _leaf("two")),
            ),
            "exactly one",
        ),
    ],
)
def test_success_expression_rejects_incomplete_shapes(build: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build()  # type: ignore[operator]


@pytest.mark.parametrize(
    ("case", "criterion_results", "result_payload", "source_bindings", "uncertain", "expected"),
    [
        (
            "complete closure",
            (
                CriterionEvaluation("criterion:saved", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:dialog-absent", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:constraint", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:external", CriterionStatus.SATISFIED),
                CriterionEvaluation(
                    "criterion:recheck",
                    CriterionStatus.SATISFIED,
                    authoritative_final_recheck=True,
                ),
                _output_criterion(),
            ),
            {"saved_record": {"id": "record:1"}},
            {"saved_record": ("resource:record:1",)},
            (),
            CriterionStatus.SATISFIED,
        ),
        (
            "receipt report plan and prose are not criteria",
            (),
            {
                "receipt_success": True,
                "latest_report_passed": True,
                "plan_exhausted": True,
                "planner_summary": "done",
                "saved_record": {"id": "record:1"},
            },
            {"saved_record": ("resource:record:1",)},
            (),
            CriterionStatus.UNSATISFIED,
        ),
        (
            "constraint violation",
            (
                CriterionEvaluation("criterion:saved", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:dialog-absent", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:constraint", CriterionStatus.UNSATISFIED),
            ),
            {},
            {},
            (),
            CriterionStatus.UNSATISFIED,
        ),
        (
            "external effect remains uncertain",
            (
                CriterionEvaluation("criterion:saved", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:dialog-absent", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:constraint", CriterionStatus.SATISFIED),
                _output_criterion(),
            ),
            {"saved_record": {"id": "record:1"}},
            {"saved_record": ("resource:record:1",)},
            ("effect:send",),
            CriterionStatus.UNKNOWN,
        ),
        (
            "final recheck is not authoritative",
            (
                CriterionEvaluation("criterion:saved", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:dialog-absent", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:constraint", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:external", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:recheck", CriterionStatus.SATISFIED),
                _output_criterion(),
            ),
            {"saved_record": {"id": "record:1"}},
            {"saved_record": ("resource:record:1",)},
            (),
            CriterionStatus.UNKNOWN,
        ),
        (
            "required output lacks source binding",
            (
                CriterionEvaluation("criterion:saved", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:dialog-absent", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:constraint", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:external", CriterionStatus.SATISFIED),
                CriterionEvaluation(
                    "criterion:recheck",
                    CriterionStatus.SATISFIED,
                    authoritative_final_recheck=True,
                ),
                _output_criterion(),
            ),
            {"saved_record": {"id": "record:1"}},
            {},
            (),
            CriterionStatus.UNSATISFIED,
        ),
    ],
)
def test_task_completion_requires_full_typed_closure(
    case: str,
    criterion_results: tuple[CriterionEvaluation, ...],
    result_payload: dict[str, object],
    source_bindings: dict[str, tuple[str, ...]],
    uncertain: tuple[str, ...],
    expected: CriterionStatus,
) -> None:
    del case
    task = TaskSpec(
        task_id="task:save",
        revision=1,
        objective="save settings",
        operation_class=OperationClass.EXTERNAL_SIDE_EFFECT,
        requirements=(
            *canonical_effect_requirements(("settings",), OperationClass.EXTERNAL_SIDE_EFFECT, "request:save", ()),
            TaskRequirement(
                requirement_id="requirement:output:1",
                payload=TaskSemanticPayload(kind="output", subject="saved_record"),
                source_anchor_refs=("request:save",),
            ),
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("settings",)),
        success=SuccessExpression(
            expression_id="success:root",
            operator="all_of",
            children=(
                _leaf("criterion:saved"),
                _leaf("criterion:dialog-absent"),
                _external_effect_leaf(),
                _final_recheck_leaf(),
            ),
        ),
        constraint_criterion_ids=("criterion:constraint",),
        external_effect_criterion_ids=("criterion:external",),
        final_recheck_criterion_ids=("criterion:recheck",),
        required_outputs=(
            OutputSpec(
                output_id="saved_record",
                requirement_ref="requirement:output:1",
                materialization_criterion_id="criterion:output",
            ),
        ),
        source_request_ref="request:save",
    )

    evaluation = TaskCompletionEvaluator().evaluate(
        task_spec=task,
        criterion_results=_bind_success_evaluations(task, criterion_results),
        result_payload=result_payload,
        output_source_bindings=source_bindings,
        output_materializations=(
            (
                OutputMaterialization(
                    output_id="saved_record",
                    materialization_criterion_id="criterion:output",
                    schema_digest="sha256:a2b4b10733fb28fb92a7b5b79abdf4de51559597143c2f24dd217558201505e6",
                    content_digest=digest_payload(result_payload["saved_record"]),
                    task_id=task.task_id,
                    task_revision=task.revision,
                    observation_ref="observation:test",
                    source_refs=source_bindings["saved_record"],
                    source_binding_refs=source_bindings["saved_record"],
                    value=result_payload["saved_record"],
                )
            ,)
            if result_payload.get("saved_record") is not None
            and source_bindings.get("saved_record")
            and any(
                item.criterion_id == "criterion:output" and item.status == CriterionStatus.SATISFIED
                for item in criterion_results
            )
            else ()
        ),
        uncertain_external_effects=uncertain,
    )

    assert evaluation.status == expected
    assert evaluation.completed is (expected == CriterionStatus.SATISFIED)


@pytest.mark.parametrize(
    "operation_class",
    (OperationClass.EXTERNAL_SIDE_EFFECT, OperationClass.IRREVERSIBLE),
)
def test_high_risk_taskspec_requires_declared_effect_and_authoritative_recheck(
    operation_class: OperationClass,
) -> None:
    with pytest.raises(ValidationError, match="requires external-effect criteria"):
        TaskSpec(
            task_id="task:high-risk",
            revision=1,
            objective="perform external effect",
            operation_class=operation_class,
            requirements=canonical_effect_requirements(("external-system",), operation_class, "request:high-risk", ()),
            allowed_effect_refs=canonical_effect_requirement_refs(("external-system",)),
            success=_leaf("criterion:effect-observed"),
            source_request_ref="request:high-risk",
        )


@pytest.mark.parametrize(
    "policy",
    (
        CriterionPolicy(
            satisfaction=SatisfactionMode.ACTION_CAUSED,
            causal_lineage_required=True,
        ),
        CriterionPolicy(
            validity=EvidenceValidityMode.FINAL_RECHECK,
            minimum_assurance=AssuranceLevel.AUTHORITATIVE,
        ),
        CriterionPolicy(minimum_assurance=AssuranceLevel.AUTHORITATIVE),
    ),
)
def test_success_policy_rejects_unbound_satisfied_observation(policy: CriterionPolicy) -> None:
    task = TaskSpec(
        task_id="task:policy-bound",
        revision=1,
        objective="perform policy-bound effect",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(
            ("settings",), OperationClass.REVERSIBLE_WRITE, "request:policy", ()
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("settings",)),
        success=SuccessExpression(
            expression_id="success:policy-bound",
            operator="criterion",
            criterion_id="criterion:policy-bound",
            requirement_refs=("requirement:effect:1",),
            policy=policy,
        ),
        source_request_ref="request:policy",
    )
    observation = Observation(
        "revision:1",
        snapshot_id="snapshot:1",
        metadata={
            "criterion_evaluations": {
                "criterion:policy-bound": {
                    "status": "satisfied",
                    "evidence_refs": ["evidence:unbound"],
                    "source_kind": "dom_state",
                    "assurance": "structural",
                }
            }
        },
    )

    admitted = admit_completion_evidence(
        task_spec=task,
        observation=observation,
        evidence_context=PredicateEvidenceContext(current_observation_ref=observation.snapshot_id),
    )
    evaluation = TaskCompletionEvaluator().evaluate(
        task_spec=task,
        criterion_results=admitted,
        result_payload={},
    )

    assert evaluation.status == CriterionStatus.UNKNOWN


def test_same_id_satisfied_result_without_policy_binding_is_unknown() -> None:
    task = TaskSpec(
        task_id="task:unbound-result",
        revision=1,
        objective="save",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(
            ("settings",), OperationClass.REVERSIBLE_WRITE, "request:unbound", ()
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("settings",)),
        success=_leaf("criterion:saved"),
        source_request_ref="request:unbound",
    )

    evaluation = TaskCompletionEvaluator().evaluate(
        task_spec=task,
        criterion_results=(CriterionEvaluation("criterion:saved", CriterionStatus.SATISFIED),),
        result_payload={},
    )

    assert evaluation.status == CriterionStatus.UNKNOWN


def test_untrusted_observation_metadata_cannot_create_or_carry_completion_evidence() -> None:
    criterion_id = "criterion:current-only"
    task = TaskSpec(
        task_id="task:current-only",
        revision=1,
        objective="observe the current state",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(("state",), OperationClass.READ_ONLY, "request:current-only", ()),
        allowed_effect_refs=canonical_effect_requirement_refs(("state",)),
        success=SuccessExpression(
            expression_id="success:current-only",
            operator="criterion",
            criterion_id=criterion_id,
            requirement_refs=("requirement:effect:1",),
            policy=CriterionPolicy(validity=EvidenceValidityMode.CURRENT_OBSERVATION),
        ),
        source_request_ref="request:current-only",
    )
    state = SimpleNamespace(
        current_contract=None,
        task_progress=SimpleNamespace(
            recent_action_outcomes=RecentActionOutcomeEvidenceIndex(),
            durable_evidence=DurableEvidenceStore(),
        ),
        uncertain_external_effects=(),
    )
    first = Observation(
        "revision:1",
        snapshot_id="snapshot:1",
        metadata={
            "criterion_evaluations": {
                criterion_id: {
                    "status": "satisfied",
                    "evidence_refs": ["evidence:1"],
                    "source_kind": "dom_state",
                    "assurance": "structural",
                }
            }
        },
    )
    second = Observation("revision:2", snapshot_id="snapshot:2")

    epoch1 = ProgressEvaluationService().evaluate_task_completion(
        task_spec=task,
        state=state,
        observation=first,
        report=None,
        result={},
    )
    epoch2 = ProgressEvaluationService().evaluate_task_completion(
        task_spec=task,
        state=state,
        observation=second,
        report=None,
        result={},
    )

    assert epoch1 is not None and epoch1.status == CriterionStatus.UNKNOWN
    assert epoch2 is not None and epoch2.status == CriterionStatus.UNKNOWN
    assert epoch2.criterion_results == ()


def test_final_recheck_uses_runtime_owned_canonical_resource_version() -> None:
    criterion_id = "criterion:resource-current"
    task = TaskSpec(
        task_id="task:resource-current",
        revision=1,
        objective="verify current resource",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(
            ("resource",), OperationClass.READ_ONLY, "request:resource-current", ()
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("resource",)),
        success=SuccessExpression(
            expression_id="success:resource-current",
            operator="criterion",
            criterion_id=criterion_id,
            requirement_refs=("requirement:effect:1",),
            policy=CriterionPolicy(
                validity=EvidenceValidityMode.FINAL_RECHECK,
                minimum_assurance=AssuranceLevel.AUTHORITATIVE,
                allowed_source_kinds=(EvidenceSourceKind.API_STATE,),
            ),
        ),
        final_recheck_criterion_ids=(criterion_id,),
        source_request_ref="request:resource-current",
    )
    observation = Observation("revision:resource", snapshot_id="snapshot:resource")
    canonical = UnifiedObservation(
        snapshot_id=observation.snapshot_id,
        page_revision=observation.page_revision,
        environment_revision=observation.environment_revision,
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id="target",
                surface="api",
                role="resource",
                label="Resource",
                supported_actions=("read",),
                state={"status": "ready"},
            ),
        ),
    )
    report = VerificationReport(
        VerificationStatus.PASSED,
        [
            VerificationEvidence(
                verifier_kind="http_json",
                target="target:status",
                passed=True,
                source="api_state",
                observed="ready",
                evidence_id="verification:resource",
                criterion_ids=(criterion_id,),
                environment_revision=observation.environment_revision,
                snapshot_id=observation.snapshot_id,
                strength="authoritative",
            )
        ],
    )
    state = SimpleNamespace(
        current_contract=None,
        task_progress=SimpleNamespace(
            recent_action_outcomes=RecentActionOutcomeEvidenceIndex(),
            durable_evidence=DurableEvidenceStore(),
        ),
        uncertain_external_effects=(),
    )

    evaluation = ProgressEvaluationService().evaluate_task_completion(
        task_spec=task,
        state=state,
        observation=observation,
        canonical_observation=canonical,
        report=report,
        result={},
    )

    assert evaluation is not None and evaluation.status == CriterionStatus.SATISFIED

    strong_only = ProgressEvaluationService().evaluate_task_completion(
        task_spec=task,
        state=state,
        observation=observation,
        canonical_observation=canonical,
        report=VerificationReport(
            VerificationStatus.PASSED,
            [replace(report.evidence[0], strength="strong")],
        ),
        result={},
    )
    assert strong_only is not None and strong_only.status == CriterionStatus.UNKNOWN
    assert strong_only.missing_rechecks == (criterion_id,)


@pytest.mark.parametrize("runtime_lineage", (False, True))
def test_action_caused_uses_runtime_lineage_not_observation_claims(runtime_lineage: bool) -> None:
    criterion_id = "criterion:caused"
    task = TaskSpec(
        task_id="task:caused",
        revision=1,
        objective="cause the setting change",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(
            ("settings",), OperationClass.REVERSIBLE_WRITE, "request:caused", ()
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("settings",)),
        success=SuccessExpression(
            expression_id="success:caused",
            operator="criterion",
            criterion_id=criterion_id,
            requirement_refs=("requirement:effect:1",),
            policy=CriterionPolicy(
                satisfaction=SatisfactionMode.ACTION_CAUSED,
                causal_lineage_required=True,
            ),
        ),
        source_request_ref="request:caused",
    )
    observation = Observation(
        "revision:post",
        snapshot_id="snapshot:post",
        metadata={
            "current_contract_id": "contract:forged",
            "criterion_evaluations": {
                criterion_id: {
                    "status": "satisfied",
                    "evidence_refs": ["evidence:observation-claim"],
                    "source_kind": "dom_state",
                    "assurance": "structural",
                    "contract_id": "contract:1",
                    "receipt_ref": "receipt:1",
                    "pre_observation_ref": "snapshot:pre",
                    "post_observation_ref": "snapshot:post",
                    "effect_criterion_ids": [criterion_id],
                }
            },
        },
    )
    recent = RecentActionOutcomeEvidenceIndex()
    if runtime_lineage:
        recent.append(
            RecentActionOutcomeEvidence(
                outcome_id="outcome:1",
                contract_id="contract:1",
                receipt_ref="receipt:1",
                pre_observation_ref="snapshot:pre",
                post_observation_ref="snapshot:post",
                effect_criterion_ids=(criterion_id,),
                evidence_refs=("evidence:runtime",),
                effect_satisfied=True,
                facts=(
                    RecentActionFact(
                        subject_ref="settings",
                        before_value=False,
                        after_value=True,
                        source_kind=EvidenceSourceKind.DOM_STATE,
                        assurance=AssuranceLevel.STRUCTURAL,
                        effect_criterion_ids=(criterion_id,),
                        evidence_refs=("evidence:runtime",),
                        state_delta_id="delta:1",
                    ),
                ),
            )
        )
    state = SimpleNamespace(
        current_contract=SimpleNamespace(id="contract:1"),
        task_progress=SimpleNamespace(
            recent_action_outcomes=recent,
            durable_evidence=DurableEvidenceStore(),
        ),
        uncertain_external_effects=(),
    )

    evaluation = ProgressEvaluationService().evaluate_task_completion(
        task_spec=task,
        state=state,
        observation=observation,
        report=None,
        result={},
    )

    assert evaluation is not None
    assert evaluation.status == (CriterionStatus.SATISFIED if runtime_lineage else CriterionStatus.UNKNOWN)

"""Compact P0 correctness redlines, organized by typed failure surface."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
from affordance_runtime.action_contract_builder import ActionContractBuilder
from affordance_runtime.action_selection import (
    ActionSelectionError,
    ActionSelectionValidator,
    SelectionRejectionCode,
)
from affordance_runtime.choice_contracts import (
    ActionChoice,
    ActionSelection,
    ChoiceBuildReport,
    ChoiceRejection,
    SelectChoice,
)
from affordance_runtime.choice_presentation import ChoicePresentationProjector
from affordance_runtime.grounding import (
    DomGroundingPayload,
    GroundingCandidate,
    GroundingSource,
    WoTGroundingPayload,
)
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.semantic_audit import SemanticAudit, SemanticAuditStatus
from affordance_runtime.source_context import TaskSpecGap
from affordance_runtime.source_envelope import SourceEnvelopeBuilder
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    OperationClass,
    RequestedEffect,
    TaskRequirement,
    TaskSemanticPayload,
    TaskSpec,
    UserRequest,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.task_spec_authority import MinimalIntentProposal, TaskSpecAuthority
from affordance_runtime.unified_observation import (
    CoverageCompleteness,
    CoverageStatus,
    SourceCoverage,
    UnifiedObservation,
    UnifiedObservationTarget,
)
from affordance_runtime.verification.contracts import (
    CriterionEvaluation,
    CriterionStatus,
    OutputSpec,
    SuccessExpression,
)
from affordance_runtime.verification.task_completion import TaskCompletionEvaluator

ROOT = Path(__file__).parents[2]
RUNTIME = ROOT / "src" / "affordance_runtime"


def _choices(count: int = 4) -> tuple[ActionChoice, ...]:
    return tuple(
        ActionChoice(
            choice_id=f"choice:{index:03}",
            task_revision=1,
            state_version=2,
            snapshot_id="observation:2",
            active_step_id="step:active",
            action_kind=PlannerActionKind.ACTIVATE,
            target_id=f"target:{index:03}",
            target_label=f"Target {index} " + "x" * 300,
            relevant_current_state={f"state:{item}": item for item in range(13)},
            criterion_ids=("criterion:done",),
        )
        for index in range(count)
    )


def _catalog(*, realization: str = "eager", count: int = 4) -> ActionChoiceCatalog:
    return ActionChoiceCatalog.from_choices(
        task_revision=1,
        plan_revision=1,
        state_version=2,
        observation_ref="observation:2",
        active_step_id="step:active",
        choices=_choices(count),
        realization=realization,
    )


def _completion_task() -> TaskSpec:
    return TaskSpec(
        task_id="task:redline",
        revision=1,
        objective="save record",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=(
            *canonical_effect_requirements(("record",), OperationClass.REVERSIBLE_WRITE, "request:redline", ()),
            TaskRequirement(
                requirement_id="requirement:output:1",
                payload=TaskSemanticPayload(kind="output", subject="record"),
                source_anchor_refs=("request:redline",),
            ),
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("record",)),
        success=SuccessExpression(
            expression_id="success:root",
            operator="criterion",
            criterion_id="criterion:saved",
            requirement_refs=("requirement:effect:1", "requirement:output:1"),
        ),
        required_outputs=(
            OutputSpec(
                output_id="record",
                requirement_ref="requirement:output:1",
                materialization_criterion_id="criterion:output",
                source_binding_requirement=("source:any",),
            ),
        ),
        source_request_ref="request:redline",
    )


def _case_target_81() -> None:
    catalog = _catalog(count=81)
    page = ChoicePresentationProjector(page_size=80).project(catalog)
    assert catalog.count == 81
    assert catalog.contains("choice:080")
    assert page.total_choice_count == 81 and page.truncated


def _case_state_13() -> None:
    target = UnifiedObservationTarget(
        target_id="target:state",
        surface="dom",
        role="form",
        label="Stateful form",
        supported_actions=("activate",),
        state={f"field:{index}": index for index in range(13)},
    )
    observation = UnifiedObservation(
        snapshot_id="observation:state",
        page_revision="page:1",
        environment_revision="env:1",
        observed_text="",
        targets=(target,),
    )
    assert len(observation.targets[0].state) == 13
    assert observation.targets[0].state["field:12"] == 12


def _case_projection_truncation() -> None:
    catalog = _catalog()
    projections = tuple(
        ChoicePresentationProjector(page_size=size, projection_policy_id=f"view:{size}").project(catalog)
        for size in (1, 2, 4)
    )
    assert {item.catalog_digest for item in projections} == {catalog.catalog_digest}
    assert all(item.total_choice_count == 4 for item in projections)
    assert catalog.get("choice:003").target_label.endswith("x" * 300)  # type: ignore[union-attr]


def _case_presentation_policy() -> None:
    first = _catalog()
    second = _catalog()
    ChoicePresentationProjector(page_size=1, projection_policy_id="provider:a").project(first)
    ChoicePresentationProjector(page_size=3, projection_policy_id="provider:b").project(second)
    assert (first.count, first.catalog_digest) == (second.count, second.catalog_digest)
    assert tuple(item.choice_id for item in first.page(None, 10).choices) == tuple(
        item.choice_id for item in second.page(None, 10).choices
    )


def _case_realization() -> None:
    catalogs = tuple(_catalog(realization=value) for value in ("eager", "lazy", "indexed"))
    assert len({item.catalog_digest for item in catalogs}) == 1
    assert all(item.count == 4 and item.contains("choice:003") for item in catalogs)


def _case_acquisition_truncation() -> None:
    coverage = SourceCoverage(
        source=GroundingSource.DOM,
        capture_policy_id="bounded-acquisition",
        captured_item_count=80,
        truncated=True,
        omitted_item_count_estimate=1,
        completeness=CoverageCompleteness.BOUNDED,
        status=CoverageStatus.ACQUISITION_TRUNCATED,
    )
    assert coverage.status == CoverageStatus.ACQUISITION_TRUNCATED
    assert coverage.status != CoverageStatus.TARGET_ABSENT_COMPLETE


def _case_material_conflict() -> None:
    rejection = ChoiceRejection("target:conflict", PlannerActionKind.ACTIVATE, "material_conflict")
    catalog = ActionChoiceCatalog.from_choices(
        task_revision=1,
        plan_revision=1,
        state_version=2,
        observation_ref="observation:2",
        active_step_id="step:active",
        choices=(),
        build_report=ChoiceBuildReport(1, 0, (rejection,)),
    )
    assert catalog.count == 0
    assert catalog.build_report.rejections == (rejection,)


def _binding(candidate_id: str, source: GroundingSource) -> GroundingCandidate:
    payload = (
        DomGroundingPayload(selector="#save")
        if source == GroundingSource.DOM
        else WoTGroundingPayload(thing_id="thing:save", form_index=0, operation="invoke")
    )
    return GroundingCandidate(
        candidate_id=candidate_id,
        semantic_target_id="target:save",
        source=source,
        payload=payload,
        compatible_executor=source.value,
        observation_epoch_id="observation:2",
        environment_revision="env:1",
        page_revision="page:1",
        target_fingerprint=candidate_id,
        supported_actions=frozenset({"activate"}),
        evidence_kinds=frozenset(),
    )


def _case_multi_binding() -> None:
    bindings = (_binding("binding:dom", GroundingSource.DOM), _binding("binding:wot", GroundingSource.WOT))
    observation = UnifiedObservation(
        snapshot_id="observation:2",
        page_revision="page:1",
        environment_revision="env:1",
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id="target:save",
                surface="multi",
                role="button",
                label="Save",
                supported_actions=("activate",),
                state={},
            ),
        ),
        bindings=bindings,
    )
    catalog = ActionChoiceCatalog.from_choices(
        task_revision=1,
        plan_revision=1,
        state_version=2,
        observation_ref=observation.epoch_id,
        active_step_id="step:active",
        choices=(
            _choices(1)[0].__class__(
                choice_id="choice:save",
                task_revision=1,
                state_version=2,
                snapshot_id="observation:2",
                active_step_id="step:active",
                action_kind=PlannerActionKind.ACTIVATE,
                target_id="target:save",
            ),
        ),
    )
    assert catalog.count == 1
    assert len([item for item in observation.bindings if item.semantic_target_id == "target:save"]) == 2


def _case_hidden_selection() -> None:
    catalog = _catalog()
    page = ChoicePresentationProjector(page_size=1).project(catalog)
    with pytest.raises(ActionSelectionError) as exc:
        ActionSelectionValidator().validate(SelectChoice("choice:003"), catalog, page)
    assert exc.value.code == SelectionRejectionCode.UNPRESENTED_CHOICE_ID


def _case_contract_identity() -> None:
    catalog = _catalog(count=1)
    selection = ActionSelection(
        choice_id="choice:000",
        catalog_ref=catalog.ref,
        task_revision=1,
        plan_revision=1,
        state_version=0,
        observation_ref="stale-observation",
        active_step_id="step:active",
    )
    observation = UnifiedObservation(
        snapshot_id="observation:2",
        page_revision="page:1",
        environment_revision="env:1",
        observed_text="",
        targets=(),
    )
    with pytest.raises(ValueError, match="current observation"):
        ActionContractBuilder().build(
            selection,
            catalog,
            _completion_task(),
            StateKernel("task:redline", "save record"),
            None,  # type: ignore[arg-type]
            observation,
        )


def _case_raw_text_read_set() -> None:
    prohibited = (
        "action_choice_catalog.py",
        "action_selection.py",
        "action_contract_builder.py",
        "action_admission.py",
        "execution_phase.py",
        "runtime_committer.py",
        "verification/task_completion.py",
    )
    for name in prohibited:
        tree = ast.parse((RUNTIME / name).read_text(encoding="utf-8"))
        identifiers = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert "raw_text" not in identifiers
        assert not any(value.endswith("source_context") for value in imports)


def _case_prose_not_completion() -> None:
    evaluation = TaskCompletionEvaluator().evaluate(
        task_spec=_completion_task(),
        criterion_results=(),
        result_payload={
            "receipt_success": True,
            "latest_report_passed": True,
            "plan_exhausted": True,
            "summary": "done",
        },
        output_source_bindings={"record": ("resource:1",)},
    )
    assert evaluation.status != CriterionStatus.SATISFIED and not evaluation.completed


def _case_output_closure() -> None:
    evaluation = TaskCompletionEvaluator().evaluate(
        task_spec=_completion_task(),
        criterion_results=(
            CriterionEvaluation("criterion:saved", CriterionStatus.SATISFIED),
            CriterionEvaluation("criterion:output", CriterionStatus.SATISFIED),
        ),
        result_payload={"record": {"id": "1"}},
        output_source_bindings={},
    )
    assert evaluation.status == CriterionStatus.UNSATISFIED and not evaluation.completed


def _case_task_spec_gap() -> None:
    gap = TaskSpecGap(
        gap_id="gap:recipient",
        missing_field="recipient",
        anchor_ids=("anchor:recipient",),
        clarification="Which recipient?",
    )
    with pytest.raises(Exception):
        gap.missing_field = "silently-filled"  # type: ignore[misc]
    assert not hasattr(gap, "apply") and not hasattr(gap, "patch_task_spec")


def _case_default_thin_source() -> None:
    request = UserRequest(request_id="thin", raw_text="Open settings")
    envelope = SourceEnvelopeBuilder().build(request)
    proposal = MinimalIntentProposal(
        objective="Open settings",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="settings",
                source_ref=envelope.whole_request_anchor.anchor_id,
            ),
        ),
        success=SuccessExpression(
            expression_id="success:settings",
            operator="criterion",
            criterion_id="criterion:settings-visible",
            requirement_refs=("requirement:effect:1",),
        ),
    )
    result = TaskSpecAuthority().admit(request, envelope, proposal)
    assert result.task_spec is not None
    assert not hasattr(result.task_spec, "source_claims")
    assert not hasattr(result.task_spec, "obligations")
    assert importlib.util.find_spec("affordance_runtime.source_ledger") is None


def test_task_spec_v2_has_one_canonical_field_set() -> None:
    assert set(TaskSpec.model_fields) == {
        "schema_version",
        "task_id",
        "revision",
        "objective",
        "operation_class",
        "requirements",
        "inputs",
        "allowed_effect_refs",
        "hard_constraint_refs",
        "preference_refs",
        "forbidden_effect_refs",
        "capability_ceiling",
        "risk_policy",
        "success",
        "required_outputs",
        "criterion_source_bindings",
        "constraint_criterion_ids",
        "external_effect_criterion_ids",
        "final_recheck_criterion_ids",
        "semantic_value_constraints",
        "evidence_requirements",
        "source_request_ref",
        "source_envelope_ref",
        "source_binding_digest",
        "created_at_s",
    }


def _case_audit_negative_authority() -> None:
    request = UserRequest(request_id="audit", raw_text="Open settings")
    envelope = SourceEnvelopeBuilder().build(request)
    proposal = MinimalIntentProposal(
        objective="Open settings",
        requested_effects=(
            RequestedEffect(
                operation_class=OperationClass.NAVIGATION,
                target="settings",
                source_ref=envelope.whole_request_anchor.anchor_id,
            ),
        ),
        success=SuccessExpression(
            expression_id="success:settings",
            operator="criterion",
            criterion_id="criterion:settings-visible",
            requirement_refs=("requirement:effect:1",),
        ),
    )
    result = SemanticAudit().evaluate(envelope, proposal, material_conflicts=("recipient",))
    assert set(SemanticAuditStatus) == {
        SemanticAuditStatus.PASS,
        SemanticAuditStatus.VETO,
        SemanticAuditStatus.CLARIFICATION_REQUIRED,
    }
    assert result.status == SemanticAuditStatus.VETO
    assert not hasattr(result, "proposal") and not hasattr(result, "task_spec")


def _case_p1_recovery_commit_boundaries() -> None:
    loop_tree = ast.parse((RUNTIME / "runtime_loop_phase.py").read_text(encoding="utf-8"))
    loop_calls = {
        node.func.id
        if isinstance(node.func, ast.Name)
        else node.func.attr
        if isinstance(node.func, ast.Attribute)
        else ""
        for node in ast.walk(loop_tree)
        if isinstance(node, ast.Call)
    }
    assert loop_calls.isdisjoint({"classify_failure", "build_failure_owner_handoff", "verify"})

    committer_tree = ast.parse((RUNTIME / "runtime_committer.py").read_text(encoding="utf-8"))
    committer = next(
        node for node in committer_tree.body if isinstance(node, ast.ClassDef) and node.name == "RuntimeCommitter"
    )
    methods = {node.name for node in committer.body if isinstance(node, ast.FunctionDef)}
    names = {node.id for node in ast.walk(committer) if isinstance(node, ast.Name)}
    assert methods.isdisjoint({"commit_failure_owner", "commit_action"})
    assert names.isdisjoint({"RecoveryOutcome", "classify_failure", "build_failure_owner_handoff"})
    assert not (RUNTIME / "task_planning.py").exists()
    assert not (RUNTIME / "legacy_task_plan_provider.py").exists()
    planner_tree = ast.parse((RUNTIME / "task_planner.py").read_text(encoding="utf-8"))
    imported_modules = {node.module or "" for node in ast.walk(planner_tree) if isinstance(node, ast.ImportFrom)}
    assert "affordance_runtime.task_planning" not in imported_modules


CASES = {
    "P0-01-target-81": _case_target_81,
    "P0-02-state-13": _case_state_13,
    "P0-03-projection-truncation": _case_projection_truncation,
    "P0-04-presentation-policy": _case_presentation_policy,
    "P0-05-realization": _case_realization,
    "P0-06-acquisition-truncation": _case_acquisition_truncation,
    "P0-07-material-conflict": _case_material_conflict,
    "P0-08-multi-binding": _case_multi_binding,
    "P0-09-hidden-selection": _case_hidden_selection,
    "P0-10-contract-identity": _case_contract_identity,
    "P0-11-raw-text-read-set": _case_raw_text_read_set,
    "P0-12-no-prose-completion": _case_prose_not_completion,
    "P0-13-output-closure": _case_output_closure,
    "P0-14-task-spec-gap": _case_task_spec_gap,
    "P0-15-thin-default-source": _case_default_thin_source,
    "P0-16-audit-negative-authority": _case_audit_negative_authority,
    "P1-01-recovery-commit-boundaries": _case_p1_recovery_commit_boundaries,
}


@pytest.mark.parametrize("invariant_id", CASES, ids=CASES)
def test_runtime_redline_matrix(invariant_id: str) -> None:
    CASES[invariant_id]()

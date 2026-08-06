from __future__ import annotations

from dataclasses import replace

import pytest

from affordance_runtime.action_admission import ActionAdmissionService, AdmissionGate
from affordance_runtime.action_choice_authority import authorize_choice
from affordance_runtime.action_choice_builder import ActionChoiceCatalogBuilder
from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
from affordance_runtime.action_contract_builder import ActionContractBuilder
from affordance_runtime.action_selection import ActionSelection
from affordance_runtime.active_step_scope import ActiveStepScope
from affordance_runtime.choice_contracts import ActionChoice, ActionChoiceFailure
from affordance_runtime.contracts import ActionContract, Observation, RiskLevel, RuntimeErrorCode
from affordance_runtime.criteria import PredicateExpr, PredicateOperator, SubjectExpr
from affordance_runtime.effect_authority_contracts import (
    AuthorityStatus,
    EffectAuthorizationScope,
    EffectClass,
    ResourceScopeRef,
)
from affordance_runtime.grounding import DomGroundingPayload, GroundingCandidate, GroundingSource
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.simplified_runtime_contracts import (
    ElementIntent,
    SourceReference,
    StepActivityStatus,
    StepSpec,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    OperationClass,
    TaskRequirement,
    TaskSemanticPayload,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.unified_observation import UnifiedObservation, UnifiedObservationTarget
from affordance_runtime.verification.contracts import AssuranceLevel, CriterionPolicy, SuccessExpression


def _choices():
    from affordance_runtime.choice_contracts import ActionChoice

    return tuple(
        ActionChoice(
            choice_id=f"choice:{index}",
            task_revision=3,
            state_version=7,
            snapshot_id="observation:7",
            active_step_id="step:current",
            action_kind=PlannerActionKind.ACTIVATE,
            target_id=f"target:{index}",
            criterion_ids=("criterion:done",),
        )
        for index in range(4)
    )


@pytest.mark.parametrize("realization", ["eager", "lazy", "indexed"])
@pytest.mark.parametrize("page_size", [1, 2, 10])
def test_catalog_semantics_are_invariant_to_realization_and_presentation(
    realization: str,
    page_size: int,
) -> None:
    """Failure: model/materialization budgets used to own Runtime membership.

    Owner: ActionChoiceCatalog. Existing builder tests only covered eager tuples
    and could not detect a digest/order change caused by page policy. This test
    retires when Catalog has a stronger shared conformance suite.
    """
    from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
    from affordance_runtime.choice_presentation import ChoicePresentationProjector

    catalog = ActionChoiceCatalog.from_choices(
        task_revision=3,
        plan_revision=2,
        state_version=7,
        observation_ref="observation:7",
        active_step_id="step:current",
        choices=_choices(),
        realization=realization,
    )
    page = ChoicePresentationProjector(page_size=page_size).project(catalog)

    assert catalog.count == 4
    assert tuple(choice.choice_id for choice in catalog.page(None, 10).choices) == (
        "choice:0",
        "choice:1",
        "choice:2",
        "choice:3",
    )
    assert (
        catalog.catalog_digest
        == ActionChoiceCatalog.from_choices(
            task_revision=3,
            plan_revision=2,
            state_version=7,
            observation_ref="observation:7",
            active_step_id="step:current",
            choices=_choices(),
            realization="eager",
        ).catalog_digest
    )
    assert page.total_choice_count == 4
    assert page.included_choice_count == min(page_size, 4)


def test_selection_rejects_catalog_member_not_presented_on_current_page() -> None:
    """Failure: a guessed hidden catalog ID could previously be dispatched.

    Owner: ActionSelectionValidator. Existing validation only checked full-set
    membership, so it could not distinguish unknown from unpresented IDs. The
    test retires only if this invariant moves into a shared selection suite.
    """
    from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
    from affordance_runtime.action_selection import (
        ActionSelectionError,
        ActionSelectionValidator,
        SelectionRejectionCode,
    )
    from affordance_runtime.choice_contracts import SelectChoice
    from affordance_runtime.choice_presentation import ChoicePresentationProjector

    catalog = ActionChoiceCatalog.from_choices(
        task_revision=3,
        plan_revision=2,
        state_version=7,
        observation_ref="observation:7",
        active_step_id="step:current",
        choices=_choices(),
    )
    page = ChoicePresentationProjector(page_size=1).project(catalog)

    with pytest.raises(ActionSelectionError) as exc_info:
        ActionSelectionValidator().validate(
            SelectChoice("choice:3", "guessed hidden id"),
            catalog,
            page,
        )

    assert exc_info.value.code == SelectionRejectionCode.UNPRESENTED_CHOICE_ID


def test_choice_serializer_projects_only_the_displayed_page_without_runtime_handles() -> None:
    from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
    from affordance_runtime.choice_contracts import ChoicePlanningRequest
    from affordance_runtime.choice_presentation import ChoicePresentationProjector
    from affordance_runtime.planning_request_serializer import (
        serialize_choice_planning_request,
    )

    catalog = ActionChoiceCatalog.from_choices(
        task_revision=3,
        plan_revision=2,
        state_version=7,
        observation_ref="observation:7",
        active_step_id="step:current",
        choices=_choices(),
    )
    page = ChoicePresentationProjector(page_size=2).project(catalog)
    payload = serialize_choice_planning_request(ChoicePlanningRequest(3, 2, "step:current", catalog.ref, page))

    assert [item["choice_id"] for item in payload["choices"]] == [
        "choice:0",
        "choice:1",
    ]
    encoded = repr(payload).casefold()
    for forbidden in ("selector", "coordinate", "backend", "locator", "approval"):
        assert forbidden not in encoded


def test_choice_presentation_uses_runtime_authority_risk_and_destination() -> None:
    from affordance_runtime.choice_presentation import ChoicePresentationProjector

    choice = ActionChoice(
        choice_id="choice:risk",
        task_revision=1,
        state_version=0,
        snapshot_id="snapshot:risk",
        active_step_id="step:risk",
        action_kind=PlannerActionKind.DRAG,
        target_id="target:source",
        target_label="Source",
        destination_id="target:destination",
        destination_label="Approved",
        requirement_refs=("requirement:risk",),
        effect_refs=("requirement:risk",),
        risk="high",
    )
    catalog = ActionChoiceCatalog.from_choices(
        task_revision=1,
        plan_revision=1,
        state_version=0,
        observation_ref="snapshot:risk",
        active_step_id="step:risk",
        choices=(choice,),
    )

    presented = ChoicePresentationProjector().project(catalog).choices[0]

    assert presented.risk == "high"
    assert presented.destination_label == "Approved"
    assert presented.effect_refs == ("requirement:risk",)


def _effect_task(subject: str) -> TaskSpec:
    return TaskSpec(
        task_id="task:catalog-authority",
        revision=1,
        objective=f"Delete {subject}",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=(
            TaskRequirement(
                requirement_id="requirement:effect:1",
                payload=TaskSemanticPayload(
                    kind="effect",
                    subject=f"Delete {subject}",
                    target_identity=f"target:delete:{subject.casefold()}",
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    effect_authorization_scope=EffectAuthorizationScope(
                        requirement_ref="requirement:effect:1",
                        operation_constraint="resource.update@v1",
                        resource_scope=ResourceScopeRef(f"target:delete:{subject.casefold()}"),
                        effect_class=EffectClass.UPDATE,
                    ),
                ),
                source_anchor_refs=("request:catalog-authority",),
            ),
        ),
        allowed_effect_refs=canonical_effect_requirement_refs((f"Delete {subject}",)),
        success=SuccessExpression(
            expression_id="success:catalog-authority",
            operator="criterion",
            criterion_id="criterion:deleted",
            requirement_refs=("requirement:effect:1",),
        ),
        source_request_ref="request:catalog-authority",
    )


def _effect_step(target: str):
    source = SourceReference("request:catalog-authority", "request:catalog-authority:whole")
    return StepSpec(
        step_id="step:delete",
        objective=f"Delete {target}",
        interaction=ElementIntent(f"Delete {target}", (source,)),
        completion_criteria=(
            PredicateExpr(
                "criterion:deleted",
                SubjectExpr("semantic_target", f"Delete {target}"),
                PredicateOperator.CHANGED,
                CriterionPolicy(),
            ),
        ),
        source_refs=(source,),
        requirement_refs=("requirement:effect:1",),
        effect_authorization_refs=("requirement:effect:1",),
        effectful=True,
    )


def _delete_observation(target: str) -> UnifiedObservation:
    return UnifiedObservation(
        snapshot_id="snapshot:delete",
        page_revision="page:delete",
        environment_revision="env:delete",
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id=f"target:delete:{target.casefold()}",
                surface="dom",
                role="button",
                label=f"Delete {target}",
                supported_actions=("activate",),
                state={"enabled": True, "visible": True},
                risk=RiskLevel.MEDIUM,
                risk_asserted=True,
                operation_ref="resource.update@v1",
                effect_class=EffectClass.UPDATE.value,
                source_assurance=AssuranceLevel.STRUCTURAL,
                externality="local",
                reversibility="reversible",
            ),
        ),
    )


def test_catalog_rejects_concrete_target_outside_exact_effect_authority() -> None:
    task = _effect_task("Alice")
    step = _effect_step("Bob")
    observation = _delete_observation("Bob")
    scope = ActiveStepScope.from_active_step(
        task_revision=task.revision,
        evaluated_at_state_version=0,
        snapshot_id=observation.epoch_id,
        step=step,
        activity_status=StepActivityStatus.ACTIVE,
    )

    result = ActionChoiceCatalogBuilder().build(
        task_revision=task.revision,
        task_spec=task,
        plan_revision=1,
        state_version=0,
        step=step,
        scope=scope,
        observation=observation,
    )

    assert isinstance(result, ActionChoiceFailure)
    assert result.reason_code == "authority_denied"
    assert result.build_report is not None
    assert result.build_report.rejections
    assert {item.status for item in result.build_report.rejections} == {AuthorityStatus.DENY}
    assert all(item.reason_codes for item in result.build_report.rejections)


def test_catalog_derives_effect_and_risk_instead_of_trusting_planner_flags() -> None:
    task = _effect_task("Alice")
    step = replace(_effect_step("Alice"), effect_authorization_refs=(), effectful=False)
    observation = _delete_observation("Alice")
    result = ActionChoiceCatalogBuilder().build(
        task_revision=1,
        task_spec=task,
        plan_revision=1,
        state_version=0,
        step=step,
        scope=ActiveStepScope.from_active_step(
            task_revision=1,
            evaluated_at_state_version=0,
            snapshot_id=observation.epoch_id,
            step=step,
            activity_status=StepActivityStatus.ACTIVE,
        ),
        observation=observation,
    )

    assert not isinstance(result, ActionChoiceFailure)
    choice = result.page(None, 1).choices[0]
    assert choice.effect_refs == ("requirement:effect:1",)
    assert choice.effectful
    assert choice.risk == "medium"
    assert choice.authorization_scope_digest.startswith("sha256:")


def test_catalog_rejects_planner_declared_read_only_destructive_target() -> None:
    task = TaskSpec(
        task_id="task:navigation-authority",
        revision=1,
        objective="Open settings",
        operation_class=OperationClass.NAVIGATION,
        requirements=(
            TaskRequirement(
                requirement_id="requirement:open-settings",
                payload=TaskSemanticPayload(
                    kind="effect",
                    subject="Open settings",
                    target_identity="Open settings",
                    operation_class=OperationClass.NAVIGATION,
                ),
                source_anchor_refs=("request:navigation",),
            ),
        ),
        allowed_effect_refs=("requirement:open-settings",),
        success=SuccessExpression(
            expression_id="success:settings-open",
            operator="criterion",
            criterion_id="criterion:settings-open",
            requirement_refs=("requirement:open-settings",),
        ),
        source_request_ref="request:navigation",
    )
    source = SourceReference("request:navigation", "request:navigation:whole")
    step = StepSpec(
        step_id="step:delete-account",
        objective="Delete account",
        interaction=ElementIntent("Delete account", (source,)),
        completion_criteria=(
            PredicateExpr(
                "criterion:settings-open",
                SubjectExpr("semantic_target", "Delete account"),
                PredicateOperator.CHANGED,
                CriterionPolicy(),
            ),
        ),
        source_refs=(source,),
        requirement_refs=("requirement:open-settings",),
        effect_authorization_refs=(),
        effectful=False,
    )
    observation = UnifiedObservation(
        snapshot_id="snapshot:navigation",
        page_revision="page:navigation",
        environment_revision="env:navigation",
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id="target:delete-account",
                surface="dom",
                role="button",
                label="Delete account",
                supported_actions=("activate",),
                state={"enabled": True},
                risk=RiskLevel.IRREVERSIBLE,
            ),
        ),
    )
    scope = ActiveStepScope.from_active_step(
        task_revision=1,
        evaluated_at_state_version=0,
        snapshot_id=observation.epoch_id,
        step=step,
        activity_status=StepActivityStatus.ACTIVE,
    )

    result = ActionChoiceCatalogBuilder().build(
        task_revision=1,
        task_spec=task,
        plan_revision=1,
        state_version=0,
        step=step,
        scope=scope,
        observation=observation,
    )

    assert isinstance(result, ActionChoiceFailure)


def test_catalog_rejects_observed_action_risk_above_admitted_operation_class() -> None:
    task = TaskSpec(
        task_id="task:read-account",
        revision=1,
        objective="Inspect account control",
        operation_class=OperationClass.READ_ONLY,
        requirements=canonical_effect_requirements(
            ("Account control",), OperationClass.READ_ONLY, "request:read-account", ()
        ),
        allowed_effect_refs=("requirement:effect:1",),
        success=SuccessExpression(
            expression_id="success:read-account",
            operator="criterion",
            criterion_id="criterion:read-account",
            requirement_refs=("requirement:effect:1",),
        ),
        source_request_ref="request:read-account",
    )
    source = SourceReference("request:read-account", "request:read-account:whole")
    step = StepSpec(
        step_id="step:account",
        objective="Inspect account control",
        interaction=ElementIntent("Account control", (source,)),
        completion_criteria=(
            PredicateExpr(
                "criterion:read-account",
                SubjectExpr("semantic_target", "Account control"),
                PredicateOperator.CHANGED,
                CriterionPolicy(),
            ),
        ),
        source_refs=(source,),
        requirement_refs=("requirement:effect:1",),
        effect_authorization_refs=("requirement:effect:1",),
        effectful=False,
    )
    observation = UnifiedObservation(
        snapshot_id="snapshot:account",
        page_revision="page:account",
        environment_revision="env:account",
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id="target:account",
                surface="dom",
                role="button",
                label="Account control",
                supported_actions=("activate",),
                state={},
                risk=RiskLevel.IRREVERSIBLE,
            ),
        ),
    )
    result = ActionChoiceCatalogBuilder().build(
        task_revision=1,
        task_spec=task,
        plan_revision=1,
        state_version=0,
        step=step,
        scope=ActiveStepScope.from_active_step(
            task_revision=1,
            evaluated_at_state_version=0,
            snapshot_id=observation.epoch_id,
            step=step,
            activity_status=StepActivityStatus.ACTIVE,
        ),
        observation=observation,
    )

    assert isinstance(result, ActionChoiceFailure)


def test_non_english_target_identity_is_exact_without_keyword_fallback() -> None:
    task = _effect_task("unused").model_copy(
        update={
            "objective": "删除爱丽丝",
            "requirements": (
                TaskRequirement(
                    requirement_id="requirement:effect:1",
                    payload=TaskSemanticPayload(
                        kind="effect",
                        subject="爱丽丝",
                        target_identity="爱丽丝",
                        operation_class=OperationClass.REVERSIBLE_WRITE,
                    ),
                    source_anchor_refs=("request:catalog-authority",),
                ),
            ),
        }
    )
    source = SourceReference("request:catalog-authority", "request:catalog-authority:whole")
    step = StepSpec(
        step_id="step:delete",
        objective="删除鲍勃",
        interaction=ElementIntent("鲍勃", (source,)),
        completion_criteria=(
            PredicateExpr(
                "criterion:deleted",
                SubjectExpr("semantic_target", "鲍勃"),
                PredicateOperator.CHANGED,
                CriterionPolicy(),
            ),
        ),
        source_refs=(source,),
        requirement_refs=("requirement:effect:1",),
        effect_authorization_refs=("requirement:effect:1",),
        effectful=True,
    )
    observation = UnifiedObservation(
        snapshot_id="snapshot:delete",
        page_revision="page:delete",
        environment_revision="env:delete",
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id="target:bob",
                surface="dom",
                role="button",
                label="鲍勃",
                supported_actions=("activate",),
                state={},
            ),
        ),
    )
    result = ActionChoiceCatalogBuilder().build(
        task_revision=1,
        task_spec=task,
        plan_revision=1,
        state_version=0,
        step=step,
        scope=ActiveStepScope.from_active_step(
            task_revision=1,
            evaluated_at_state_version=0,
            snapshot_id="snapshot:delete",
            step=step,
            activity_status=StepActivityStatus.ACTIVE,
        ),
        observation=observation,
    )

    assert isinstance(result, ActionChoiceFailure)


def test_drag_destination_must_match_typed_effect_scope() -> None:
    task = TaskSpec(
        task_id="task:drag",
        revision=1,
        objective="Move Alice to Approved",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=(
            TaskRequirement(
                requirement_id="requirement:drag",
                payload=TaskSemanticPayload(
                    kind="effect",
                    subject="Alice",
                    target_identity="Alice",
                    destination_identity="Approved",
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                ),
                source_anchor_refs=("request:drag",),
            ),
        ),
        allowed_effect_refs=("requirement:drag",),
        success=SuccessExpression(
            expression_id="success:drag",
            operator="criterion",
            criterion_id="criterion:drag",
            requirement_refs=("requirement:drag",),
        ),
        source_request_ref="request:drag",
    )
    source = SourceReference("request:drag", "request:drag:whole")
    step = StepSpec(
        step_id="step:drag",
        objective="Move Alice",
        interaction=ElementIntent("Alice", (source,)),
        completion_criteria=(
            PredicateExpr(
                "criterion:drag",
                SubjectExpr("semantic_target", "Alice"),
                PredicateOperator.CHANGED,
                CriterionPolicy(),
            ),
        ),
        source_refs=(source,),
        requirement_refs=("requirement:drag",),
        effect_authorization_refs=("requirement:drag",),
        effectful=True,
    )
    observation = UnifiedObservation(
        snapshot_id="snapshot:drag",
        page_revision="page:drag",
        environment_revision="env:drag",
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id="target:alice",
                surface="dom",
                role="item",
                label="Alice",
                supported_actions=("drag",),
                state={},
            ),
            UnifiedObservationTarget(
                target_id="target:rejected",
                surface="dom",
                role="region",
                label="Rejected",
                supported_actions=("drag",),
                state={},
            ),
        ),
    )
    choice = ActionChoice(
        choice_id="choice:drag",
        task_revision=1,
        state_version=0,
        snapshot_id="snapshot:drag",
        active_step_id=step.step_id,
        action_kind=PlannerActionKind.DRAG,
        target_id="target:alice",
        destination_id="target:rejected",
        requirement_refs=("requirement:drag",),
    )

    assert not authorize_choice(choice, step, task, observation).authorized


def test_choice_and_action_contract_preserve_exact_authority_refs() -> None:
    task = _effect_task("A")
    choice = _choices()[0].__class__(
        choice_id="choice:authorized",
        task_revision=1,
        state_version=0,
        snapshot_id="snapshot:delete",
        active_step_id="step:delete",
        action_kind=PlannerActionKind.ACTIVATE,
        target_id="target:delete:a",
        requirement_refs=("requirement:effect:1",),
        effect_refs=("requirement:effect:1",),
    )
    proof = authorize_choice(choice, _effect_step("A"), task, _delete_observation("A"))
    choice = replace(
        choice,
        action_authority_proof=proof,
        risk=proof.risk.value,
    )
    catalog = ActionChoiceCatalog.from_choices(
        task_revision=1,
        plan_revision=1,
        state_version=0,
        observation_ref="snapshot:delete",
        active_step_id="step:delete",
        choices=(choice,),
    )
    selection = ActionSelection(
        choice_id=choice.choice_id,
        catalog_ref=catalog.ref,
        task_revision=1,
        plan_revision=1,
        state_version=0,
        observation_ref="snapshot:delete",
        active_step_id="step:delete",
    )

    class StubMaterializer:
        def build(self, proposal, task_spec, state, capture, observation):  # type: ignore[no-untyped-def]
            del proposal, task_spec, state, capture, observation
            return ActionContract(
                id="contract:authorized",
                intent="Delete A",
                affordance_id="target:delete:a",
                action="activate",
                backend="dom",
                environment_revision="env:delete",
                locator={"selector": "#delete-a"},
            )

    contract = ActionContractBuilder(StubMaterializer()).build(  # type: ignore[arg-type]
        selection,
        catalog,
        task,
        StateKernel(task.task_id, task.objective),
        None,  # type: ignore[arg-type]
        _delete_observation("A"),
    )

    assert contract.requirement_refs == ("requirement:effect:1",)
    assert contract.effect_authorization_refs == ("requirement:effect:1",)
    assert contract.effectful


def test_actual_binding_risk_escalation_requires_approval() -> None:
    task = _effect_task("A")
    step = _effect_step("A")
    candidate = GroundingCandidate(
        candidate_id="candidate:high-risk",
        semantic_target_id="target:delete:a",
        source=GroundingSource.DOM,
        payload=DomGroundingPayload(selector="#delete-a"),
        compatible_executor="browser",
        observation_epoch_id="snapshot:route-risk",
        environment_revision="env:route-risk",
        page_revision="page:route-risk",
        target_fingerprint="",
        supported_actions=frozenset({"activate"}),
        evidence_kinds=frozenset(),
        operation_ref="resource.update@v1",
        effect_class=EffectClass.UPDATE.value,
        externality="local",
        reversibility="reversible",
        resource_sensitivity="high",
        authority_source_assurance=AssuranceLevel.STRUCTURAL.value,
    )
    observation = UnifiedObservation(
        snapshot_id="snapshot:route-risk",
        page_revision="page:route-risk",
        environment_revision="env:route-risk",
        observed_text="",
        targets=(
            UnifiedObservationTarget(
                target_id="target:delete:a",
                surface="dom",
                role="button",
                label="Delete A",
                supported_actions=("activate",),
                state={"enabled": True},
                operation_ref="resource.update@v1",
                effect_class=EffectClass.UPDATE.value,
                externality="local",
                reversibility="reversible",
                resource_sensitivity="moderate",
                source_assurance=AssuranceLevel.STRUCTURAL,
            ),
        ),
        bindings=(candidate,),
    )
    choice = ActionChoice(
        choice_id="choice:route-risk",
        task_revision=1,
        state_version=0,
        snapshot_id=observation.epoch_id,
        active_step_id=step.step_id,
        action_kind=PlannerActionKind.ACTIVATE,
        target_id="target:delete:a",
        requirement_refs=("requirement:effect:1",),
        effect_refs=("requirement:effect:1",),
    )
    catalog_proof = authorize_choice(choice, step, task, observation)
    assert catalog_proof.risk == RiskLevel.MEDIUM
    choice = replace(
        choice,
        action_authority_proof=catalog_proof,
        risk=catalog_proof.risk.value,
    )
    catalog = ActionChoiceCatalog.from_choices(
        task_revision=1,
        plan_revision=1,
        state_version=0,
        observation_ref=observation.epoch_id,
        active_step_id=step.step_id,
        choices=(choice,),
    )
    selection = ActionSelection(
        choice.choice_id,
        catalog.ref,
        1,
        1,
        0,
        observation.epoch_id,
        step.step_id,
    )

    class HighRiskRouteMaterializer:
        def build(self, proposal, task_spec, state, capture, current_observation):  # type: ignore[no-untyped-def]
            del proposal, task_spec, state, capture, current_observation
            return ActionContract(
                id="contract:route-risk",
                intent="Delete A",
                affordance_id="target:delete:a",
                action="activate",
                backend="dom",
                environment_revision="env:route-risk",
                snapshot_id="snapshot:route-risk",
                page_revision="page:route-risk",
                locator={"selector": "#delete-a"},
                grounding_candidate=candidate,
            )

    contract = ActionContractBuilder(HighRiskRouteMaterializer()).build(  # type: ignore[arg-type]
        selection,
        catalog,
        task,
        StateKernel(task.task_id, task.objective),
        None,  # type: ignore[arg-type]
        observation,
    )

    assert contract.action_authority_proof.risk == RiskLevel.HIGH
    assert contract.risk == RiskLevel.HIGH
    with pytest.raises(ValueError, match="cannot be lower"):
        replace(contract, risk=RiskLevel.MEDIUM, contract_hash="")
    admission = ActionAdmissionService(TaskConstraintPolicy()).evaluate(
        contract,
        constraints={},
        capability_gate=CapabilityGate(),
        observation=Observation(
            "env:route-risk",
            snapshot_id="snapshot:route-risk",
            page_revision="page:route-risk",
        ),
        task_spec=task,
        canonical_observation=observation,
    )
    assert tuple(item.gate for item in admission.policy_results) == (
        AdmissionGate.TASK_AUTHORITY,
        AdmissionGate.CAPABILITY,
        AdmissionGate.APPROVAL,
    )
    assert admission.error == RuntimeErrorCode.APPROVAL_REQUIRED

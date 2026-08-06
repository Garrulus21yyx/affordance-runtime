from __future__ import annotations

import pytest

from affordance_runtime.action_choice_catalog import ActionChoiceCatalog, ActionChoiceCatalogBuilder
from affordance_runtime.action_contract_builder import ActionContractBuilder
from affordance_runtime.action_selection import ActionSelection
from affordance_runtime.active_step_scope import ActiveStepScope
from affordance_runtime.choice_contracts import ActionChoiceFailure
from affordance_runtime.contracts import ActionContract
from affordance_runtime.criteria import PredicateExpr, PredicateOperator, SubjectExpr
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.simplified_runtime_contracts import (
    ElementIntent,
    SourceReference,
    StepActivityStatus,
    StepSpec,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    OperationClass,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.unified_observation import UnifiedObservation, UnifiedObservationTarget
from affordance_runtime.verification.contracts import CriterionPolicy, SuccessExpression


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


def _effect_task(subject: str) -> TaskSpec:
    return TaskSpec(
        task_id="task:catalog-authority",
        revision=1,
        objective=f"Delete {subject}",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(
            (f"Delete {subject}",),
            OperationClass.REVERSIBLE_WRITE,
            "request:catalog-authority",
            (),
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
            ),
        ),
    )


def test_catalog_rejects_concrete_target_outside_exact_effect_authority() -> None:
    task = _effect_task("A")
    step = _effect_step("B")
    observation = _delete_observation("B")
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
    assert result.reason_code == "no_feasible_action_choice"


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
        effectful=True,
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

from dataclasses import replace
from types import SimpleNamespace

from affordance_runtime.actions import ActionBinding, ActionRisk, ActionSpaceBuilder
from affordance_runtime.actions.classification import classify_dom_action
from affordance_runtime.actions.effect_semantics import Reversibility
from affordance_runtime.execution import (
    ActionIntent,
    ActionResult,
    BoundActionRequest,
    CommittedEffect,
    DispatchStatus,
    ExecutionReceipt,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import ObservationSourceProfile, SemanticTarget
from tests.support.world import fused_world

SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _binding(*, reversibility: Reversibility) -> ActionBinding:
    return ActionBinding(
        binding_id=f"binding:{reversibility.value}",
        world_observation_id="observation:1",
        source_observation_id="observation:1",
        source_revision="revision:1",
        target_fingerprint="fingerprint:account:second",
        target_id="target:account:second",
        source_target_id="target:account:second",
        surface="dom",
        executor_id="dom",
        semantic_action="activate",
        primitive_action="click",
        effect_category="external",
        semantic_effects=("account_checked",),
        parameter_schema=SCHEMA,
        payload={"handle": "private"},
        risk=ActionRisk.HIGH,
        resource_ref="account:second",
        reversibility=reversibility,
    )


def _task() -> TaskGoal:
    return TaskGoal(
        "task:check-account",
        "Check the second account",
        allowed_effects=("account_checked",),
        risk_profile=RiskProfile.HIGH,
    )


def _world(*bindings: ActionBinding):
    return fused_world(
        "observation:1",
        (SemanticTarget("target:account:second", "button", "Second account"),),
        bindings=bindings,
        surface="dom",
        profile=ObservationSourceProfile.dom(),
    )


def test_effect_semantics_are_conserved_from_binding_to_committed_receipt() -> None:
    binding = _binding(reversibility=Reversibility.COMPENSATABLE)
    builder = ActionSpaceBuilder()
    option = builder.build(_task(), _world(binding)).options[0]
    selection = builder.admit(option, {})
    request = BoundActionRequest(
        "request:1",
        "context:1",
        "observation:1",
        ActionIntent("activate", "target:account:second"),
        selection,
        binding,
    )
    receipt = ExecutionReceipt(
        request,
        ActionResult("request:1", DispatchStatus.SENT, "dom", True),
        "observation:1",
        "observation:2",
    )

    committed = CommittedEffect.from_receipt(receipt, task_revision=2)

    assert option.resource_ref == selection.resource_ref == "account:second"
    assert option.reversibility is selection.reversibility is Reversibility.COMPENSATABLE
    assert committed.resource_ref == "account:second"
    assert committed.reversibility is Reversibility.COMPENSATABLE
    assert committed.semantic_effects == ("account_checked",)
    assert committed.dispatch_status is DispatchStatus.SENT


def test_conflicting_effect_semantics_are_not_merged_into_one_action() -> None:
    compensatable = _binding(reversibility=Reversibility.COMPENSATABLE)
    irreversible = replace(
        compensatable,
        binding_id="binding:irreversible",
        reversibility=Reversibility.IRREVERSIBLE,
    )

    space = ActionSpaceBuilder().build(_task(), _world(compensatable, irreversible))

    assert space.options == ()
    assert len(space.issues) == 1
    assert space.issues[0].conflicting_contract_fields == ("reversibility",)


def test_page_metadata_cannot_downgrade_registered_irreversibility() -> None:
    affordance = SimpleNamespace(
        role="button",
        externality="",
        reversibility="reversible",
        operation_ref="payment.commit@v1",
        risk=None,
        risk_asserted=False,
        effect_class="",
    )

    classification = classify_dom_action(_task(), affordance, "activate")

    assert classification.reversibility is Reversibility.IRREVERSIBLE


def test_registered_reversibility_survives_without_page_metadata() -> None:
    affordance = SimpleNamespace(
        role="button",
        externality="",
        reversibility="",
        operation_ref="resource.share@v1",
        risk=None,
        risk_asserted=False,
        effect_class="",
    )

    classification = classify_dom_action(_task(), affordance, "activate")

    assert classification.reversibility is Reversibility.COMPENSATABLE

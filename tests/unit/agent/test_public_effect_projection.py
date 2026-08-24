from __future__ import annotations

import json
from dataclasses import replace
from itertools import product

import pytest

from affordance_runtime.actions import ActionBinder, ActionBinding, ActionSpaceBuilder
from affordance_runtime.agent.context.observation_delivery import (
    DeliveryContinuationCapability,
    InformationDeltaKind,
    ObservationDeliveryStore,
    PublicEffectProjector,
)
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.context.world_transition import (
    PublicChangeKind,
    WorldTransitionProjector,
)
from affordance_runtime.agent.decisions import (
    ContinueDeliveryResult,
    PublicEvidenceResult,
    SearchPageContentResult,
    SelectAction,
)
from affordance_runtime.agent.run_state import RunStatus, StepResult
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage, RuntimeFailure
from affordance_runtime.agent.tool_result_projection import project_committed_tool_return
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import (
    ActionResult,
    DispatchStatus,
    ExecutionCompletion,
    ExecutionReceipt,
    ExecutionReceiptBatch,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ObservationSourceProfile,
    ObservationStructureNode,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)
from tests.support.canonical_world import canonical_world


def _world(
    observation_id: str,
    *,
    target_id: str = "target:item",
    fact_values: tuple[str, ...] = ("one",),
    state_value: str = "ready",
    extra_target: bool = False,
):
    source_id = f"browsergym-observation:{observation_id}:987654"
    target = SemanticTarget(target_id, "button", "Go", {"status": state_value})
    targets = (
        target,
        *( (SemanticTarget(f"extra:{observation_id}", "button", "Extra"),) if extra_target else () ),
    )
    child_ids = (
        f"button:{observation_id}",
        *((f"extra:{observation_id}",) if extra_target else ()),
    )
    source = SurfaceObservation(
        source_id,
        "browser",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        targets,
        tuple(
            StateFact(f"fact:{observation_id}:{index}", target_id, "value", value, source_id)
            for index, value in enumerate(fact_values)
        ),
        bindings=(
            ActionBinding(
                f"binding:{observation_id}",
                source_id,
                source_id,
                f"revision:{observation_id}",
                f"fingerprint:{observation_id}",
                target_id,
                target_id,
                "browser",
                "fixture",
                "activate",
                "click",
                "interaction",
                (),
                {"type": "object", "properties": {}, "additionalProperties": False},
                {"selector": "#private"},
            ),
        ),
        structure=(
            ObservationStructureNode(
                f"root:{observation_id}",
                "document",
                "Page",
                child_structure_ids=child_ids,
            ),
            ObservationStructureNode(
                f"button:{observation_id}",
                "button",
                "Go",
                parent_structure_id=f"root:{observation_id}",
                semantic_target_id=target_id,
            ),
            *(
                (ObservationStructureNode(
                    f"extra:{observation_id}",
                    "button",
                    "Extra",
                    parent_structure_id=f"root:{observation_id}",
                    semantic_target_id=f"extra:{observation_id}",
                ),)
                if extra_target
                else ()
            ),
        ),
        structure_total_count=2 + int(extra_target),
    )
    result = WorldFusion().fuse((source,))
    assert result.observation is not None
    return replace(
        result.observation,
        observation_id=observation_id,
        bindings=tuple(
            replace(item, world_observation_id=observation_id)
            for item in result.observation.bindings
        ),
    )


def _project(before, after):
    delta = WorldTransitionProjector().project(before, after)
    inventory = PublicEffectProjector().project(
        delta,
        canonical_world(before),
        canonical_world(after),
    )
    return delta, inventory


def _external_step(before, after):
    task = TaskGoal(
        "task:effect",
        "Activate the control",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )
    option = ActionSpaceBuilder().build(task, before).options[0]
    selection = ActionSpaceBuilder().admit(option, {})
    request = ActionBinder().bind(selection, before, "context:effect", tool_call_id="call:effect")
    result = ActionResult(request.request_id, DispatchStatus.SENT, "fixture", True)
    return StepResult(
        SelectAction("context:effect", option.action_id, tool_call_id="call:effect"),
        before,
        after,
        TaskEvaluation(
            "task:effect",
            after.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "public effect fixture",
        ),
        execution_receipts=ExecutionReceiptBatch(
            (ExecutionReceipt(request, result, before.observation_id, after.observation_id),),
            ExecutionCompletion.COMPLETE,
        ),
        feedback="action_dispatched",
        before_public_world=canonical_world(before),
        after_public_world=canonical_world(after),
    )


def _two_fact_world(observation_id: str, values: tuple[str, str]):
    source_id = f"source:{observation_id}"
    targets = tuple(SemanticTarget(f"target:{observation_id}:{index}", "status", "Item") for index in range(2))
    source = SurfaceObservation(
        source_id,
        "browser",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        targets,
        tuple(
            StateFact(f"fact:{observation_id}:{index}", target.target_id, "value", value, source_id)
            for index, (target, value) in enumerate(zip(targets, values, strict=True))
        ),
        structure=(
            ObservationStructureNode("root", "document", "Page", child_structure_ids=("a", "b")),
            ObservationStructureNode("a", "status", "Item", parent_structure_id="root", semantic_target_id=targets[0].target_id),
            ObservationStructureNode("b", "status", "Item", parent_structure_id="root", semantic_target_id=targets[1].target_id),
        ),
        structure_total_count=3,
    )
    result = WorldFusion().fuse((source,))
    assert result.observation is not None
    return replace(result.observation, observation_id=observation_id)


def _ambiguous_index(world):
    index = WorldDeliveryIndex.from_observation(world)
    contexts = {
        target_id: replace(context, public_order=0)
        for target_id, context in index.target_contexts.items()
    }
    return replace(index, target_contexts=contexts)


def test_full_identity_remount_with_equal_public_semantics_has_no_effect_atoms() -> None:
    before = _world("world:before", target_id="private:old")
    after = _world("world:after-with-a-much-longer-id", target_id="private:new")

    delta, inventory = _project(before, after)

    assert canonical_world(before).public_document_signature == (
        canonical_world(after).public_document_signature
    )
    assert delta.target_changes or delta.fact_changes
    assert inventory.atoms == ()
    assert inventory.transition != "new_document"
    assert inventory.changed_target_slot_keys == ()
    assert inventory.raw_delta_lineage


@pytest.mark.parametrize(
    ("before_values", "after_values", "expected"),
    [
        (("same",), ("same", "same"), PublicChangeKind.ADDED),
        (("same", "same"), ("same",), PublicChangeKind.REMOVED),
    ],
)
def test_duplicate_public_fact_multiplicity_changes_by_exactly_one_atom(
    before_values: tuple[str, ...],
    after_values: tuple[str, ...],
    expected: PublicChangeKind,
) -> None:
    _delta, inventory = _project(
        _world("world:before", fact_values=before_values),
        _world("world:after", fact_values=after_values),
    )

    fact_atoms = tuple(item for item in inventory.atoms if item.atom_kind == "fact")
    assert len(fact_atoms) == 1
    assert fact_atoms[0].change is expected


def test_stable_slot_single_value_change_is_one_modified_atom() -> None:
    _delta, inventory = _project(
        _world("world:before", fact_values=("old",)),
        _world("world:after", fact_values=("new",)),
    )

    fact_atoms = tuple(item for item in inventory.atoms if item.atom_kind == "fact")
    assert [(item.change, item.exact_value) for item in fact_atoms] == [
        (PublicChangeKind.MODIFIED, "new")
    ]


def test_one_public_target_add_and_remove_produce_exact_target_atom_and_tombstone() -> None:
    before = _world("world:before")
    after = _world("world:after", extra_target=True)

    _delta, added = _project(before, after)
    _delta, removed = _project(after, before)
    added_targets = tuple(item for item in added.atoms if item.atom_kind == "target")
    removed_targets = tuple(item for item in removed.atoms if item.atom_kind == "target")

    assert len(added_targets) == 1
    assert added_targets[0].change is PublicChangeKind.ADDED
    assert len(removed_targets) == 1
    assert removed_targets[0].change is PublicChangeKind.REMOVED
    assert not removed_targets[0].subject_id


def test_ambiguous_same_slot_pairing_remains_adds_and_removed_tombstones() -> None:
    before = _two_fact_world("world:before", ("old-a", "old-b"))
    after = _two_fact_world("world:after", ("new-a", "new-b"))
    delta = WorldTransitionProjector().project(before, after)
    inventory = PublicEffectProjector().project(
        delta,
        canonical_world(before, index=_ambiguous_index(before)),
        canonical_world(after, index=_ambiguous_index(after)),
    )

    fact_atoms = tuple(item for item in inventory.atoms if item.atom_kind == "fact")
    assert [item.change for item in fact_atoms].count(PublicChangeKind.ADDED) == 2
    assert [item.change for item in fact_atoms].count(PublicChangeKind.REMOVED) == 2
    assert all(not item.subject_id for item in fact_atoms if item.change is PublicChangeKind.REMOVED)


def test_public_effect_is_id_permutation_invariant_but_raw_lineage_remains_private() -> None:
    before_a = _world("world:a", target_id="private:short", fact_values=("old",))
    after_a = _world("world:b", target_id="private:next", fact_values=("new",))
    before_b = _world("world:before-with-long-id", target_id="private:xxxxxxxx", fact_values=("old",))
    after_b = _world("world:after-with-long-id", target_id="private:yyyyyyyy", fact_values=("new",))

    _delta_a, effect_a = _project(before_a, after_a)
    _delta_b, effect_b = _project(before_b, after_b)

    assert effect_a.inventory_id == effect_b.inventory_id
    assert tuple(item.public_value for item in effect_a.atoms) == tuple(
        item.public_value for item in effect_b.atoms
    )
    assert effect_a.raw_delta_lineage != effect_b.raw_delta_lineage
    public = json.dumps(to_json_compatible(tuple(item.public_value for item in effect_a.atoms)))
    assert "browsergym-observation:" not in public
    assert "private:" not in public


def test_latest_external_effect_survives_local_operations_and_supersedes_once() -> None:
    before = _world("world:before", state_value="before")
    after = _world("world:after", state_value="after")
    final = _world("world:final", state_value="final")
    store = ObservationDeliveryStore().reduce(_external_step(before, after), step_index=1).next_store
    assert store.latest_effect is not None
    first_identity = store.latest_effect.inventory.inventory_id

    for operation in ("read_region", "search_page_content", "find_controls"):
        local = StepResult(
            SearchPageContentResult(
                "context:effect",
                operation,
                {"query": "fixture"},
                PublicEvidenceResult.from_value(
                    {"kind": "NoMatches", "items": ()},
                    source_scope="current",
                ),
            ),
            after,
            after,
            TaskEvaluation(
                "task:effect",
                after.observation_id,
                TaskEvaluationStatus.INCOMPLETE,
                "local effect-preservation fixture",
            ),
            feedback="local_tool_result",
        )
        next_store = store.reduce(local, step_index=2).next_store
        assert next_store.latest_effect is store.latest_effect
        assert next_store.latest_effect.inventory.inventory_id == first_identity

    replaced = store.reduce(_external_step(after, final), step_index=3).next_store
    assert replaced.latest_effect is not None
    assert replaced.latest_effect.step_index == 3
    assert replaced.latest_effect.inventory.inventory_id != first_identity
    assert replaced.active_read is None


@pytest.mark.parametrize(
    ("evidence_count", "admitted_count", "failed"),
    tuple(product((0, 2), (None, 0, 1), (False, True))),
)
def test_committed_step_reducer_composes_effect_evidence_continuation_and_failure(
    evidence_count: int,
    admitted_count: int | None,
    failed: bool,
) -> None:
    """Adding any legal transition leaves every independent transition conserved."""

    before = _world("world:matrix-before", state_value="before")
    current = _world("world:matrix-current", state_value="after")
    store = ObservationDeliveryStore().reduce(
        _external_step(before, current), step_index=1
    ).next_store
    assert store.latest_effect is not None
    effect_identity = store.latest_effect.inventory.inventory_id
    evidence = PublicEvidenceResult.from_value(
        {
            "kind": "Page",
            "items": tuple(
                {"ordinal": index, "nested": {"text": f"完整🙂-{index}"}}
                for index in range(evidence_count)
            ),
        },
        source_scope="matrix",
    )
    capability = (
        DeliveryContinuationCapability(
            "query",
            True,
            admitted_count,
            3,
            current.observation_id,
            "actions:matrix",
            "result:matrix",
            "order:matrix",
            0,
            "explicit_query",
        )
        if admitted_count is not None
        else None
    )
    failure = (
        RuntimeFailure(FailureStage.SESSION, FailureKind.CALL_FAILED, "matrix.failure")
        if failed
        else None
    )
    decision = ContinueDeliveryResult(
        "context:matrix",
        "action_results_next_page",
        {"scope": "query"},
        evidence,
        "call:matrix",
        continuation=capability,
    )
    step = StepResult(
        decision,
        current,
        current,
        TaskEvaluation(
            "task:effect",
            current.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "composition matrix",
        ),
        status_after=RunStatus.FAILED if failed else RunStatus.RUNNING,
        runtime_failure=failure,
        feedback="local_tool_result",
    )

    transition = store.reduce(step, step_index=2)

    assert transition.next_store.latest_effect is store.latest_effect
    assert transition.next_store.latest_effect.inventory.inventory_id == effect_identity
    assert transition.runtime_failure is failure
    assert transition.information_delta is not None
    assert transition.information_delta.kind is (
        InformationDeltaKind.NEW_INFORMATION
        if evidence_count
        else InformationDeltaKind.NO_MATCHES
    )
    inventory = transition.next_store.public_result_inventory
    assert (() if inventory is None else inventory.records) == tuple(
        transition.next_store.local_deliveries[-1].records
    )
    progress = next(
        (item for item in transition.next_store.cursor_progress if item.scope == "query"),
        None,
    )
    assert (None if progress is None else progress.offset) == admitted_count
    tool_return = project_committed_tool_return(step)
    assert tool_return is not None
    assert tuple(tool_return["items"]) == evidence.records
    physical_result = json.dumps(to_json_compatible(tool_return), ensure_ascii=False)
    assert "actions:matrix" not in physical_result
    assert "result:matrix" not in physical_result
    assert "order:matrix" not in physical_result

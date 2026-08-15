from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field, replace

from PIL import Image
from test_agent_loop import ScriptedPolicy, _loop, _world
from test_agent_loop import _task as shared_task

from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus
from affordance_runtime.model_boundary.budgets import BoundedSection, ContextProjectionBudget
from affordance_runtime.model_boundary.contracts import AgentActionOptionView, AgentActionPageView
from affordance_runtime.model_boundary.grounding_projection import GroundingProjection
from affordance_runtime.model_boundary.world_projection import project_model_world
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    AcquisitionStatus,
    ActionBinder,
    ActionBinding,
    ActionRisk,
    ActionSpaceBuilder,
    CoverageState,
    EntityCorrespondence,
    ObservationGroundingRegion,
    ObservationMedia,
    ObservationOffer,
    ObservationOrchestrator,
    ObservationRequestKind,
    ObservationSourceProfile,
    RouteSelectionCode,
    RouteSelector,
    SemanticTarget,
    SourceAcquisitionStatus,
    StateFact,
    SurfaceObservation,
    WorldFusion,
    WorldObservationRequest,
)
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


def _task() -> TaskGoal:
    return TaskGoal(
        "task:any-name", "Enable it", allowed_effects=("enabled",), risk_profile=RiskProfile.LOW,
    )


def _source(
    surface: str,
    *,
    profile: ObservationSourceProfile | None = None,
    local_id: str = "target",
    canonical_id: str = "",
    value: object = False,
    confidence: float = 1.0,
    media: tuple[ObservationMedia, ...] = (),
    acquisition_root_id: str = "root:shared",
) -> SurfaceObservation:
    observation_id = f"{surface}:obs"
    revision = f"{surface}:rev"
    binding = ActionBinding(
        f"{surface}:binding",
        observation_id,
        observation_id,
        revision,
        f"{surface}:fingerprint",
        local_id,
        local_id,
        surface,
        surface,
        "activate",
        "click",
        "local_reversible",
        ("enabled",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"private": surface},
        confidence=confidence,
        risk=ActionRisk.LOW,
    )
    return SurfaceObservation(
        observation_id,
        surface,
        revision,
        profile or ObservationSourceProfile.dom(),
        (SemanticTarget(local_id, "button", "Enable"),),
        (StateFact(f"{surface}:enabled", local_id, "enabled", value, observation_id),),
        (binding,),
        CoverageState.COMPLETE,
        media=media,
        acquisition_root_id=acquisition_root_id,
        correspondences=(EntityCorrespondence(local_id, canonical_id),) if canonical_id else (),
        visual_only_target_ids=(local_id,)
        if (profile or ObservationSourceProfile.dom()).modality.value == "visual" and not canonical_id
        else (),
    )


def test_selection_skips_expensive_visual_until_typed_visual_need() -> None:
    selector = ObservationOrchestrator()
    offers = (
        ObservationOffer("dom", "structural", "structural", "low"),
        ObservationOffer("visual", "visual", "weak", "high"),
    )

    ordinary = selector.select(
        offers, WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, "ordinary"),
    )
    visual = selector.select(
        offers,
        WorldObservationRequest(
            ObservationRequestKind.POLICY_REQUEST, "spatial gap", modality="visual",
        ),
    )

    assert [item.source for item in ordinary.plan.selections] == ["dom"]  # type: ignore[union-attr]
    assert [item.source for item in visual.plan.selections] == ["dom", "visual"]  # type: ignore[union-attr]
    assert visual.plan.selections[1].requirement.value == "optional"  # type: ignore[union-attr]


def test_environment_state_is_required_and_structural_world_is_augmented() -> None:
    selector = ObservationOrchestrator()
    offers = (
        ObservationOffer("dom", "structural", "structural", "low"),
        ObservationOffer("wot", "environment_state", "authoritative", "medium"),
    )

    selected = selector.select(
        offers,
        WorldObservationRequest(
            ObservationRequestKind.POLICY_REQUEST,
            "verify device state",
            modality="environment_state",
            required_assurance="authoritative",
        ),
    )

    assert selected.plan is not None
    assert [item.source for item in selected.plan.selections] == ["wot", "dom"]
    assert [item.requirement.value for item in selected.plan.selections] == [
        "required",
        "optional",
    ]


@dataclass
class OfferedAdapter:
    surface: str
    offer: ObservationOffer
    observation: SurfaceObservation | None
    reset_calls: int = 0
    observe_calls: int = 0
    prepared: bool = False

    @property
    def observation_offers(self):
        return (self.offer,)

    def prepare(self, task):
        del task
        self.prepared = True

    async def reset(self, task):
        del task
        self.reset_calls += 1

    async def observe(self, reason):
        del reason
        self.observe_calls += 1
        if self.observation is None:
            raise RuntimeError("unavailable")
        return self.observation

    async def execute(self, request):
        return ActionResult(
            request.request_id, DispatchStatus.SENT, self.surface, True,
        )


def test_optional_source_failure_preserves_required_world_and_typed_gap() -> None:
    async def scenario() -> None:
        dom = OfferedAdapter(
            "dom", ObservationOffer("dom", "structural", "structural", "low"), _source("dom"),
        )
        visual = OfferedAdapter(
            "visual", ObservationOffer("visual", "visual", "weak", "high"), None,
        )
        environment = UnifiedWorldEnvironment((dom, visual))
        initial = await environment.reset(_task())
        assert dom.observe_calls == 1 and visual.observe_calls == 0
        assert [item.status for item in initial.source_results] == [
            SourceAcquisitionStatus.NOT_ACQUIRED,
            SourceAcquisitionStatus.ACQUIRED,
        ]
        acquired = await environment.capture(WorldObservationRequest(
            ObservationRequestKind.POLICY_REQUEST, "spatial gap", modality="visual",
        ))

        assert acquired.status is AcquisitionStatus.ACQUIRED
        assert acquired.reason_code == "world_acquired_with_optional_gap"
        assert acquired.observation is not None
        assert acquired.observation.coverage["visual"] is CoverageState.FAILED
        assert [item.status for item in acquired.source_results] == [
            SourceAcquisitionStatus.ACQUIRED,
            SourceAcquisitionStatus.FAILED,
        ]

    asyncio.run(scenario())


def test_post_action_reacquires_route_owner_and_prior_required_source() -> None:
    async def scenario() -> None:
        dom = OfferedAdapter(
            "dom", ObservationOffer("dom", "structural", "structural", "low"), _source("dom"),
        )
        visual = OfferedAdapter(
            "visual", ObservationOffer("visual", "visual", "weak", "high"),
            _source("visual", profile=ObservationSourceProfile.visual()),
        )
        environment = UnifiedWorldEnvironment((dom, visual))
        task = _task()
        await environment.reset(task)
        acquired = await environment.capture(WorldObservationRequest(
            ObservationRequestKind.POLICY_REQUEST, "spatial gap", modality="visual",
        ))
        assert acquired.observation is not None
        option = next(
            item for item in ActionSpaceBuilder().build(task, acquired.observation).options
            if any(
                binding.binding_id in item.eligible_binding_ids and binding.surface == "visual"
                for binding in acquired.observation.bindings
            )
        )
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(option, {}), acquired.observation, "context:test",
        )

        outcome = await environment.execute(request)

        assert outcome.result.dispatch_status is DispatchStatus.SENT
        assert outcome.post_acquisition.selection_plan is not None
        assert {
            (item.source, item.requirement.value)
            for item in outcome.post_acquisition.selection_plan.selections
        } == {("dom", "required"), ("visual", "required")}
        assert dom.observe_calls == 3 and visual.observe_calls == 2

    asyncio.run(scenario())


def test_fusion_merges_only_explicit_correspondence_and_conserves_provenance() -> None:
    left = _source(
        "dom", local_id="dom-target", canonical_id="entity:shared",
        acquisition_root_id="root:dom",
    )
    right = _source(
        "wot", profile=ObservationSourceProfile.wot(), local_id="wot-target",
        canonical_id="entity:shared", acquisition_root_id="root:wot",
    )
    result = WorldFusion().fuse((left, right))

    assert result.observation is not None
    assert [item.target_id for item in result.observation.targets] == ["entity:shared"]
    assert {item.target_id for item in result.observation.bindings} == {"entity:shared"}
    assert result.entity_provenance[0].source_refs == (
        ("dom", "dom-target"), ("wot", "wot-target"),
    )
    assert len(result.entity_provenance[0].acquisition_roots) == 2


def test_visual_correspondence_adds_non_overlapping_state_without_replacing_dom_identity() -> None:
    dom = _source(
        "dom",
        local_id="dom-target",
        canonical_id="entity:shared",
        acquisition_root_id="root:shared",
    )
    visual = replace(
        _source(
            "visual",
            profile=ObservationSourceProfile.visual(),
            local_id="visual-target",
            canonical_id="entity:shared",
            acquisition_root_id="root:shared",
        ),
        bindings=(),
        targets=(SemanticTarget(
            "visual-target",
            dom.targets[0].role,
            dom.targets[0].label,
            {"visually_selected": True},
        ),),
    )

    result = WorldFusion().fuse((dom, visual))

    assert result.observation is not None
    target = result.observation.targets[0]
    assert target.target_id == "entity:shared"
    assert target.state["visually_selected"] is True


def test_duplicate_labels_without_explicit_link_never_merge() -> None:
    result = WorldFusion().fuse((
        _source("dom", local_id="same"),
        _source("visual", profile=ObservationSourceProfile.visual(), local_id="same"),
    ))

    assert result.observation is not None
    assert len(result.observation.targets) == 2
    assert len({item.target_id for item in result.observation.targets}) == 2


def test_visual_coordinate_binding_requires_explicit_visual_only_classification() -> None:
    visual = replace(
        _source("visual", profile=ObservationSourceProfile.visual()),
        visual_only_target_ids=(),
    )

    result = WorldFusion().fuse((_source("dom"), visual))

    assert result.observation is None
    assert result.reason_code == "visual_binding_identity_unclassified"


def test_visual_coordinate_binding_requires_shared_structural_acquisition_root() -> None:
    visual = _source(
        "visual",
        profile=ObservationSourceProfile.visual(),
        acquisition_root_id="root:visual",
    )

    result = WorldFusion().fuse((
        _source("dom", acquisition_root_id="root:dom"),
        visual,
    ))

    assert result.observation is None
    assert result.reason_code == "visual_binding_requires_shared_acquisition"


def test_visual_coordinate_binding_cannot_bypass_missing_structural_root() -> None:
    result = WorldFusion().fuse((
        _source("dom", acquisition_root_id=""),
        _source("visual", profile=ObservationSourceProfile.visual()),
    ))

    assert result.observation is None
    assert result.reason_code == "visual_binding_requires_shared_acquisition"


def test_visual_correspondence_requires_shared_acquisition_without_coordinate_binding() -> None:
    visual = replace(
        _source(
            "visual",
            profile=ObservationSourceProfile.visual(),
            canonical_id="entity:shared",
            acquisition_root_id="root:visual",
        ),
        bindings=(),
    )

    result = WorldFusion().fuse((
        _source(
            "dom", local_id="dom-target", canonical_id="entity:shared",
            acquisition_root_id="root:dom",
        ),
        visual,
    ))

    assert result.observation is None
    assert result.reason_code == "visual_correspondence_requires_shared_acquisition"


def test_visual_correspondence_must_resolve_to_structural_identity() -> None:
    visual = replace(
        _source(
            "visual",
            profile=ObservationSourceProfile.visual(),
            canonical_id="entity:missing",
        ),
        bindings=(),
    )

    result = WorldFusion().fuse((_source("dom"), visual))

    assert result.observation is None
    assert result.reason_code == "visual_correspondence_target_unresolved"


def test_corresponded_visual_entity_cannot_retain_coordinate_binding() -> None:
    visual = _source(
        "visual",
        profile=ObservationSourceProfile.visual(),
        canonical_id="entity:shared",
    )

    result = WorldFusion().fuse((
        _source("dom", canonical_id="entity:shared"),
        visual,
    ))

    assert result.observation is None
    assert result.reason_code == "corresponded_visual_binding_forbidden"


def test_material_conflict_blocks_only_affected_action_option() -> None:
    conflicted = WorldFusion().fuse((
        _source("dom", local_id="dom", canonical_id="entity:shared", value=False),
        _source(
            "wot", profile=ObservationSourceProfile.wot(), local_id="wot",
            canonical_id="entity:shared", value=True,
        ),
    )).observation
    assert conflicted is not None and conflicted.conflicts

    action_space = ActionSpaceBuilder().build(_task(), conflicted)

    assert action_space.options == ()


def test_route_selector_is_deterministic_and_model_never_selects_private_route() -> None:
    world = WorldFusion().fuse((
        _source("dom", local_id="dom", canonical_id="entity:shared", confidence=0.8),
        _source(
            "wot", profile=ObservationSourceProfile.wot(), local_id="wot",
            canonical_id="entity:shared", confidence=0.9,
        ),
    )).observation
    assert world is not None
    option = ActionSpaceBuilder().build(_task(), world).options[0]
    selection = ActionSpaceBuilder().admit(option, {})

    selected = RouteSelector().select(selection, world)
    alternate = RouteSelector().select(
        selection, world, excluded_binding_ids=frozenset({selected.binding.binding_id}),  # type: ignore[union-attr]
    )

    assert selected.code is RouteSelectionCode.SELECTED
    assert selected.binding.surface == "wot"  # type: ignore[union-attr]
    assert alternate.binding.surface == "dom"  # type: ignore[union-attr]
    assert set(option.eligible_binding_ids) == {"dom:binding", "wot:binding"}


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="PNG")
    return output.getvalue()


def test_marked_truth_depends_only_on_media_selected_for_this_model_call() -> None:
    marked_media = ObservationMedia(
        "marked", "screenshot", "image/png", _png(),
        (ObservationGroundingRegion("target", (1, 1, 5, 5)),),
    )
    plain_media = ObservationMedia("plain", "screenshot", "image/png", _png())
    source = _source("dom", media=(marked_media, plain_media))
    world = WorldFusion().fuse((source,)).observation
    assert world is not None
    model_world = project_model_world(world, ContextProjectionBudget())
    option = AgentActionOptionView(
        "action", "activate", "target", "Enable", False, BoundedSection((), 0, False),
        {"type": "object", "properties": {}, "additionalProperties": False},
        "activate target", ("enabled",), ActionRisk.LOW, True,
    )
    actions = AgentActionPageView((option,), 1, 1, False, False)

    dropped = GroundingProjection().project(
        world, model_world, actions, selected_media_ids=("plain",),
    )
    emitted = GroundingProjection().project(
        world, model_world, actions, selected_media_ids=("marked",),
    )

    assert dropped.index.entities[0].marked is False
    assert emitted.index.entities[0].marked is True
    assert len(dropped.images) == len(emitted.images) == 1


@dataclass
class SharedCaptureAdapter(OfferedAdapter):
    group_observations: dict[str, SurfaceObservation] = field(default_factory=dict)
    group_calls: int = 0

    async def observe_group(self, reason, sources):
        del reason
        self.group_calls += 1
        return {source: self.group_observations[source] for source in sources}


def test_shared_acquisition_group_has_one_reset_owner_and_one_group_capture() -> None:
    async def scenario() -> None:
        group = "browser:shared"
        dom_observation = _source("dom")
        visual_observation = _source("visual", profile=ObservationSourceProfile.visual())
        dom = SharedCaptureAdapter(
            "dom", ObservationOffer("dom", "structural", "structural", "low", group),
            dom_observation, group_observations={"dom": dom_observation, "visual": visual_observation},
        )
        visual = OfferedAdapter(
            "visual", ObservationOffer("visual", "visual", "weak", "high", group),
            visual_observation,
        )
        environment = UnifiedWorldEnvironment((dom, visual))
        await environment.reset(_task())
        acquired = await environment.capture(WorldObservationRequest(
            ObservationRequestKind.POLICY_REQUEST, "spatial gap", modality="visual",
        ))

        assert acquired.status is AcquisitionStatus.ACQUIRED
        assert dom.group_calls == 1
        assert dom.reset_calls == 1 and visual.reset_calls == 0
        assert visual.prepared is True
        assert visual.observe_calls == 0

    asyncio.run(scenario())


def _equivalent_route_world(observation_id: str, enabled: bool):
    base = _world(observation_id, enabled)
    dom_binding = replace(base.bindings[0], confidence=0.8)
    wot_source_id = f"wot:{observation_id}"
    wot_binding = replace(
        base.bindings[0],
        binding_id=f"wot:binding:{observation_id}",
        source_observation_id=wot_source_id,
        source_revision=f"wot:revision:{observation_id}",
        surface="wot",
        executor_id="wot",
        confidence=0.9,
    )
    wot_source = SurfaceObservation(
        wot_source_id,
        "wot",
        f"wot:revision:{observation_id}",
        ObservationSourceProfile.wot(),
        base.targets,
        tuple(replace(item, source_id=wot_source_id) for item in base.facts),
        (wot_binding,),
    )
    return replace(
        base,
        bindings=(dom_binding, wot_binding),
        coverage={"dom": CoverageState.COMPLETE, "wot": CoverageState.COMPLETE},
        sources=(replace(base.sources[0], bindings=(dom_binding,)), wot_source),
    )


def test_not_sent_may_use_one_equivalent_alternate_and_dispatch_once() -> None:
    async def scenario() -> None:
        before = _equivalent_route_world("route-before", False)
        fresh = _equivalent_route_world("route-fresh", False)
        after = _equivalent_route_world("route-after", True)

        def execute(request, observation):
            del observation
            if request.binding.surface == "wot":
                return ActionResult(
                    request.request_id, DispatchStatus.NOT_SENT, "wot", False,
                    ActionError.CURRENTNESS_UNAVAILABLE,
                )
            return ActionResult(request.request_id, DispatchStatus.SENT, "dom", True)

        environment = StaticEnvironment(
            initial_observation=before,
            independent_observations=(fresh,),
            post_observations=(after,),
            execute_fn=execute,
        )
        result = await (_loop(ScriptedPolicy(["first"]))).run(
            environment, shared_task(),
        )

        assert result.status is AgentLoopStatus.DONE
        assert environment.execute_calls == 2
        assert [item.binding.surface for item in environment.executed_requests] == ["wot", "dom"]
        transition = result.control_transitions[0]
        assert len(transition.execution_attempts) == 2
        assert sum(
            item.dispatch_status is not DispatchStatus.NOT_SENT
            for item in transition.execution_attempts
        ) == 1

    asyncio.run(scenario())


def test_sent_unknown_closes_reroute_even_when_equivalent_route_exists() -> None:
    async def scenario() -> None:
        before = _equivalent_route_world("unknown-before", False)
        after = _equivalent_route_world("unknown-after", False)

        def execute(request, observation):
            del observation
            return ActionResult(
                request.request_id,
                DispatchStatus.SENT_UNKNOWN,
                request.binding.executor_id,
                False,
                ActionError.EXECUTION_FAILED,
            )

        environment = StaticEnvironment(
            initial_observation=before,
            post_observations=(after,),
            execute_fn=execute,
        )
        await (_loop(ScriptedPolicy(["first"]))).run(
            environment, shared_task(),
        )

        assert environment.execute_calls == 1
        assert [item.binding.surface for item in environment.executed_requests] == ["wot"]

    asyncio.run(scenario())

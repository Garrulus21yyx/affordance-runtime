from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import numpy as np

from affordance_runtime.actions import (
    ActionSpaceBuilder,
)
from affordance_runtime.agent import RequestObservation
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.model.policy.grounded_tool_catalog import (
    compile_grounded_tool_catalog,
    resolve_grounded_tool_call,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall
from affordance_runtime.surfaces.browsergym.semantics import PRIVATE_CONTROL_PROPERTIES_KEY
from affordance_runtime.surfaces.visual.disambiguation import (
    VisualCandidateDisambiguationRequest,
)
from affordance_runtime.surfaces.visual.grounding import (
    VisualGroundingPoint,
    VisualGroundingRequest,
    VisualRegion,
    VisualRegionProposalRequest,
)
from affordance_runtime.world import (
    ObservationAssurance,
    ObservationModality,
    ObservationNeed,
    ObservationPurpose,
    ObservationRequestKind,
    SourceAcquisitionStatus,
    WorldObservationRequest,
)
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    FakeBrowserGym,
    ax_node,
    open_surface,
    raw_observation,
)


@dataclass
class _Proposer:
    regions: list[VisualRegion]
    calls: list[VisualRegionProposalRequest] = field(default_factory=list)
    provider: str = "fixture"
    model: str = "fixture"
    prompt_version: str = "fixture-v1"

    def propose(self, request: VisualRegionProposalRequest) -> list[VisualRegion]:
        self.calls.append(request)
        return list(self.regions)


@dataclass
class _FailingProposer:
    provider: str = "fixture"
    model: str = "fixture"
    prompt_version: str = "fixture-v1"

    def propose(self, request: VisualRegionProposalRequest) -> list[VisualRegion]:
        del request
        raise RuntimeError("visual source unavailable")


@dataclass
class _Grounder:
    point: VisualGroundingPoint
    calls: list[VisualGroundingRequest] = field(default_factory=list)
    provider: str = "zhipu"
    model: str = "glm-fixture"
    prompt_version: str = "visual-grounder-v1"

    def ground(self, request: VisualGroundingRequest) -> VisualGroundingPoint:
        self.calls.append(request)
        return self.point


@dataclass
class _CandidateDisambiguator:
    selected_ref: str | None = "E1"
    calls: list[VisualCandidateDisambiguationRequest] = field(default_factory=list)
    provider: str = "fixture"
    model: str = "fixture"
    prompt_version: str = "fixture-v1"

    def choose(self, request: VisualCandidateDisambiguationRequest) -> str | None:
        self.calls.append(request)
        return self.selected_ref


def _raw(*, shade: int = 255):
    raw = raw_observation(goal="Click the visible target.")
    raw["screenshot"] = np.full((100, 200, 3), shade, dtype=np.uint8)
    return raw


def _open(
    fake: FakeBrowserGym,
    proposer: _Proposer,
    *,
    with_point: bool = True,
    point: tuple[float, float] | None = None,
):
    point_grounder = None
    if with_point:
        first = proposer.regions[0]
        x, y, width, height = first.bbox_xywh
        point_grounder = _Grounder(
            VisualGroundingPoint(
                point or (x + width / 2, y + height / 2),
                normalized=first.normalized,
            )
        )
    return open_surface(
        "browsergym/miniwob.click-button",
        7,
        gym_factory=lambda *_args, **_kwargs: fake,
        visual_region_proposer=proposer,
        visual_point_grounder=point_grounder,
    )


def _visual_request():
    return WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        "structural actions do not ground the visible target",
        (
            ObservationNeed(
                "agent:visual:current-world",
                ObservationPurpose.ENTITY_DISCOVERY,
                ("current_world",),
                ObservationModality.VISUAL,
                ObservationAssurance.WEAK,
            ),
        ),
    )


def _target_disambiguation_request() -> WorldObservationRequest:
    return WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        "the policy needs one current target",
        (
            ObservationNeed(
                "agent:visual:target",
                ObservationPurpose.TARGET_DISAMBIGUATION,
                ("current_world",),
                ObservationModality.VISUAL,
                ObservationAssurance.WEAK,
            ),
        ),
    )


def _candidate_raw(*boxes: tuple[int, int, int, int]) -> dict[str, object]:
    nodes = tuple(ax_node(f"button-{index}", "button", "Choice") for index in range(len(boxes)))
    raw = raw_observation(*nodes)
    raw["screenshot"] = np.full((100, 200, 3), 255, dtype=np.uint8)
    physical = raw[PRIVATE_CONTROL_PROPERTIES_KEY]
    assert isinstance(physical, dict)
    for index, bbox in enumerate(boxes):
        item = physical[f"button-{index}"]
        assert isinstance(item, dict)
        item["bbox"] = list(bbox)
    return raw


def test_disambiguation_candidates_are_current_viewport_scoped_and_clipped() -> None:
    async def scenario() -> None:
        raw = _candidate_raw((10, 10, 30, 20), (190, 30, 20, 20), (10, 1000, 30, 20))
        fake = FakeBrowserGym(raw)
        disambiguator = _CandidateDisambiguator()
        environment, task = open_surface(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: fake,
            visual_candidate_disambiguator=disambiguator,
        )
        try:
            await environment.reset(task)
            acquired = await environment.capture(_target_disambiguation_request())
        finally:
            await environment.close()

        assert acquired.status.value == "acquired"
        assert len(disambiguator.calls) == 1
        assert tuple(item.bbox for item in disambiguator.calls[0].candidates) == (
            (10, 10, 30, 20),
            (190, 30, 10, 20),
        )
        assert environment.visual_provider_failure_count == 0

    asyncio.run(scenario())


def test_insufficient_viewport_candidates_do_not_call_or_blame_provider() -> None:
    async def scenario() -> None:
        raw = _candidate_raw((10, 10, 30, 20), (10, 1000, 30, 20))
        fake = FakeBrowserGym(raw)
        disambiguator = _CandidateDisambiguator()
        environment, task = open_surface(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: fake,
            visual_candidate_disambiguator=disambiguator,
        )
        try:
            await environment.reset(task)
            acquired = await environment.capture(_target_disambiguation_request())
        finally:
            await environment.close()

        result = next(item for item in acquired.source_results if item.source == "browsergym_visual")
        assert result.status is SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE
        assert result.reason_code == "visual_candidate_set_unavailable"
        assert disambiguator.calls == []
        assert environment.visual_disambiguator_calls == 0
        assert environment.visual_provider_failure_count == 0

    asyncio.run(scenario())


def test_empty_structural_bindings_do_not_trigger_visual_without_typed_need() -> None:
    async def scenario() -> None:
        fake = FakeBrowserGym(_raw())
        proposer = _Proposer([VisualRegion((0.25, 0.2, 0.2, 0.3), "target", 0.9)])
        environment, task = _open(fake, proposer)
        try:
            initial = await environment.reset(task)
            assert initial.observation is not None
            assert initial.observation.bindings == ()
            assert len(proposer.calls) == 0
            assert environment.visual_proposer_calls == 0
            assert [(item.source, item.status) for item in initial.source_results] == [
                ("browsergym", SourceAcquisitionStatus.ACQUIRED),
                ("browsergym_visual", SourceAcquisitionStatus.NOT_ACQUIRED),
            ]
            assert {source.surface for source in initial.observation.sources} == {"browsergym"}

            acquired = await environment.capture(_visual_request())
            assert acquired.observation is not None
            assert fake.capture_count == 1
            assert len(proposer.calls) == 1
            assert {source.surface for source in acquired.observation.sources} == {
                "browsergym",
                "browsergym_visual",
            }
            assert acquired.observation.bindings == ()
            visual = next(source for source in acquired.observation.sources if source.surface == "browsergym_visual")
            assert len(visual.targets) == 1
            assert visual.bindings == ()
            assert environment.visual_point_grounder_calls == 0
            context = ContextBuilder().build(
                task,
                acquired.observation,
                ActionSpaceBuilder().build(task, acquired.observation),
                TaskEvaluation(
                    task.task_id,
                    acquired.observation.observation_id,
                    TaskEvaluationStatus.INCOMPLETE,
                    "ongoing",
                ),
                observation_capabilities=environment.observation_capabilities,
            )
            assert len(context.image_inputs) == 1
            assert sum(item.marked for item in context.grounding.entities) == 0
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_multi_purpose_visual_activation_reports_only_the_executed_purpose() -> None:
    async def scenario() -> None:
        fake = FakeBrowserGym(_raw())
        proposer = _Proposer([VisualRegion((0.25, 0.2, 0.2, 0.3), "target", 0.9)])
        environment, task = open_surface(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: fake,
            visual_region_proposer=proposer,
            marked_candidate_policy_available=True,
        )
        try:
            await environment.reset(task)
            acquisition = await environment.capture(
                WorldObservationRequest(
                    ObservationRequestKind.POLICY_REQUEST,
                    "two visual purposes",
                    (
                        ObservationNeed(
                            "need:disambiguate",
                            ObservationPurpose.TARGET_DISAMBIGUATION,
                            ("current_world",),
                            ObservationModality.VISUAL,
                            ObservationAssurance.WEAK,
                        ),
                        ObservationNeed(
                            "need:discover",
                            ObservationPurpose.ENTITY_DISCOVERY,
                            ("current_world",),
                            ObservationModality.VISUAL,
                            ObservationAssurance.WEAK,
                        ),
                    ),
                )
            )
        finally:
            await environment.close()

        visual = next(item for item in acquisition.source_results if item.source == "browsergym_visual")
        assert visual.status is SourceAcquisitionStatus.ACQUIRED
        assert visual.fulfilled_need_ids == ("need:disambiguate",)
        assert visual.unfulfilled_need_ids == ("need:discover",)
        assert proposer.calls == []

    asyncio.run(scenario())


def test_point_grounder_cannot_create_browsergym_mainline_action_authority() -> None:
    async def scenario() -> None:
        raw = _raw()
        fake = FakeBrowserGym(raw)
        fake.step_terminated = False
        fake.step_done = False
        proposer = _Proposer([VisualRegion((0.25, 0.2, 0.2, 0.3), "target", 0.9)])
        environment, task = _open(fake, proposer, point=(0.3, 0.3))
        try:
            await environment.reset(task)
            acquired = await environment.capture(_visual_request())
            assert acquired.observation is not None
            assert ActionSpaceBuilder().build(task, acquired.observation).options == ()
            assert acquired.observation.bindings == ()
            assert environment.visual_point_grounder_calls == 0
            assert isinstance(environment.visual_point_grounder, _Grounder)
            assert environment.visual_point_grounder.calls == []
            assert fake.actions == []
            assert environment.step_calls == 0
            assert environment.dom_action_calls == 0
            assert environment.structural_binding_dispatch_count == 0
            assert environment.visual_binding_dispatch_count == 0
            assert len(proposer.calls) == 1
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_changed_screenshot_does_not_make_observation_only_visual_entity_executable() -> None:
    async def scenario() -> None:
        initial = _raw()
        fake = FakeBrowserGym(initial, _raw(shade=1))
        proposer = _Proposer([VisualRegion((0.25, 0.2, 0.2, 0.3), "target", 0.9)])
        environment, task = _open(fake, proposer)
        try:
            await environment.reset(task)
            acquired = await environment.capture(_visual_request())
            assert acquired.observation is not None
            # Capture used ``post`` in the fixture; changing it cannot create an
            # executable route for an unmatched observation-only V-ref.
            fake.post = _raw(shade=2)
            assert acquired.observation.bindings == ()
            assert ActionSpaceBuilder().build(task, acquired.observation).options == ()
            assert environment.visual_point_grounder_calls == 0
            assert fake.actions == []
            assert environment.step_calls == 0
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_unsupported_visual_primitive_never_creates_action_authority() -> None:
    async def scenario() -> None:
        fake = FakeBrowserGym(_raw())
        proposer = _Proposer(
            [
                VisualRegion((0.25, 0.2, 0.2, 0.3), "target", 0.9, primitive_action="drag"),
            ]
        )
        environment, task = _open(fake, proposer, with_point=False)
        try:
            await environment.reset(task)
            acquired = await environment.capture(_visual_request())
            assert acquired.observation is not None
            assert len(acquired.observation.targets) == 1
            assert acquired.observation.bindings == ()
            assert ActionSpaceBuilder().build(task, acquired.observation).options == ()
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_visual_entity_facts_do_not_imply_point_action_authority() -> None:
    async def scenario() -> None:
        fake = FakeBrowserGym(_raw())
        proposer = _Proposer(
            [
                VisualRegion(
                    (0.25, 0.2, 0.2, 0.3),
                    "blue circle",
                    0.9,
                    role="shape",
                    primitive_action="observe_only",
                    state={"color": "blue", "shape": "circle", "row": 2, "column": 3},
                ),
                VisualRegion(
                    (0.55, 0.2, 0.2, 0.3),
                    "uncertain target",
                    0.49,
                    role="option",
                    state={"selected": False},
                ),
            ]
        )
        environment, task = _open(fake, proposer, with_point=False)
        try:
            await environment.reset(task)
            acquired = await environment.capture(_visual_request())
            assert acquired.observation is not None
            visual = next(source for source in acquired.observation.sources if source.surface == "browsergym_visual")
            assert len(visual.targets) == 2
            assert {(fact.predicate, fact.value) for fact in visual.facts} >= {
                ("color", "blue"),
                ("shape", "circle"),
                ("row", 2),
                ("column", 3),
                ("selected", False),
            }
            assert visual.bindings == ()
            assert ActionSpaceBuilder().build(task, acquired.observation).options == ()
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_required_visual_failure_returns_typed_failed_acquisition() -> None:
    async def scenario() -> None:
        fake = FakeBrowserGym(_raw())
        environment, task = open_surface(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: fake,
            visual_region_proposer=_FailingProposer(),
        )
        try:
            await environment.reset(task)
            acquired = await environment.capture(_visual_request())
            assert acquired.observation is None
            assert acquired.reason_code == "required_source_exhausted"
            result = next(item for item in acquired.source_results if item.source == "browsergym_visual")
            assert result.status is SourceAcquisitionStatus.FAILED
            assert result.reason_code == "region_proposal_provider_error"
            assert fake.capture_count == 1
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_visual_observation_capability_remains_explicitly_requestable() -> None:
    async def scenario() -> None:
        fake = FakeBrowserGym(_raw())
        proposer = _Proposer([VisualRegion((0.25, 0.2, 0.2, 0.3), "target", 0.9)])
        environment, task = _open(fake, proposer)
        try:
            initial = await environment.reset(task)
            assert initial.observation is not None
            space = ActionSpaceBuilder().build(task, initial.observation)
            context = ContextBuilder().build(
                task,
                initial.observation,
                space,
                TaskEvaluation(
                    task.task_id,
                    initial.observation.observation_id,
                    TaskEvaluationStatus.INCOMPLETE,
                    "ongoing",
                ),
                observation_capabilities=environment.observation_capabilities,
            )
            from affordance_runtime.model.policy.grounded_tool_contracts import GroundedToolPhase

            catalog = compile_grounded_tool_catalog(context, GroundedToolPhase.ACTION_SELECTION)
            assert "request_evidence" in {item.name for item in catalog.specs}
            decision = resolve_grounded_tool_call(
                catalog,
                ToolCall(
                    "request_evidence",
                    {
                        "purpose": "entity_discovery",
                        "subject": "current_world",
                    },
                ),
                expected_context_id=context.context_id,
            )
            from affordance_runtime.model.policy.grounded_tool_contracts import (
                GroundedActionResolution,
            )

            assert isinstance(decision, GroundedActionResolution)
            assert isinstance(decision.decision, RequestObservation)
            assert decision.decision.purpose == "entity_discovery"
            assert decision.decision.subject_id == "current_world"
        finally:
            await environment.close()

    asyncio.run(scenario())

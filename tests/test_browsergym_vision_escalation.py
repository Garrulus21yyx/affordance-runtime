from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import numpy as np
from browsergym_adapter_support import FakeBrowserGym, ax_node, raw_observation

from affordance_runtime.benchmarks.external_smoke.browsergym_environment import (
    BrowserGymMiniWobEnvironment,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
)
from affordance_runtime.execution import DispatchStatus
from affordance_runtime.model_port import StructuredModelError
from affordance_runtime.visual_disambiguation import VisualCandidateDisambiguationRequest
from affordance_runtime.visual_grounding import (
    VisualGroundingPoint,
    VisualGroundingRequest,
    VisualRegion,
    VisualRegionProposalRequest,
)
from affordance_runtime.world import (
    ActionSpaceBuilder,
    ObservationRequestKind,
    SourceAcquisitionStatus,
    VisionEscalationMode,
    VisionEvidenceNeed,
    WorldObservationRequest,
)
from affordance_runtime.world.binder import ActionBinder


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
class _Disambiguator:
    selected_ref: str | None
    calls: list[VisualCandidateDisambiguationRequest] = field(default_factory=list)
    provider: str = "fixture"
    model: str = "fixture"
    prompt_version: str = "visual-e-ref-choice-v1"

    def choose(self, request: VisualCandidateDisambiguationRequest) -> str | None:
        self.calls.append(request)
        return self.selected_ref


def _raw_with_buttons(
    *buttons: tuple[str, str, tuple[int, int, int, int]],
    goal: str = "Click the requested target.",
):
    nodes = tuple(ax_node(bid, "button", label) for bid, label, _bbox in buttons)
    raw = raw_observation(*nodes, goal=goal)
    raw["screenshot"] = np.full((100, 200, 3), 255, dtype=np.uint8)
    physical = raw[PRIVATE_CONTROL_PROPERTIES_KEY]
    for bid, _label, bbox in buttons:
        physical[bid]["bbox"] = list(bbox)
    return raw


def _open(
    fake: FakeBrowserGym,
    proposer: _Proposer,
    *,
    disambiguator: _Disambiguator | None = None,
):
    first = proposer.regions[0]
    x, y, width, height = first.bbox_xywh
    grounder = _Grounder(VisualGroundingPoint(
        (x + width / 2, y + height / 2),
        normalized=first.normalized,
    ))
    return BrowserGymMiniWobEnvironment.open(
        "browsergym/miniwob.click-button",
        7,
        gym_factory=lambda *_args, **_kwargs: fake,
        visual_region_proposer=proposer,
        visual_point_grounder=grounder,
        visual_candidate_disambiguator=disambiguator,
    )


def _visual_request() -> WorldObservationRequest:
    return WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        "current structured evidence needs visual assistance",
        subject_id="current_world",
        modality="visual",
        required_assurance="weak",
    )


def test_provider_presence_does_not_trigger_vision_when_dom_binding_is_sufficient() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(("okay", "Okay", (50, 20, 40, 30)))
        proposer = _Proposer([VisualRegion((0.25, 0.2, 0.2, 0.3), "Okay", 0.9)])
        environment, task = _open(FakeBrowserGym(raw), proposer)
        try:
            initial = await environment.reset(task)
            assert initial.observation is not None
            assert proposer.calls == []
            assert environment.last_visual_escalation is not None
            assert environment.last_visual_escalation.mode is VisionEscalationMode.SKIP
            assert [item.status for item in initial.source_results] == [
                SourceAcquisitionStatus.ACQUIRED,
                SourceAcquisitionStatus.NOT_ACQUIRED,
            ]
            assert {item.surface for item in initial.observation.sources} == {"browsergym"}
            assert len(initial.observation.bindings) == 1
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_visual_selection_is_recomputed_after_action_instead_of_sticking() -> None:
    async def scenario() -> None:
        initial = raw_observation(goal="Click the visible target.")
        initial["screenshot"] = np.full((100, 200, 3), 255, dtype=np.uint8)
        post = _raw_with_buttons(("continue", "Continue", (20, 20, 50, 30)))
        fake = FakeBrowserGym(initial, post)
        fake.step_terminated = False
        fake.step_done = False
        proposer = _Proposer([VisualRegion((0.25, 0.2, 0.2, 0.3), "target", 0.9)])
        environment, task = _open(fake, proposer)
        try:
            acquired = await environment.reset(task)
            assert acquired.observation is not None
            assert len(proposer.calls) == 1
            assert isinstance(environment.visual_point_grounder, _Grounder)
            assert "next atomic interaction" in environment.visual_point_grounder.calls[0].instruction
            assert "hidden behind a menu" in environment.visual_point_grounder.calls[0].instruction
            space = ActionSpaceBuilder().build(task, acquired.observation)
            request = ActionBinder().bind(
                ActionSpaceBuilder().admit(space.options[0], {}),
                acquired.observation,
                "context:visual",
            )

            outcome = await environment.execute(request)

            assert outcome.result.dispatch_status is DispatchStatus.SENT
            assert outcome.post_acquisition.observation is not None
            assert len(proposer.calls) == 1
            assert environment.last_visual_escalation is not None
            assert environment.last_visual_escalation.mode is VisionEscalationMode.SKIP
            assert {item.surface for item in outcome.post_acquisition.observation.sources} == {
                "browsergym"
            }
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_multi_target_visual_selection_is_typed_as_next_matching_entity() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(
            ("left", "", (20, 20, 40, 30)),
            ("right", "", (120, 20, 40, 30)),
            goal="Click all the grey shades.",
        )
        proposer = _Proposer([VisualRegion((0.1, 0.2, 0.2, 0.3), "unused", 0.9)])
        disambiguator = _Disambiguator("E1")
        environment, task = _open(FakeBrowserGym(raw), proposer, disambiguator=disambiguator)
        try:
            acquired = await environment.reset(task)
            assert acquired.observation is not None
            assert environment.last_visual_escalation is not None
            assert environment.last_visual_escalation.evidence_need is VisionEvidenceNeed.NEXT_MATCHING_TARGET
            assert disambiguator.calls[0].evidence_need is VisionEvidenceNeed.NEXT_MATCHING_TARGET
            assert len(acquired.observation.bindings) == 1
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_visual_value_task_stays_with_screenshot_policy_instead_of_e_ref() -> None:
    async def scenario() -> None:
        raw = raw_observation(
            ax_node("answer", "textbox", ""),
            ax_node("submit", "button", "Submit"),
            goal="Count the shapes and enter the total number.",
        )
        raw["screenshot"] = np.full((100, 200, 3), 255, dtype=np.uint8)
        proposer = _Proposer([VisualRegion((0.1, 0.2, 0.2, 0.3), "unused", 0.9)])
        disambiguator = _Disambiguator("E1")
        environment, task = _open(FakeBrowserGym(raw), proposer, disambiguator=disambiguator)
        try:
            acquired = await environment.reset(task)
            assert acquired.observation is not None
            assert environment.last_visual_escalation is not None
            assert environment.last_visual_escalation.mode is VisionEscalationMode.SKIP
            assert environment.last_visual_escalation.evidence_need is VisionEvidenceNeed.VISUAL_VALUE_REASONING
            assert disambiguator.calls == []
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_provider_validation_failure_is_retained_as_typed_diagnostic() -> None:
    @dataclass
    class FailingGrounder:
        provider: str = "fixture"
        model: str = "fixture"
        prompt_version: str = "fixture"

        def ground(self, request: VisualGroundingRequest) -> VisualGroundingPoint:
            del request
            raise StructuredModelError("invalid point")

    async def scenario() -> None:
        raw = raw_observation(goal="Click the visible target.")
        raw["screenshot"] = np.full((100, 200, 3), 255, dtype=np.uint8)
        environment, task = BrowserGymMiniWobEnvironment.open(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: FakeBrowserGym(raw),
            visual_point_grounder=FailingGrounder(),
        )
        try:
            acquired = await environment.reset(task)
            assert acquired.observation is not None
            assert environment.visual_provider_failure_count == 1
            assert environment.visual_provider_structured_output_failure_count == 1
            assert environment.visual_point_grounding_failure_count == 1
            failure = environment.visual_provider_failures[0]
            assert failure.exception_class == "StructuredModelError"
            assert failure.reason_code == "point_grounding_structured_output"
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_same_frame_visual_region_merges_into_dom_identity_without_coordinate_binding() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(("okay", "Okay", (50, 20, 40, 30)))
        proposer = _Proposer([
            VisualRegion((0.25, 0.2, 0.2, 0.3), "red Okay button", 0.9),
        ])
        environment, task = _open(FakeBrowserGym(raw), proposer)
        try:
            await environment.reset(task)
            acquired = await environment.capture(_visual_request())
            assert acquired.observation is not None
            visual = next(
                item for item in acquired.observation.sources
                if item.surface == "browsergym_visual"
            )
            assert len(visual.correspondences) == 1
            assert len(acquired.observation.targets) == 1
            assert [item.surface for item in acquired.observation.bindings] == ["browsergym"]
            assert environment.visual_binding_acquired_count == 0
            assert environment.visual_correspondence_matched_count == 1
            space = ActionSpaceBuilder().build(task, acquired.observation)
            assert len(space.options) == 1
            assert len(space.options[0].eligible_binding_ids) == 1
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_only_visual_region_without_dom_correspondence_gets_coordinate_binding() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(("okay", "Okay", (0, 0, 20, 20)))
        proposer = _Proposer([
            VisualRegion((0.5, 0.5, 0.2, 0.2), "canvas-only dot", 0.9, role="shape"),
        ])
        environment, task = _open(FakeBrowserGym(raw), proposer)
        try:
            await environment.reset(task)
            acquired = await environment.capture(_visual_request())
            assert acquired.observation is not None
            assert {item.surface for item in acquired.observation.bindings} == {
                "browsergym",
                "browsergym_visual",
            }
            assert environment.visual_binding_acquired_count == 1
            assert environment.visual_correspondence_unmatched_count == 1
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_overlapping_multiple_dom_candidates_is_ambiguous_and_non_coordinate() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(
            ("left", "Target left", (50, 20, 40, 30)),
            ("right", "Target right", (50, 20, 40, 30)),
        )
        proposer = _Proposer([VisualRegion((0.25, 0.2, 0.2, 0.3), "Target", 0.9)])
        environment, task = _open(FakeBrowserGym(raw), proposer)
        try:
            await environment.reset(task)
            acquired = await environment.capture(_visual_request())
            assert acquired.observation is not None
            assert [item.surface for item in acquired.observation.bindings] == [
                "browsergym",
                "browsergym",
            ]
            assert environment.visual_binding_acquired_count == 0
            assert environment.visual_correspondence_ambiguous_count == 1
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_overlapping_semantic_conflict_is_non_coordinate() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(("okay", "Okay", (50, 20, 40, 30)))
        proposer = _Proposer([
            VisualRegion(
                (0.25, 0.2, 0.2, 0.3),
                "decorative paragraph",
                0.9,
                role="text",
            ),
        ])
        environment, task = _open(FakeBrowserGym(raw), proposer)
        try:
            await environment.reset(task)
            acquired = await environment.capture(_visual_request())
            assert acquired.observation is not None
            assert [item.surface for item in acquired.observation.bindings] == ["browsergym"]
            assert environment.visual_binding_acquired_count == 0
            assert environment.visual_correspondence_conflict_count == 1
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_ambiguous_dom_candidates_use_e_ref_disambiguation_without_point_authority() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(
            ("left", "Save", (20, 20, 40, 30)),
            ("right", "Save", (120, 20, 40, 30)),
        )
        proposer = _Proposer([VisualRegion((0.1, 0.2, 0.2, 0.3), "unused", 0.9)])
        disambiguator = _Disambiguator("E2")
        environment, task = _open(
            FakeBrowserGym(raw),
            proposer,
            disambiguator=disambiguator,
        )
        try:
            acquired = await environment.reset(task)
            assert acquired.observation is not None
            assert environment.last_visual_escalation is not None
            assert (
                environment.last_visual_escalation.mode
                is VisionEscalationMode.VERIFY_STRUCTURED_CANDIDATES
            )
            assert len(disambiguator.calls) == 1
            assert proposer.calls == []
            assert environment.visual_point_grounder_calls == 0
            selected_facts = [
                fact for fact in acquired.observation.facts
                if fact.predicate == "visually_selected" and fact.value is True
            ]
            assert len(selected_facts) == 1
            assert [item.surface for item in acquired.observation.bindings] == ["browsergym"]
            assert acquired.observation.bindings[0].target_id == selected_facts[0].subject_id
            assert selected_facts[0].subject_id in {
                binding.target_id for binding in acquired.observation.bindings
            }
            visual = next(
                item for item in acquired.observation.sources
                if item.surface == "browsergym_visual"
            )
            assert len(visual.correspondences) == 1
            assert visual.bindings == ()
        finally:
            await environment.close()

    asyncio.run(scenario())

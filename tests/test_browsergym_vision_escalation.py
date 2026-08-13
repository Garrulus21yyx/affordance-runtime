from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np
from browsergym_adapter_support import FakeBrowserGym, ax_node, raw_observation

from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.agent.step_execution_evidence import resolve_visual_step_execution_evidence
from affordance_runtime.benchmarks.external_smoke.browsergym_environment import (
    BrowserGymMiniWobEnvironment,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
)
from affordance_runtime.execution import DispatchStatus
from affordance_runtime.task.set_objective import (
    PredicateTruth,
    ScopeEntityDomain,
    ScopeExtent,
    ScopeSpec,
    SetQuantifier,
    VisualConcept,
)
from affordance_runtime.task.set_objective_state import establish_set_objective_state
from affordance_runtime.visual_disambiguation import VisualCandidateDisambiguationRequest
from affordance_runtime.visual_grounding import (
    VisualGroundingPoint,
    VisualGroundingRequest,
    VisualRegion,
    VisualRegionProposalRequest,
)
from affordance_runtime.visual_predicate_classification import (
    VisualPredicateClassification,
    VisualPredicateClassificationRequest,
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


@dataclass
class _PredicateClassifier:
    truths: tuple[PredicateTruth, ...]
    calls: list[VisualPredicateClassificationRequest] = field(default_factory=list)
    provider: str = "fixture"
    model: str = "fixture"
    prompt_version: str = "visual-e-ref-predicate-batch-v1"

    def classify(self, request: VisualPredicateClassificationRequest):
        self.calls.append(request)
        assert len(request.candidates) == len(self.truths)
        return tuple(
            VisualPredicateClassification(candidate.ref, truth, 0.95)
            for candidate, truth in zip(request.candidates, self.truths, strict=True)
        )


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
    classifier: _PredicateClassifier | None = None,
):
    first = proposer.regions[0]
    x, y, width, height = first.bbox_xywh
    grounder = _Grounder(
        VisualGroundingPoint(
            (x + width / 2, y + height / 2),
            normalized=first.normalized,
        )
    )
    return BrowserGymMiniWobEnvironment.open(
        "browsergym/miniwob.click-button",
        7,
        gym_factory=lambda *_args, **_kwargs: fake,
        visual_region_proposer=proposer,
        visual_point_grounder=grounder,
        visual_candidate_disambiguator=disambiguator,
        visual_predicate_classifier=classifier,
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
        initial = _raw_with_buttons(
            ("left", "Target", (20, 20, 40, 30)),
            ("right", "Target", (120, 20, 40, 30)),
            goal="Click the visible target.",
        )
        post = _raw_with_buttons(("continue", "Continue", (20, 20, 50, 30)))
        fake = FakeBrowserGym(initial, post)
        fake.step_terminated = False
        fake.step_done = False
        fake.probe_override = {
            "raw": initial,
            "task": {
                "ready": True,
                "done": False,
                "raw_reward": 0,
                "episode": "0",
                "url": initial["url"],
            },
            "latency_ms": 0.1,
        }
        proposer = _Proposer([VisualRegion((0.25, 0.2, 0.2, 0.3), "target", 0.9)])
        disambiguator = _Disambiguator("E1")
        environment, task = _open(fake, proposer, disambiguator=disambiguator)
        try:
            acquired = await environment.reset(task)
            assert acquired.observation is not None
            assert len(disambiguator.calls) == 1
            assert proposer.calls == []
            assert isinstance(environment.visual_point_grounder, _Grounder)
            assert environment.visual_point_grounder.calls == []
            space = ActionSpaceBuilder().build(task, acquired.observation)
            request = ActionBinder().bind(
                ActionSpaceBuilder().admit(space.options[0], {}),
                acquired.observation,
                "context:visual",
            )

            outcome = await environment.execute(request)

            assert outcome.result.dispatch_status is DispatchStatus.SENT
            assert outcome.post_acquisition.observation is not None
            assert len(disambiguator.calls) == 1
            assert proposer.calls == []
            assert environment.visual_point_grounder.calls == []
            assert environment.last_visual_escalation is not None
            assert environment.last_visual_escalation.mode is VisionEscalationMode.SKIP
            assert {item.surface for item in outcome.post_acquisition.observation.sources} == {"browsergym"}
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_marked_main_policy_owns_ambiguous_candidates_without_task_text_routing() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(
            ("left", "", (20, 20, 40, 30)),
            ("right", "", (120, 20, 40, 30)),
            goal="Click all the grey shades.",
        )
        proposer = _Proposer([VisualRegion((0.1, 0.2, 0.2, 0.3), "unused", 0.9)])
        disambiguator = _Disambiguator("E1")
        environment, task = BrowserGymMiniWobEnvironment.open(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: FakeBrowserGym(raw),
            visual_region_proposer=proposer,
            visual_candidate_disambiguator=disambiguator,
            marked_candidate_policy_available=True,
        )
        try:
            acquired = await environment.reset(task)
            assert acquired.observation is not None
            assert environment.last_visual_escalation is not None
            assert environment.last_visual_escalation.evidence_need is VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION
            assert environment.last_visual_escalation.mode is VisionEscalationMode.SKIP
            assert disambiguator.calls == []
            assert len(acquired.observation.bindings) == 2
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_marked_screenshot_policy_owns_ambiguous_e_ref_choice_without_provider_call() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(
            ("left", "", (20, 20, 40, 30)),
            ("right", "", (120, 20, 40, 30)),
            goal="Click all the grey shades.",
        )
        proposer = _Proposer([VisualRegion((0.1, 0.2, 0.2, 0.3), "unused", 0.9)])
        disambiguator = _Disambiguator("E1")
        environment, task = BrowserGymMiniWobEnvironment.open(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: FakeBrowserGym(raw),
            visual_region_proposer=proposer,
            visual_candidate_disambiguator=disambiguator,
            marked_candidate_policy_available=True,
        )
        try:
            acquired = await environment.reset(task)

            assert acquired.observation is not None
            assert environment.last_visual_escalation is not None
            assert environment.last_visual_escalation.mode is VisionEscalationMode.SKIP
            assert environment.last_visual_escalation.evidence_need is VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION
            assert environment.last_visual_escalation.reason_code == (
                "marked_candidate_choice_delegated_to_screenshot_policy"
            )
            assert disambiguator.calls == []
            assert len(acquired.observation.bindings) == 2
            assert {item.surface for item in acquired.observation.bindings} == {"browsergym"}
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_auxiliary_predicate_classifier_is_not_automatically_invoked() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(
            ("left", "", (20, 20, 40, 30)),
            ("right", "", (120, 20, 40, 30)),
            goal="Click all apples.",
        )
        proposer = _Proposer([VisualRegion((0.1, 0.2, 0.2, 0.3), "unused", 0.9)])
        disambiguator = _Disambiguator("E1")
        classifier = _PredicateClassifier((PredicateTruth.TRUE, PredicateTruth.FALSE))
        environment, task = BrowserGymMiniWobEnvironment.open(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: FakeBrowserGym(raw),
            visual_region_proposer=proposer,
            visual_candidate_disambiguator=disambiguator,
            visual_predicate_classifier=classifier,
            marked_candidate_policy_available=True,
        )
        try:
            acquired = await environment.reset(task)

            assert acquired.observation is not None
            assert environment.last_visual_escalation is not None
            assert environment.last_visual_escalation.evidence_need is VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION
            assert classifier.calls == []
            assert disambiguator.calls == []
            assert len(acquired.observation.bindings) == 2
            assert not any(fact.predicate.startswith("task_predicate") for fact in acquired.observation.facts)
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_runtime_set_evidence_obligation_invokes_visual_classifier() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(
            ("left", "", (20, 20, 40, 30)),
            ("right", "", (120, 20, 40, 30)),
            goal="Click all apples.",
        )
        proposer = _Proposer([VisualRegion((0.1, 0.2, 0.2, 0.3), "unused", 0.9)])
        classifier = _PredicateClassifier((PredicateTruth.TRUE, PredicateTruth.FALSE))
        environment, task = _open(FakeBrowserGym(raw), proposer, classifier=classifier)
        try:
            acquired = await environment.reset(task)
            assert acquired.observation is not None
            state = AgentLoopState(acquired.observation)
            state.active_step_execution = establish_set_objective_state(
                predicate=VisualConcept("apple"),
                quantifier=SetQuantifier.ALL_IN_CLOSED_SCOPE,
                semantic_action="activate",
                candidate_entity_ids=tuple(item.target_id for item in acquired.observation.targets),
                observation=acquired.observation,
                # This witness classifies an already closed DOM candidate set;
                # it is not an open-world "all visible apples" claim.
                scope=ScopeSpec(
                    "scope:structured-visual-disambiguation",
                    "current-viewport",
                    ScopeExtent.CURRENT_VIEWPORT,
                    entity_domain=ScopeEntityDomain.STRUCTURED,
                ),
            )
            session = SimpleNamespace(state=state, environment=environment)

            resolved = await resolve_visual_step_execution_evidence(session)

            assert resolved is True
            assert len(classifier.calls) == 1
            assert environment.visual_predicate_classifier_calls == 1
            assert [item.truth for item in state.active_step_execution.assessments] == [
                PredicateTruth.TRUE,
                PredicateTruth.FALSE,
            ]
            assert all(item.confidence is None for item in state.active_step_execution.assessments)
            assert await resolve_visual_step_execution_evidence(session) is False
            assert len(classifier.calls) == 1
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_open_world_visual_set_does_not_classify_before_visual_scope_closure() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(
            ("left", "", (20, 20, 40, 30)),
            ("right", "", (120, 20, 40, 30)),
            goal="Click all apples.",
        )
        classifier = _PredicateClassifier((PredicateTruth.TRUE, PredicateTruth.FALSE))
        environment, task = _open(
            FakeBrowserGym(raw),
            _Proposer([VisualRegion((0.1, 0.2, 0.2, 0.3), "unused", 0.9)]),
            classifier=classifier,
        )
        try:
            acquired = await environment.reset(task)
            assert acquired.observation is not None
            state = AgentLoopState(acquired.observation)
            state.active_step_execution = establish_set_objective_state(
                predicate=VisualConcept("apple"),
                quantifier=SetQuantifier.ALL_IN_CLOSED_SCOPE,
                semantic_action="activate",
                candidate_entity_ids=(),
                observation=acquired.observation,
            )
            session = SimpleNamespace(state=state, environment=environment)

            assert state.active_step_execution.universe.coverage.value == "partial"
            assert await resolve_visual_step_execution_evidence(session) is False
            assert classifier.calls == []
            assert state.active_step_execution.certificate is None
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
            assert environment.last_visual_escalation.evidence_need is VisionEvidenceNeed.NONE
            assert disambiguator.calls == []
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_unowned_repeated_leaf_payload_is_not_promoted_to_semantic_truth() -> None:
    async def scenario() -> None:
        raw = raw_observation(
            ax_node("answer", "textbox", ""),
            ax_node("submit", "button", "Submit"),
            goal="Count the shapes and enter the total number.",
        )
        raw["screenshot"] = np.full((100, 200, 3), 255, dtype=np.uint8)
        raw["_browsergym_private_visual_groups"] = [
            {"count": 8, "bbox": [20, 20, 50, 40]},
            {"count": 2, "bbox": [100, 40, 30, 20]},
        ]
        proposer = _Proposer([VisualRegion((0.1, 0.2, 0.2, 0.3), "unused", 0.9)])
        environment, task = _open(FakeBrowserGym(raw), proposer)
        try:
            acquired = await environment.reset(task)

            assert acquired.observation is not None
            groups = [item for item in acquired.observation.targets if item.role == "visual-group"]
            assert groups == []
            assert environment.last_visual_escalation is not None
            assert environment.last_visual_escalation.evidence_need is VisionEvidenceNeed.NONE
            assert proposer.calls == []
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_point_grounder_is_not_a_browsergym_mainline_visual_capability() -> None:
    @dataclass
    class FailingGrounder:
        provider: str = "fixture"
        model: str = "fixture"
        prompt_version: str = "fixture"

        def ground(self, request: VisualGroundingRequest) -> VisualGroundingPoint:
            del request
            raise AssertionError("BrowserGym mainline must not invoke a point grounder")

    async def scenario() -> None:
        raw = raw_observation(goal="Click the visible target.")
        raw["screenshot"] = np.full((100, 200, 3), 255, dtype=np.uint8)
        grounder = FailingGrounder()
        environment, task = BrowserGymMiniWobEnvironment.open(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: FakeBrowserGym(raw),
            visual_point_grounder=grounder,
        )
        try:
            acquired = await environment.reset(task)
            assert acquired.observation is not None
            assert acquired.observation.bindings == ()
            assert environment.last_visual_escalation is not None
            assert environment.last_visual_escalation.mode is VisionEscalationMode.UNAVAILABLE
            assert environment.visual_provider_failure_count == 0
            assert environment.visual_point_grounder_calls == 0
            assert all(offer.source != "browsergym_visual" for offer in environment.observation_capabilities.offers)
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_same_frame_visual_region_merges_into_dom_identity_without_coordinate_binding() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(("okay", "Okay", (50, 20, 40, 30)))
        proposer = _Proposer(
            [
                VisualRegion((0.25, 0.2, 0.2, 0.3), "red Okay button", 0.9),
            ]
        )
        environment, task = _open(FakeBrowserGym(raw), proposer)
        try:
            await environment.reset(task)
            acquired = await environment.capture(_visual_request())
            assert acquired.observation is not None
            visual = next(item for item in acquired.observation.sources if item.surface == "browsergym_visual")
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


def test_visual_region_without_dom_correspondence_remains_observation_only() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(("okay", "Okay", (0, 0, 20, 20)))
        proposer = _Proposer(
            [
                VisualRegion((0.5, 0.5, 0.2, 0.2), "canvas-only dot", 0.9, role="shape"),
            ]
        )
        environment, task = _open(FakeBrowserGym(raw), proposer)
        try:
            await environment.reset(task)
            acquired = await environment.capture(_visual_request())
            assert acquired.observation is not None
            assert {item.surface for item in acquired.observation.bindings} == {"browsergym"}
            visual = next(item for item in acquired.observation.sources if item.surface == "browsergym_visual")
            assert len(visual.targets) == 1
            assert visual.bindings == ()
            assert environment.visual_binding_acquired_count == 0
            assert environment.visual_point_grounder_calls == 0
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
        proposer = _Proposer(
            [
                VisualRegion(
                    (0.25, 0.2, 0.2, 0.3),
                    "decorative paragraph",
                    0.9,
                    role="text",
                ),
            ]
        )
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
            assert environment.last_visual_escalation.mode is VisionEscalationMode.VERIFY_STRUCTURED_CANDIDATES
            assert len(disambiguator.calls) == 1
            assert proposer.calls == []
            assert environment.visual_point_grounder_calls == 0
            selected_facts = [
                fact
                for fact in acquired.observation.facts
                if fact.predicate == "visually_selected" and fact.value is True
            ]
            assert len(selected_facts) == 1
            assert [item.surface for item in acquired.observation.bindings] == ["browsergym"]
            assert acquired.observation.bindings[0].target_id == selected_facts[0].subject_id
            assert selected_facts[0].subject_id in {binding.target_id for binding in acquired.observation.bindings}
            visual = next(item for item in acquired.observation.sources if item.surface == "browsergym_visual")
            assert len(visual.correspondences) == 1
            assert visual.bindings == ()
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_clickable_svg_candidates_use_e_ref_then_dom_binding_without_point() -> None:
    async def scenario() -> None:
        raw = raw_observation(
            ax_node("circle-left", "graphics-symbol", "", parent_id="svg-root"),
            ax_node("circle-right", "graphics-symbol", "", parent_id="svg-root"),
            goal="Click the requested grid coordinate.",
        )
        raw["screenshot"] = np.full((120, 220, 3), 255, dtype=np.uint8)
        for bid, bbox in (
            ("circle-left", [20, 40, 14, 14]),
            ("circle-right", [120, 40, 14, 14]),
        ):
            raw["extra_element_properties"][bid].update(
                {
                    "clickable": True,
                    "visibility": 1.0,
                    "bbox": bbox,
                }
            )
            raw[PRIVATE_CONTROL_PROPERTIES_KEY][bid]["bbox"] = bbox
        proposer = _Proposer([VisualRegion((0.1, 0.1, 0.2, 0.2), "unused", 0.9)])
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
            assert environment.last_visual_escalation.mode is VisionEscalationMode.VERIFY_STRUCTURED_CANDIDATES
            assert len(disambiguator.calls) == 1
            assert len(disambiguator.calls[0].candidates) == 2
            assert [item.bbox for item in disambiguator.calls[0].candidates] == [
                (20, 40, 14, 14),
                (120, 40, 14, 14),
            ]
            assert proposer.calls == []
            assert environment.visual_point_grounder_calls == 0
            assert len(acquired.observation.bindings) == 1
            binding = acquired.observation.bindings[0]
            assert binding.surface == "browsergym"
            assert binding.semantic_action == "activate"
            assert binding.primitive_action == "click"
            assert "point" not in repr(binding).casefold()
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_dom_selected_class_is_public_current_state_not_private_answer_data() -> None:
    async def scenario() -> None:
        raw = _raw_with_buttons(("shade", "", (20, 20, 18, 18)))
        raw[PRIVATE_CONTROL_PROPERTIES_KEY]["shade"]["selected"] = True
        proposer = _Proposer([VisualRegion((0.1, 0.2, 0.2, 0.3), "unused", 0.9)])
        environment, task = _open(FakeBrowserGym(raw), proposer)
        try:
            acquired = await environment.reset(task)

            assert acquired.observation is not None
            target = next(item for item in acquired.observation.targets if item.role == "button")
            assert target.state["selected"] is True
            assert "color" not in target.state
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_unlabeled_clickable_computed_color_is_public_without_hidden_dom_attribute() -> None:
    async def scenario() -> None:
        raw = raw_observation(
            ax_node("shade", "graphics-symbol", ""),
            goal="Select all the blue shades.",
        )
        raw["screenshot"] = np.full((100, 200, 3), 255, dtype=np.uint8)
        raw["extra_element_properties"]["shade"].update(
            {
                "clickable": True,
                "visibility": 1.0,
                "bbox": [20, 20, 18, 18],
            }
        )
        raw[PRIVATE_CONTROL_PROPERTIES_KEY]["shade"].update(
            {
                "bbox": [20, 20, 18, 18],
                "color_family": "blue",
            }
        )
        proposer = _Proposer([VisualRegion((0.1, 0.2, 0.2, 0.3), "unused", 0.9)])
        environment, task = _open(FakeBrowserGym(raw), proposer)
        try:
            acquired = await environment.reset(task)

            assert acquired.observation is not None
            target = next(item for item in acquired.observation.targets if item.role == "clickable")
            assert target.state == {"appearance.color_family": "blue"}
            assert "data-color" not in repr(target)
        finally:
            await environment.close()

    asyncio.run(scenario())

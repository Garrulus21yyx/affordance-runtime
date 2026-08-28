from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np

import affordance_runtime.surfaces.browsergym.environment as browsergym_environment_module
from affordance_runtime.actions import (
    ActionSpaceBuilder,
)
from affordance_runtime.agent import RequestObservation
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.model.policy.tool_contracts import ToolCall
from affordance_runtime.surfaces.browsergym.binding import BrowserGymVisualBinding
from affordance_runtime.surfaces.browsergym.semantics import PRIVATE_CONTROL_PROPERTIES_KEY
from affordance_runtime.surfaces.browsergym.visual_projection import browsergym_visual_frame
from affordance_runtime.surfaces.visual.contracts import VisualRegionBinding
from affordance_runtime.surfaces.visual.disambiguation import (
    VisualCandidateDisambiguationRequest,
)
from affordance_runtime.surfaces.visual.grounding import (
    VisualGroundingAbstained,
    VisualGroundingAbstentionReason,
    VisualGroundingPoint,
    VisualGroundingRequest,
    VisualRegion,
    VisualRegionProposalRequest,
)
from affordance_runtime.surfaces.visual.predicate_classification import (
    PredicateTruth,
    VisualPredicateClassification,
    VisualPredicateClassificationRequest,
)
from affordance_runtime.surfaces.visual.semantic_classification import (
    VisualBooleanClassification,
    VisualChangeClassificationRequest,
    VisualSpatialClassificationRequest,
    VisualTextReading,
    VisualTextReadingRequest,
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
from affordance_runtime.world.observation_outcomes import ObservationQueryDisposition
from tests.support.model_delivery import catalog_for, resolve_catalog_call
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
class _AbstainingGrounder:
    reason: VisualGroundingAbstentionReason
    calls: list[VisualGroundingRequest] = field(default_factory=list)
    provider: str = "zhipu"
    model: str = "glm-fixture"
    prompt_version: str = "visual-grounder-v3"

    def ground(self, request: VisualGroundingRequest) -> VisualGroundingPoint:
        self.calls.append(request)
        raise VisualGroundingAbstained(self.reason)


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


@dataclass
class _PredicateClassifier:
    truths: tuple[PredicateTruth, ...]
    calls: list[VisualPredicateClassificationRequest] = field(default_factory=list)
    provider: str = "fixture"
    model: str = "fixture"
    prompt_version: str = "fixture-v1"

    def classify(
        self,
        request: VisualPredicateClassificationRequest,
    ) -> tuple[VisualPredicateClassification, ...]:
        self.calls.append(request)
        return tuple(
            VisualPredicateClassification(candidate.ref, truth, 0.9)
            for candidate, truth in zip(request.candidates, self.truths, strict=True)
        )


@dataclass
class _TextReader:
    texts: tuple[str | None, ...]
    calls: list[VisualTextReadingRequest] = field(default_factory=list)
    provider: str = "fixture"
    model: str = "fixture"
    prompt_version: str = "fixture-v1"

    def read(self, request: VisualTextReadingRequest) -> tuple[VisualTextReading, ...]:
        self.calls.append(request)
        return tuple(
            VisualTextReading(candidate.ref, text, 0.9)
            for candidate, text in zip(request.candidates, self.texts, strict=True)
        )


@dataclass
class _BooleanClassifier:
    truth: PredicateTruth
    calls: list[VisualSpatialClassificationRequest | VisualChangeClassificationRequest] = field(default_factory=list)
    provider: str = "fixture"
    model: str = "fixture"
    prompt_version: str = "fixture-v1"

    def classify(self, request):
        self.calls.append(request)
        return VisualBooleanClassification(self.truth, 0.9)


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


_RUNTIME_ROLES = {"viewport", "focused_context"}


def _non_runtime_bindings(observation):
    runtime_target_ids = {target.target_id for target in observation.targets if target.role in _RUNTIME_ROLES}
    return tuple(binding for binding in observation.bindings if binding.target_id not in runtime_target_ids)


def _non_runtime_options(task, observation):
    runtime_target_ids = {target.target_id for target in observation.targets if target.role in _RUNTIME_ROLES}
    return tuple(
        option
        for option in ActionSpaceBuilder().build(task, observation).options
        if option.target_id not in runtime_target_ids
    )


def _visual_targets(observation):
    visual_ids = {
        target.target_id
        for source in observation.sources
        if source.surface == "browsergym_visual"
        for target in source.targets
    }
    return tuple(target for target in observation.targets if target.target_id in visual_ids)


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


def _predicate_request(subject_ids: tuple[str, ...]) -> WorldObservationRequest:
    return WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        "verify the current visual state",
        (
            ObservationNeed(
                need_id="observation-query:predicate",
                purpose=ObservationPurpose.VISUAL_PROPERTY,
                subject_ids=subject_ids,
                required_modality=ObservationModality.VISUAL,
                required_assurance=ObservationAssurance.WEAK,
                evidence_property="visually selected",
                query_text="visually selected",
            ),
        ),
    )


def _semantic_request(
    purpose: ObservationPurpose,
    subject_ids: tuple[str, ...],
    query: str,
) -> WorldObservationRequest:
    return WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        "bounded visual semantic query",
        (
            ObservationNeed(
                need_id=f"observation-query:{purpose.value}",
                purpose=purpose,
                subject_ids=subject_ids,
                required_modality=ObservationModality.VISUAL,
                required_assurance=ObservationAssurance.WEAK,
                query_text=query,
            ),
        ),
    )


def test_visual_predicate_batch_returns_partial_typed_outcome_and_aligned_fact() -> None:
    async def scenario() -> None:
        raw = _candidate_raw((10, 10, 30, 20), (60, 10, 30, 20))
        fake = FakeBrowserGym(raw)
        classifier = _PredicateClassifier((PredicateTruth.TRUE, PredicateTruth.UNKNOWN))
        environment, task = open_surface(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: fake,
            visual_predicate_classifier=classifier,
        )
        try:
            initial = await environment.reset(task)
            assert initial.observation is not None
            subject_ids = tuple(item.target_id for item in initial.observation.targets if item.role == "button")
            assert len(subject_ids) == 2
            assert (
                ObservationPurpose.VISUAL_PROPERTY
                in next(
                    item for item in environment.observation_offers if item.source == "browsergym_visual"
                ).supported_purposes
            )

            acquired = await environment.capture(_predicate_request(subject_ids))
        finally:
            await environment.close()

        assert acquired.observation is not None
        outcome = acquired.query_outcome("observation-query:predicate")
        assert outcome is not None
        assert outcome.disposition is ObservationQueryDisposition.PARTIAL
        assert tuple(item.locator.input_indices for item in outcome.unknown_items) == ((1,),)
        assert len(classifier.calls) == 1
        assert tuple(item.target_id for item in classifier.calls[0].candidates) == subject_ids
        assert environment.visual_predicate_classifier_calls == 1
        assert environment.visual_predicate_assessment_count == 2
        predicate_facts = tuple(fact for fact in acquired.observation.facts if fact.predicate == "visually selected")
        assert tuple((fact.subject_id, fact.value) for fact in predicate_facts) == (
            (outcome.observed_subject_ids[0], True),
        )
        assert not any(
            fact.subject_id == subject_ids[1] and fact.predicate == "visually selected"
            for fact in acquired.observation.facts
        )
        assert not any(binding.surface == "browsergym_visual" for binding in acquired.observation.bindings)

    asyncio.run(scenario())


def test_visual_text_batch_returns_observed_and_typed_unknown_without_actions() -> None:
    async def scenario() -> None:
        raw = _candidate_raw((10, 10, 30, 20), (60, 10, 30, 20))
        reader = _TextReader(("Alpha", None))
        environment, task = open_surface(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: FakeBrowserGym(raw),
            visual_text_reader=reader,
        )
        try:
            initial = await environment.reset(task)
            assert initial.observation is not None
            subject_ids = tuple(item.target_id for item in initial.observation.targets if item.role == "button")
            acquired = await environment.capture(
                _semantic_request(ObservationPurpose.TEXT_IN_IMAGE, subject_ids, "read each label")
            )
        finally:
            await environment.close()

        outcome = acquired.query_outcome("observation-query:text_in_image")
        assert outcome is not None
        assert outcome.disposition is ObservationQueryDisposition.PARTIAL
        assert tuple(item.locator.input_indices for item in outcome.unknown_items) == ((1,),)
        assert len(reader.calls) == 1
        assert any(
            fact.predicate == "text_in_image" and fact.value == "Alpha"
            for fact in acquired.observation.facts  # type: ignore[union-attr]
        )
        assert not any(
            binding.surface == "browsergym_visual"
            for binding in acquired.observation.bindings  # type: ignore[union-attr]
        )

    asyncio.run(scenario())


def test_visual_spatial_false_is_observed_without_inventing_gui_state() -> None:
    async def scenario() -> None:
        raw = _candidate_raw((10, 10, 30, 20), (60, 10, 30, 20))
        classifier = _BooleanClassifier(PredicateTruth.FALSE)
        environment, task = open_surface(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: FakeBrowserGym(raw),
            visual_spatial_classifier=classifier,
        )
        try:
            initial = await environment.reset(task)
            assert initial.observation is not None
            subject_ids = tuple(item.target_id for item in initial.observation.targets if item.role == "button")
            acquired = await environment.capture(
                _semantic_request(
                    ObservationPurpose.SPATIAL_RELATIONSHIP,
                    subject_ids,
                    "the first is left of the second",
                )
            )
        finally:
            await environment.close()

        outcome = acquired.query_outcome("observation-query:spatial_relationship")
        assert outcome is not None
        assert outcome.disposition is ObservationQueryDisposition.OBSERVED
        assert outcome.observed_subject_ids == subject_ids
        assert len(classifier.calls) == 1
        visual = next(
            source
            for source in acquired.observation.sources  # type: ignore[union-attr]
            if source.surface == "browsergym_visual"
        )
        assert visual.facts == ()
        assert visual.bindings == ()

    asyncio.run(scenario())


def test_visual_change_without_before_lineage_is_unknown_and_zero_provider_calls() -> None:
    async def scenario() -> None:
        raw = _candidate_raw((10, 10, 30, 20))
        classifier = _BooleanClassifier(PredicateTruth.TRUE)
        environment, task = open_surface(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: FakeBrowserGym(raw),
            visual_change_classifier=classifier,
        )
        try:
            initial = await environment.reset(task)
            assert initial.observation is not None
            subject_id = next(item.target_id for item in initial.observation.targets if item.role == "button")
            offer = next(item for item in environment.observation_offers if item.source == "browsergym_visual")
            assert ObservationPurpose.VISUAL_CHANGE not in offer.supported_purposes
            acquired = await environment.capture(
                _semantic_request(
                    ObservationPurpose.VISUAL_CHANGE,
                    (subject_id,),
                    "the visible appearance changed",
                )
            )
        finally:
            await environment.close()

        assert acquired.status.value == "capability_unavailable"
        assert acquired.query_outcome("observation-query:visual_change") is None
        assert classifier.calls == []

    asyncio.run(scenario())


def test_point_grounding_uses_atomic_query_and_requires_next_policy_action() -> None:
    async def scenario() -> None:
        fake = FakeBrowserGym(_raw())
        proposer = _Proposer([VisualRegion((0.25, 0.2, 0.2, 0.3), "target", 0.9)])
        grounder = _Grounder(VisualGroundingPoint((0.5, 0.5), normalized=True))
        environment, task = open_surface(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: fake,
            visual_region_proposer=proposer,
            visual_point_grounder=grounder,
        )
        try:
            await environment.reset(task)
            assert grounder.calls == []
            acquired = await environment.capture(
                WorldObservationRequest(
                    ObservationRequestKind.POLICY_REQUEST,
                    "ground one current point",
                    (
                        ObservationNeed(
                            "observation-query:point",
                            ObservationPurpose.POINT_GROUNDING,
                            required_modality=ObservationModality.VISUAL,
                            required_assurance=ObservationAssurance.WEAK,
                            query_text="the small circular control in the center",
                        ),
                    ),
                )
            )
        finally:
            await environment.close()

        outcome = acquired.query_outcome("observation-query:point")
        assert outcome is not None
        assert outcome.disposition is ObservationQueryDisposition.OBSERVED
        assert len(grounder.calls) == 1
        assert grounder.calls[0].instruction == "the small circular control in the center"
        assert grounder.calls[0].instruction != task.instruction
        assert proposer.calls == []
        assert environment.visual_proposer_calls == 0
        assert environment.visual_point_grounder_calls == 1
        assert fake.actions == []

    asyncio.run(scenario())


def test_point_grounding_closed_abstention_is_unknown_not_provider_failure() -> None:
    async def scenario() -> None:
        grounder = _AbstainingGrounder(VisualGroundingAbstentionReason.INSUFFICIENT_RESOLUTION)
        environment, task = open_surface(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: FakeBrowserGym(_raw()),
            visual_point_grounder=grounder,
        )
        try:
            await environment.reset(task)
            acquired = await environment.capture(
                WorldObservationRequest(
                    ObservationRequestKind.POLICY_REQUEST,
                    "ground one current point",
                    (
                        ObservationNeed(
                            "observation-query:point-abstained",
                            ObservationPurpose.POINT_GROUNDING,
                            required_modality=ObservationModality.VISUAL,
                            required_assurance=ObservationAssurance.WEAK,
                            query_text="the small circular control in the center",
                        ),
                    ),
                )
            )
        finally:
            await environment.close()

        outcome = acquired.query_outcome("observation-query:point-abstained")
        assert outcome is not None
        assert outcome.disposition is ObservationQueryDisposition.UNKNOWN
        assert tuple(item.reason.value for item in outcome.unknown_items) == ("insufficient_resolution",)
        assert environment.visual_provider_abstained_count == 1
        assert environment.visual_provider_failure_count == 1
        assert environment.visual_point_grounder_calls == 1
        assert len(grounder.calls) == 1

    asyncio.run(scenario())


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


def test_typed_disambiguation_returns_chosen_candidate_without_selected_state() -> None:
    async def scenario() -> None:
        raw = _candidate_raw((10, 10, 30, 20), (60, 10, 30, 20))
        disambiguator = _CandidateDisambiguator("E2")
        environment, task = open_surface(
            "browsergym/miniwob.click-button",
            7,
            gym_factory=lambda *_args, **_kwargs: FakeBrowserGym(raw),
            visual_candidate_disambiguator=disambiguator,
        )
        try:
            initial = await environment.reset(task)
            assert initial.observation is not None
            candidate_ids = tuple(item.target_id for item in initial.observation.targets if item.role == "button")
            acquired = await environment.capture(
                WorldObservationRequest(
                    ObservationRequestKind.POLICY_REQUEST,
                    "disambiguate current candidates",
                    (
                        ObservationNeed(
                            "observation-query:disambiguation",
                            ObservationPurpose.TARGET_DISAMBIGUATION,
                            required_modality=ObservationModality.VISUAL,
                            required_assurance=ObservationAssurance.WEAK,
                            candidate_ids=candidate_ids,
                            query_text="the visually emphasized candidate",
                        ),
                    ),
                )
            )
        finally:
            await environment.close()

        outcome = acquired.query_outcome("observation-query:disambiguation")
        assert outcome is not None
        assert outcome.observed_subject_ids == (candidate_ids[1],)
        assert len(disambiguator.calls) == 1
        assert not any(
            fact.predicate == "visually_selected"
            for fact in acquired.observation.facts  # type: ignore[union-attr]
        )

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


def test_visual_only_evidence_mark_does_not_create_action_authority() -> None:
    async def scenario() -> None:
        fake = FakeBrowserGym(_raw())
        proposer = _Proposer([VisualRegion((0.25, 0.2, 0.2, 0.3), "target", 0.9)])
        environment, task = _open(fake, proposer)
        try:
            initial = await environment.reset(task)
            assert initial.observation is not None
            assert _non_runtime_bindings(initial.observation) == ()
            assert len(proposer.calls) == 0
            assert environment.visual_proposer_calls == 0
            assert environment.visual_point_grounder_calls == 0
            assert isinstance(environment.visual_point_grounder, _Grounder)
            assert environment.visual_point_grounder.calls == []
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
            assert _non_runtime_bindings(acquired.observation) == ()
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
            assert sum(item.marked for item in context.grounding.entities) == 1
            assert tuple(mark.ref for mark in context.image_inputs[0].marks) == ("N1",)
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_grouped_browsergym_projection_encodes_one_shared_frame_per_acquisition(
    monkeypatch,
) -> None:
    calls = 0
    original = browsergym_environment_module.browsergym_capture_frame

    def capture_frame(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(browsergym_environment_module, "browsergym_capture_frame", capture_frame)

    async def scenario() -> None:
        fake = FakeBrowserGym(_raw())
        proposer = _Proposer([VisualRegion((0.25, 0.2, 0.2, 0.3), "target", 0.9)])
        environment, task = _open(fake, proposer, with_point=False)
        try:
            await environment.reset(task)
            assert calls == 1
            acquired = await environment.capture(_visual_request())
            assert acquired.observation is not None
            assert calls == 2
            sources = {item.surface: item for item in acquired.observation.sources}
            assert sources["browsergym"].media[0].sha256 == sources["browsergym_visual"].media[0].sha256
            assert sources["browsergym"].media[0].dimensions == sources["browsergym_visual"].media[0].dimensions
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
            assert _non_runtime_options(task, acquired.observation) == ()
            assert _non_runtime_bindings(acquired.observation) == ()
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
            assert _non_runtime_bindings(acquired.observation) == ()
            assert _non_runtime_options(task, acquired.observation) == ()
            assert environment.visual_point_grounder_calls == 0
            assert fake.actions == []
            assert environment.step_calls == 0
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_missing_native_task_globals_use_lifecycle_fallback_for_visual_currentness() -> None:
    async def scenario() -> None:
        raw = _raw()
        fake = FakeBrowserGym(raw)
        fake.probe_task = {}
        proposer = _Proposer([])
        environment, task = _open(fake, proposer, with_point=False)
        try:
            await environment.reset(task)
            frame = browsergym_visual_frame(raw, "visual:currentness")
            region = VisualRegionBinding.from_region(
                frame,
                "visual-region:currentness",
                VisualRegion(
                    (0.25, 0.2, 0.2, 0.3),
                    "target",
                    0.9,
                    primitive_action="point_activate",
                    action_point_xy=(0.3, 0.3),
                ),
            )
            private = BrowserGymVisualBinding(
                "binding:visual-currentness",
                environment._page_identity,  # noqa: SLF001 - low-level visual currentness conformance
                environment._episode_identity,  # noqa: SLF001
                region,
            )
            environment.bindings.replace((*environment.bindings.values, private))
            request = SimpleNamespace(
                binding=SimpleNamespace(
                    binding_id=private.binding_id,
                    source_observation_id=private.source_observation_id,
                    source_revision=private.source_revision,
                    primitive_action="point_activate",
                ),
            )

            error, count = environment._probe_visual_currentness(request, private)  # noqa: SLF001
        finally:
            await environment.close()

        assert error is None and count == 1
        assert environment.last_currentness_decision is not None
        assert environment.last_currentness_decision.status.value == "current"
        assert environment.last_currentness_decision.reason.value == "current"
        assert environment.last_currentness_decision.task_state_source.value == "lifecycle_fallback"
        assert environment.last_currentness_decision.episode_source.value == "lifecycle_fallback"
        assert fake.actions == []
        assert environment.step_calls == 0

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
            assert len(_visual_targets(acquired.observation)) == 1
            assert _non_runtime_bindings(acquired.observation) == ()
            assert _non_runtime_options(task, acquired.observation) == ()
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
            assert _non_runtime_options(task, acquired.observation) == ()
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

            _, catalog = catalog_for(context)
            assert "request_evidence" in {item.name for item in catalog.specs}
            decision = resolve_catalog_call(
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
            assert decision.decision.subject_ids == ()
            assert decision.decision.atomic_query == "discover relevant visible entities"
        finally:
            await environment.close()

    asyncio.run(scenario())

"""One grouped owner for structural and visual views of one BrowserSession."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from affordance_runtime.actions.grounding import EvidenceKind, GroundingSource, PerceptionRequirements
from affordance_runtime.execution.contracts import ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.surfaces.dom.adapter import DomSurfaceAdapter
from affordance_runtime.surfaces.dom.browser_session import (
    BrowserLayer,
    BrowserLayerKind,
    BrowserSession,
    BrowserSnapshot,
)
from affordance_runtime.surfaces.visual.adapter import VisualSurfaceAdapter
from affordance_runtime.surfaces.visual.contracts import VisualFrame
from affordance_runtime.surfaces.visual.disambiguation import (
    VisualCandidate,
    VisualCandidateDisambiguationRequest,
    VisualCandidateDisambiguatorPort,
    visual_candidate_disambiguator_from_environment,
)
from affordance_runtime.surfaces.visual.grounding import (
    VisualGrounderPort,
    VisualRegionProposerPort,
    visual_grounder_from_environment,
    visual_region_proposer_from_environment,
)
from affordance_runtime.surfaces.visual.predicate_classification import (
    PredicateTruth,
    VisualPredicateClassificationRequest,
    VisualPredicateClassifierPort,
    visual_predicate_classifier_from_environment,
)
from affordance_runtime.surfaces.visual.pydantic_ai_inference import (
    pydantic_ai_visual_inference_from_environment,
)
from affordance_runtime.surfaces.visual.semantic_classification import (
    VisualChangeClassificationRequest,
    VisualChangeClassifierPort,
    VisualLayerObserverPort,
    VisualLayerTransitionRequest,
    VisualSemanticRole,
    VisualSpatialClassificationRequest,
    VisualSpatialClassifierPort,
    VisualTextReaderPort,
    VisualTextReadingRequest,
    visual_semantic_classifier_from_environment,
)
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    ObservationOffer,
    ObservationRequestKind,
    SelectedObservationRequest,
    SelectedObservationResult,
    SourceAcquisitionStatus,
)
from affordance_runtime.world.contracts import (
    CoverageState,
    EntityAlignmentBasis,
    EntityAlignmentProposal,
    ObservationMedia,
    ObservationMediaVariant,
    ObservationSourceProfile,
    SemanticTarget,
    SourceEntityEndpoint,
    StateFact,
    SurfaceObservation,
)
from affordance_runtime.world.observation_needs import ObservationPurpose
from affordance_runtime.world.observation_outcomes import (
    InputLocator,
    ObservationObservedItem,
    ObservationQueryDisposition,
    ObservationQueryOutcome,
    ObservationUnknownItem,
    VisualUnknownReason,
)


@dataclass
class BrowserSessionSurfaceBundle:
    """Structural/visual adapter with one reset, capture, dispatch, and frame lineage owner."""

    session: BrowserSession
    region_proposer: VisualRegionProposerPort
    point_grounder: VisualGrounderPort | None = field(default=None, repr=False)
    candidate_disambiguator: VisualCandidateDisambiguatorPort | None = field(default=None, repr=False)
    predicate_classifier: VisualPredicateClassifierPort | None = field(default=None, repr=False)
    text_reader: VisualTextReaderPort | None = field(default=None, repr=False)
    spatial_classifier: VisualSpatialClassifierPort | None = field(default=None, repr=False)
    change_classifier: VisualChangeClassifierPort | None = field(default=None, repr=False)
    layer_observer: VisualLayerObserverPort | None = field(default=None, repr=False)
    surface: str = field(default="browser_session", init=False)
    owns_physical_reset: bool = field(default=True, init=False)
    execution_surfaces: tuple[str, ...] = field(default=("dom", "visual"), init=False)
    _dom: DomSurfaceAdapter = field(init=False, repr=False)
    _visual: VisualSurfaceAdapter = field(init=False, repr=False)
    _task: TaskGoal | None = field(default=None, init=False, repr=False)
    _current_frame: VisualFrame | None = field(default=None, init=False, repr=False)
    _before_frame: VisualFrame | None = field(default=None, init=False, repr=False)
    _current_layers: tuple[BrowserLayer, ...] = field(default=(), init=False, repr=False)
    _before_layers: tuple[BrowserLayer, ...] = field(default=(), init=False, repr=False)
    _pending_acquisition_id: str = field(default="", init=False, repr=False)
    _pending_snapshot: BrowserSnapshot | None = field(default=None, init=False, repr=False)
    _pending_structured: SurfaceObservation | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._dom = DomSurfaceAdapter(self.session, owns_physical_reset=False)
        self._visual = VisualSurfaceAdapter(
            self.session,
            self.region_proposer,
            self.point_grounder,
            owns_physical_reset=False,
        )

    @property
    def physical_environment_id(self) -> str:
        return f"browser_session:{id(self.session)}"

    @property
    def supports_independent_capture(self) -> bool:
        return True

    @property
    def observation_offers(self) -> tuple[ObservationOffer, ...]:
        group = self.physical_environment_id
        purposes = [ObservationPurpose.WORLD_GROUNDING, ObservationPurpose.ENTITY_DISCOVERY]
        if self.point_grounder is not None:
            purposes.append(ObservationPurpose.POINT_GROUNDING)
        if self.candidate_disambiguator is not None:
            purposes.append(ObservationPurpose.TARGET_DISAMBIGUATION)
        if self.predicate_classifier is not None:
            purposes.append(ObservationPurpose.VISUAL_PROPERTY)
        if self.text_reader is not None:
            purposes.append(ObservationPurpose.TEXT_IN_IMAGE)
        if self.spatial_classifier is not None:
            purposes.append(ObservationPurpose.SPATIAL_RELATIONSHIP)
        if self.change_classifier is not None and self._change_lineage_available:
            purposes.append(ObservationPurpose.VISUAL_CHANGE)
        if self.layer_observer is not None and self._before_frame is not None:
            purposes.append(ObservationPurpose.EFFECT_VERIFICATION)
        return (
            ObservationOffer("dom", "structural", "structural", "low", group),
            ObservationOffer(
                "visual",
                "visual",
                "weak",
                "high",
                group,
                tuple(purposes),
            ),
        )

    @property
    def _change_lineage_available(self) -> bool:
        return bool(
            self._before_frame is not None
            and self._current_frame is not None
            and self._before_frame.viewport == self._current_frame.viewport
        )

    def initialize_task(self, task: TaskGoal) -> None:
        self._task = task
        self._current_frame = None
        self._before_frame = None
        self._current_layers = ()
        self._before_layers = ()
        self._pending_acquisition_id = ""
        self._pending_snapshot = None
        self._pending_structured = None
        self._dom.initialize_task(task)
        self._visual.initialize_task(task)

    async def reset_physical(self) -> None:
        self.session.reset()

    async def acquire(self, request: SelectedObservationRequest) -> SelectedObservationResult:
        return (await self.acquire_group((request,)))[0]

    async def acquire_group(
        self,
        requests: tuple[SelectedObservationRequest, ...],
    ) -> tuple[SelectedObservationResult, ...]:
        if self._task is None:
            raise RuntimeError("browser bundle must be initialized before acquisition")
        if not requests:
            return ()
        if len({item.acquisition_id for item in requests}) != 1:
            raise ValueError("browser bundle group must conserve one acquisition identity")
        if len({item.source for item in requests}) != len(requests):
            raise ValueError("browser bundle group cannot repeat a source")
        visual_request = next((item for item in requests if item.source == "visual"), None)
        if visual_request is None:
            results = []
            for item in requests:
                if item.source != "dom":
                    results.append(
                        SelectedObservationResult.failed(
                            item,
                            SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE,
                            "source_not_owned",
                        )
                    )
                    continue
                snapshot = self.session.capture(page_id="agent-loop", task_instruction="")
                dom_result = self._dom.project_snapshot(item, snapshot)
                assert dom_result.observation is not None
                structured = self._with_layer_transition_obligation(item, snapshot, dom_result.observation)
                dom_result = replace(dom_result, observation=structured)
                self._pending_acquisition_id = item.acquisition_id
                self._pending_snapshot = snapshot
                self._pending_structured = structured
                self._current_layers = snapshot.layers
                results.append(dom_result)
            return tuple(results)
        cached = self._pending_acquisition_id == visual_request.acquisition_id
        if cached:
            assert self._pending_snapshot is not None
            frame = self.session.capture_visual_frame(f"{self._pending_snapshot.observation.snapshot_id}:visual")
            snapshot = replace(self._pending_snapshot, visual_frame=frame)
        else:
            snapshot = self.session.capture(
                page_id="agent-loop",
                task_instruction="",
                perception_requirements=PerceptionRequirements(
                    required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE}),
                    acceptable_evidence=frozenset({GroundingSource.DOM, GroundingSource.VISUAL}),
                    preferred_sources=(GroundingSource.DOM, GroundingSource.VISUAL),
                    observation_budget=1,
                    model_call_budget=0,
                ),
            )
        if snapshot.visual_frame is None:
            return tuple(
                SelectedObservationResult.failed(
                    item, SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE, "visual_frame_unavailable"
                )
                for item in requests
            )
        root = f"browser:{snapshot.observation.page_revision}"
        dom_request = next((item for item in requests if item.source == "dom"), None)
        dom_result = self._dom.project_snapshot(dom_request, snapshot) if dom_request is not None else None
        structured = self._pending_structured if cached else dom_result.observation if dom_result is not None else None
        visual_result = self._acquire_visual(visual_request, snapshot, structured, root)
        self._current_frame = snapshot.visual_frame
        self._current_layers = snapshot.layers
        if cached:
            self._pending_acquisition_id = ""
            self._pending_snapshot = None
            self._pending_structured = None
        by_source = {"visual": visual_result}
        if dom_result is not None:
            by_source["dom"] = dom_result
        return tuple(
            by_source.get(item.source)
            or SelectedObservationResult.failed(
                item, SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE, "source_not_owned"
            )
            for item in requests
        )

    def _with_layer_transition_obligation(
        self,
        request: SelectedObservationRequest,
        snapshot: BrowserSnapshot,
        structured: SurfaceObservation,
    ) -> SurfaceObservation:
        if (
            request.lifecycle_kind is not ObservationRequestKind.POST_ACTION_FALLBACK
            or self.layer_observer is None
            or self._before_frame is None
        ):
            return structured
        before = {_layer_signature(item) for item in self._before_layers}
        candidate_target_ids = tuple(
            f"dom-layer:{index}"
            for index, layer in enumerate(snapshot.layers)
            if layer.kind is BrowserLayerKind.GEOMETRIC_OVERLAY and _layer_signature(layer) not in before
        )
        if not candidate_target_ids:
            return structured
        return replace(
            structured,
            artifacts={
                **structured.artifacts,
                "unresolved_visual_layer_transition": {
                    "public_summary": "A newly visible overlay requires bounded visual interpretation.",
                    "candidate_target_ids": candidate_target_ids,
                },
            },
        )

    def _acquire_visual(
        self,
        request: SelectedObservationRequest,
        snapshot: BrowserSnapshot,
        structured: SurfaceObservation | None,
        acquisition_root_id: str,
    ) -> SelectedObservationResult:
        assert snapshot.visual_frame is not None
        purpose = _visual_purpose(request)
        if purpose in {
            ObservationPurpose.WORLD_GROUNDING,
            ObservationPurpose.ENTITY_DISCOVERY,
            ObservationPurpose.POINT_GROUNDING,
        }:
            frame = replace(
                snapshot.visual_frame,
                observation_id=f"{snapshot.visual_frame.observation_id}:visual",
            )
            need = next((item for item in request.needs if item.purpose is purpose), None)
            query = need.query_text if need is not None and need.query_text.strip() else "inspect current viewport"
            return self._visual.project_frame(
                request,
                frame,
                atomic_query=query,
                use_region_proposer=purpose is ObservationPurpose.ENTITY_DISCOVERY,
                use_point_grounder=purpose is ObservationPurpose.POINT_GROUNDING,
                acquisition_root_id=acquisition_root_id,
                max_results=need.max_results if need is not None else 16,
            )
        if structured is None:
            return SelectedObservationResult.failed(
                request, SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE, "structured_baseline_unavailable"
            )
        if purpose is ObservationPurpose.VISUAL_PROPERTY:
            return self._predicate(request, snapshot.visual_frame, structured, acquisition_root_id)
        if purpose is ObservationPurpose.TARGET_DISAMBIGUATION:
            return self._disambiguate(request, snapshot.visual_frame, structured, acquisition_root_id)
        if purpose is ObservationPurpose.TEXT_IN_IMAGE:
            return self._text(request, snapshot.visual_frame, structured, acquisition_root_id)
        if purpose is ObservationPurpose.SPATIAL_RELATIONSHIP:
            return self._spatial(request, snapshot.visual_frame, structured, acquisition_root_id)
        if purpose is ObservationPurpose.VISUAL_CHANGE:
            return self._change(request, snapshot.visual_frame, structured, acquisition_root_id)
        if purpose is ObservationPurpose.EFFECT_VERIFICATION:
            return self._observe_layer_transition(
                request,
                snapshot,
                structured,
                acquisition_root_id,
            )
        return SelectedObservationResult.failed(
            request, SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE, "visual_purpose_unavailable"
        )

    def _predicate(self, request, frame, structured, root) -> SelectedObservationResult:
        assert self.predicate_classifier is not None
        need = _single_need(request, ObservationPurpose.VISUAL_PROPERTY)
        candidates, index_by_ref, missing = _candidates(need.subject_ids, structured)
        unknown = [
            ObservationUnknownItem(InputLocator((index,)), VisualUnknownReason.TARGET_NOT_VISIBLE) for index in missing
        ]
        assessments = (
            self.predicate_classifier.classify(
                VisualPredicateClassificationRequest(
                    need.need_id,
                    frame.image_bytes,
                    (frame.image_width, frame.image_height),
                    need.evidence_property,
                    candidates,
                )
            )
            if candidates
            else ()
        )
        by_ref = {item.ref: item for item in assessments}
        if set(by_ref) != {item.ref for item in candidates} or len(by_ref) != len(assessments):
            raise ValueError("predicate provider must cover current candidates exactly once")
        targets: list[SemanticTarget] = []
        facts: list[StateFact] = []
        proposals: list[EntityAlignmentProposal] = []
        observed: list[ObservationObservedItem] = []
        by_candidate = {item.ref: item for item in candidates}
        observation_id = f"{frame.observation_id}:visual-predicate"
        for ref, index in index_by_ref.items():
            assessment, candidate = by_ref[ref], by_candidate[ref]
            if assessment.truth is PredicateTruth.UNKNOWN:
                unknown.append(
                    ObservationUnknownItem(InputLocator((index,)), VisualUnknownReason.PROPERTY_NOT_OBSERVABLE)
                )
                continue
            value = assessment.truth is PredicateTruth.TRUE
            local_id = f"predicate:{index}"
            fact_id = f"fact:{observation_id}:{index}:{need.evidence_property}"
            targets.append(SemanticTarget(local_id, candidate.role, candidate.label, {need.evidence_property: value}))
            facts.append(StateFact(fact_id, local_id, need.evidence_property, value, observation_id))
            proposals.append(
                _alignment(
                    observation_id,
                    local_id,
                    structured.observation_id,
                    candidate.target_id,
                    fact_id,
                    assessment.confidence,
                )
            )
            observed.append(ObservationObservedItem(InputLocator((index,)), (candidate.target_id,), (fact_id,)))
        return _semantic_result(
            request,
            need,
            frame,
            root,
            targets,
            facts,
            proposals,
            observed,
            unknown,
            "Bounded visual predicate evidence.",
        )

    def _disambiguate(self, request, frame, structured, root) -> SelectedObservationResult:
        assert self.candidate_disambiguator is not None
        need = _single_need(request, ObservationPurpose.TARGET_DISAMBIGUATION)
        candidates, index_by_ref, missing = _candidates(need.candidate_ids, structured)
        if missing or len(candidates) < 2:
            return _unknown_result(
                request,
                need,
                frame,
                root,
                VisualUnknownReason.TARGET_NOT_VISIBLE,
                tuple(range(len(need.candidate_ids))),
                "Candidate visual evidence is unavailable.",
            )
        selected_ref = self.candidate_disambiguator.choose(
            VisualCandidateDisambiguationRequest(
                need.need_id,
                frame.image_bytes,
                (frame.image_width, frame.image_height),
                need.query_text,
                candidates,
            )
        )
        if selected_ref is None:
            return _unknown_result(
                request,
                need,
                frame,
                root,
                VisualUnknownReason.MULTIPLE_PLAUSIBLE_TARGETS,
                tuple(range(len(need.candidate_ids))),
                "Candidates remain visually ambiguous.",
            )
        selected = next(item for item in candidates if item.ref == selected_ref)
        outcome = ObservationQueryOutcome(
            need.need_id,
            need.purpose,
            ObservationQueryDisposition.OBSERVED,
            (ObservationObservedItem(InputLocator((index_by_ref[selected_ref],)), (selected.target_id,)),),
        )
        return _outcome_only_result(request, need, frame, root, outcome, "Candidate disambiguation evidence.")

    def _text(self, request, frame, structured, root) -> SelectedObservationResult:
        assert self.text_reader is not None
        need = _single_need(request, ObservationPurpose.TEXT_IN_IMAGE)
        candidates, index_by_ref, missing = _candidates(need.subject_ids, structured)
        unknown = [
            ObservationUnknownItem(InputLocator((index,)), VisualUnknownReason.TARGET_NOT_VISIBLE) for index in missing
        ]
        readings = (
            self.text_reader.read(
                VisualTextReadingRequest(
                    need.need_id,
                    frame.image_bytes,
                    (frame.image_width, frame.image_height),
                    need.query_text,
                    candidates,
                )
            )
            if candidates
            else ()
        )
        by_ref = {item.ref: item for item in readings}
        if set(by_ref) != {item.ref for item in candidates} or len(by_ref) != len(readings):
            raise ValueError("text provider must cover current candidates exactly once")
        targets: list[SemanticTarget] = []
        facts: list[StateFact] = []
        proposals: list[EntityAlignmentProposal] = []
        observed: list[ObservationObservedItem] = []
        by_candidate = {item.ref: item for item in candidates}
        observation_id = f"{frame.observation_id}:visual-text"
        for ref, index in index_by_ref.items():
            reading, candidate = by_ref[ref], by_candidate[ref]
            if reading.text is None:
                unknown.append(ObservationUnknownItem(InputLocator((index,)), VisualUnknownReason.TEXT_NOT_LEGIBLE))
                continue
            local_id, fact_id = f"text:{index}", f"fact:{observation_id}:{index}:text_in_image"
            targets.append(SemanticTarget(local_id, candidate.role, candidate.label, {"text_in_image": reading.text}))
            facts.append(StateFact(fact_id, local_id, "text_in_image", reading.text, observation_id))
            proposals.append(
                _alignment(
                    observation_id,
                    local_id,
                    structured.observation_id,
                    candidate.target_id,
                    fact_id,
                    reading.confidence,
                )
            )
            observed.append(ObservationObservedItem(InputLocator((index,)), (candidate.target_id,), (fact_id,)))
        return _semantic_result(
            request,
            need,
            frame,
            root,
            targets,
            facts,
            proposals,
            observed,
            unknown,
            "Bounded text-in-image evidence.",
        )

    def _spatial(self, request, frame, structured, root) -> SelectedObservationResult:
        assert self.spatial_classifier is not None
        need = _single_need(request, ObservationPurpose.SPATIAL_RELATIONSHIP)
        candidates, _index_by_ref, missing = _candidates(need.subject_ids, structured)
        if missing:
            return _unknown_result(
                request,
                need,
                frame,
                root,
                VisualUnknownReason.RELATION_NOT_OBSERVABLE,
                tuple(range(len(need.subject_ids))),
                "Spatial relation is not observable.",
            )
        assessment = self.spatial_classifier.classify(
            VisualSpatialClassificationRequest(
                need.need_id,
                frame.image_bytes,
                (frame.image_width, frame.image_height),
                need.query_text,
                candidates,
            )
        )
        outcome = _boolean_outcome(
            need, need.subject_ids, assessment.truth, VisualUnknownReason.RELATION_NOT_OBSERVABLE
        )
        return _outcome_only_result(request, need, frame, root, outcome, "Spatial relation evidence.")

    def _change(self, request, frame, structured, root) -> SelectedObservationResult:
        assert self.change_classifier is not None
        need = _single_need(request, ObservationPurpose.VISUAL_CHANGE)
        candidates, _index_by_ref, missing = _candidates(need.subject_ids, structured)
        before = self._before_frame
        if missing or before is None or before.viewport != frame.viewport:
            return _unknown_result(
                request,
                need,
                frame,
                root,
                VisualUnknownReason.CHANGE_NOT_DETERMINABLE,
                tuple(range(len(need.subject_ids))),
                "Before/after lineage is unavailable.",
            )
        assessment = self.change_classifier.classify(
            VisualChangeClassificationRequest(
                need.need_id,
                before.image_bytes,
                frame.image_bytes,
                (frame.image_width, frame.image_height),
                need.query_text,
                candidates,
            )
        )
        outcome = _boolean_outcome(
            need, need.subject_ids, assessment.truth, VisualUnknownReason.CHANGE_NOT_DETERMINABLE
        )
        return _outcome_only_result(request, need, frame, root, outcome, "Visual change evidence.")

    def _observe_layer_transition(
        self,
        request: SelectedObservationRequest,
        snapshot: BrowserSnapshot,
        structured: SurfaceObservation,
        root: str,
    ) -> SelectedObservationResult:
        assert self.layer_observer is not None
        assert snapshot.visual_frame is not None
        need = _single_need(request, ObservationPurpose.EFFECT_VERIFICATION)
        before = self._before_frame
        artifact = structured.artifacts.get("unresolved_visual_layer_transition")
        candidate_ids = tuple(artifact.get("candidate_target_ids", ())) if isinstance(artifact, Mapping) else ()
        targets_by_id = {target.target_id: target for target in structured.targets}
        candidates: list[VisualCandidate] = []
        index_by_ref: dict[str, int] = {}
        for input_index, target_id in enumerate(need.subject_ids):
            if target_id not in candidate_ids:
                continue
            target = targets_by_id.get(target_id)
            try:
                layer_index = int(target_id.rsplit(":", 1)[1])
                layer = snapshot.layers[layer_index]
            except (IndexError, TypeError, ValueError):
                continue
            if target is None or layer.kind is not BrowserLayerKind.GEOMETRIC_OVERLAY:
                continue
            ref = f"E{len(candidates) + 1}"
            candidates.append(
                VisualCandidate(
                    ref,
                    target_id,
                    target.role,
                    target.label,
                    layer.bbox,
                    target.state,
                )
            )
            index_by_ref[ref] = input_index
        frame = snapshot.visual_frame
        if (
            before is None
            or before.viewport != frame.viewport
            or not candidates
            or len(candidates) != len(need.subject_ids)
        ):
            return _unknown_result(
                request,
                need,
                frame,
                root,
                VisualUnknownReason.CHANGE_NOT_DETERMINABLE,
                tuple(range(len(need.subject_ids))),
                "Visual layer transition is not determinable.",
            )
        assessments = self.layer_observer.observe_layers(
            VisualLayerTransitionRequest(
                need.need_id,
                before.image_bytes,
                frame.image_bytes,
                (frame.image_width, frame.image_height),
                tuple(candidates),
            )
        )
        by_ref = {item.ref: item for item in assessments}
        if set(by_ref) != {item.ref for item in candidates} or len(by_ref) != len(assessments):
            raise ValueError("layer observer must cover current candidates exactly once")
        observation_id = f"{frame.observation_id}:visual-layer-change"
        visual_targets: list[SemanticTarget] = []
        facts: list[StateFact] = []
        proposals: list[EntityAlignmentProposal] = []
        observed: list[ObservationObservedItem] = []
        unknown: list[ObservationUnknownItem] = []
        for candidate in candidates:
            assessment = by_ref[candidate.ref]
            input_index = index_by_ref[candidate.ref]
            if assessment.description is None:
                unknown.append(
                    ObservationUnknownItem(
                        InputLocator((input_index,)),
                        VisualUnknownReason.CHANGE_NOT_DETERMINABLE,
                    )
                )
                continue
            local_id = f"layer-change:{input_index}"
            state = {
                "visual_change": "appeared",
                "visual_layer_description": assessment.description,
                "visual_layer_role": assessment.role.value,
                "occludes_primary_surface": assessment.occludes_primary_surface,
                "confidence": assessment.confidence,
            }
            visual_targets.append(
                SemanticTarget(
                    local_id,
                    candidate.role,
                    assessment.description,
                    state,
                )
            )
            local_facts = tuple(
                StateFact(
                    f"fact:{observation_id}:{input_index}:{predicate}",
                    local_id,
                    predicate,
                    value,
                    observation_id,
                )
                for predicate, value in state.items()
            )
            facts.extend(local_facts)
            proposals.append(
                _alignment(
                    observation_id,
                    local_id,
                    structured.observation_id,
                    candidate.target_id,
                    local_facts[0].fact_id,
                    assessment.confidence,
                )
            )
            observed.append(
                ObservationObservedItem(
                    InputLocator((input_index,)),
                    (candidate.target_id,),
                    tuple(item.fact_id for item in local_facts),
                )
            )
        return _semantic_result(
            request,
            need,
            frame,
            root,
            visual_targets,
            facts,
            proposals,
            observed,
            unknown,
            "Bounded visual interpretation of a newly appeared overlay.",
        )

    def is_current(self, request: BoundActionRequest) -> bool:
        if request.binding.surface == "dom":
            return self._dom.is_current(request)
        if request.binding.surface == "visual":
            return self._visual.is_current(request)
        return False

    async def execute(self, request: BoundActionRequest) -> ActionResult:
        before_frame: VisualFrame | None = None
        before_layers = self._current_layers
        if self.layer_observer is not None:
            try:
                before_frame = self.session.capture_visual_frame(
                    f"{request.binding.source_observation_id}:before-action"
                )
            except Exception:
                before_frame = None
        if request.binding.surface == "dom":
            result = await self._dom.execute(request)
        else:
            result = await self._visual.execute(request)
        if result.dispatch_status is not DispatchStatus.NOT_SENT:
            self._before_frame = before_frame or self._current_frame
            self._before_layers = before_layers
        return result


def browser_surface_from_environment(
    session: BrowserSession,
    environment: Mapping[str, str],
) -> DomSurfaceAdapter | BrowserSessionSurfaceBundle:
    """Compose one product browser owner from an explicitly selected visual profile."""

    if not environment.get("LLM_VISUAL_PROFILE", "").strip():
        return DomSurfaceAdapter(session)
    inference = pydantic_ai_visual_inference_from_environment(environment)
    text_reader = visual_semantic_classifier_from_environment(
        environment,
        inference=inference,
        role=VisualSemanticRole.TEXT,
    )
    spatial_classifier = visual_semantic_classifier_from_environment(
        environment,
        inference=inference,
        role=VisualSemanticRole.SPATIAL,
    )
    change_classifier = visual_semantic_classifier_from_environment(
        environment,
        inference=inference,
        role=VisualSemanticRole.CHANGE,
    )
    layer_observer = visual_semantic_classifier_from_environment(
        environment,
        inference=inference,
        role=VisualSemanticRole.LAYER_CHANGE,
    )
    return BrowserSessionSurfaceBundle(
        session,
        visual_region_proposer_from_environment(environment, inference=inference),
        visual_grounder_from_environment(environment, inference=inference),
        visual_candidate_disambiguator_from_environment(environment, inference=inference),
        visual_predicate_classifier_from_environment(environment, inference=inference),
        text_reader,
        spatial_classifier,
        change_classifier,
        layer_observer,
    )


def _layer_signature(layer: BrowserLayer) -> tuple[str, int, int, int, int]:
    return (
        layer.kind.value,
        *(round(value / 8) for value in layer.bbox),
    )


def _visual_purpose(request: SelectedObservationRequest) -> ObservationPurpose:
    purposes = {item.purpose for item in request.needs}
    for purpose in (
        ObservationPurpose.TARGET_DISAMBIGUATION,
        ObservationPurpose.VISUAL_PROPERTY,
        ObservationPurpose.TEXT_IN_IMAGE,
        ObservationPurpose.SPATIAL_RELATIONSHIP,
        ObservationPurpose.VISUAL_CHANGE,
        ObservationPurpose.EFFECT_VERIFICATION,
        ObservationPurpose.POINT_GROUNDING,
        ObservationPurpose.ENTITY_DISCOVERY,
        ObservationPurpose.WORLD_GROUNDING,
    ):
        if purpose in purposes:
            return purpose
    raise ValueError("visual source received no supported purpose")


def _single_need(request: SelectedObservationRequest, purpose: ObservationPurpose):
    needs = tuple(item for item in request.needs if item.purpose is purpose)
    if len(needs) != 1:
        raise ValueError(f"visual source requires one {purpose.value} need")
    return needs[0]


def _candidates(subject_ids, structured):
    targets = {item.target_id: item for item in structured.targets}
    boxes = {region.target_id: region.bbox for media in structured.media for region in media.grounding_regions}
    candidates, index_by_ref, missing = [], {}, []
    for index, subject_id in enumerate(subject_ids):
        target, bbox = targets.get(subject_id), boxes.get(subject_id)
        if target is None or bbox is None:
            missing.append(index)
            continue
        ref = f"E{len(candidates) + 1}"
        candidates.append(VisualCandidate(ref, subject_id, target.role, target.label, bbox, target.state))
        index_by_ref[ref] = index
    return tuple(candidates), index_by_ref, tuple(missing)


def _alignment(source_id, local_id, structured_id, target_id, evidence_ref, confidence):
    return EntityAlignmentProposal(
        f"proposal:{source_id}:{local_id}",
        SourceEntityEndpoint(source_id, local_id),
        SourceEntityEndpoint(structured_id, target_id),
        EntityAlignmentBasis.EXPLICIT_PROVIDER_CORRESPONDENCE,
        (evidence_ref,),
        confidence,
    )


def _semantic_source(frame, root, targets=(), facts=(), proposals=(), summary="Visual evidence."):
    observation_id = next(
        (item.source_id for item in facts),
        f"{frame.observation_id}:visual-semantic",
    )
    media = ObservationMedia(
        "visual-screenshot",
        "screenshot",
        "image/png",
        frame.image_bytes,
        (),
        capture_group_id=root,
        variant=ObservationMediaVariant.RAW,
        dimensions=(frame.image_width, frame.image_height),
        coordinate_space_id="browser-session:viewport_pixels",
    )
    return SurfaceObservation(
        observation_id,
        "visual",
        frame.source_revision,
        ObservationSourceProfile.visual(),
        tuple(targets),
        tuple(facts),
        (),
        CoverageState.COMPLETE,
        {"screenshot_semantic_state": {"public_summary": summary}},
        media=(media,),
        acquisition_root_id=root,
        alignment_proposals=tuple(proposals),
    )


def _semantic_result(request, need, frame, root, targets, facts, proposals, observed, unknown, summary):
    outcome = _completed_outcome(need, tuple(observed), tuple(unknown))
    source = _semantic_source(frame, root, targets, facts, proposals, summary)
    return SelectedObservationResult.acquired(
        request, source, fulfilled_need_ids=(need.need_id,), query_outcomes=(outcome,)
    )


def _outcome_only_result(request, need, frame, root, outcome, summary):
    return SelectedObservationResult.acquired(
        request,
        _semantic_source(frame, root, summary=summary),
        fulfilled_need_ids=(need.need_id,),
        query_outcomes=(outcome,),
    )


def _unknown_result(request, need, frame, root, reason, indices, summary):
    outcome = ObservationQueryOutcome(
        need.need_id,
        need.purpose,
        ObservationQueryDisposition.UNKNOWN,
        unknown_items=(ObservationUnknownItem(InputLocator(indices), reason),),
    )
    return _outcome_only_result(request, need, frame, root, outcome, summary)


def _completed_outcome(need, observed, unknown):
    disposition = (
        ObservationQueryDisposition.PARTIAL
        if observed and unknown
        else ObservationQueryDisposition.OBSERVED
        if observed
        else ObservationQueryDisposition.UNKNOWN
    )
    return ObservationQueryOutcome(need.need_id, need.purpose, disposition, observed, unknown)


def _boolean_outcome(need, subject_ids, truth, reason):
    locator = InputLocator(tuple(range(len(subject_ids))))
    if truth is PredicateTruth.UNKNOWN:
        return ObservationQueryOutcome(
            need.need_id,
            need.purpose,
            ObservationQueryDisposition.UNKNOWN,
            unknown_items=(ObservationUnknownItem(locator, reason),),
        )
    return ObservationQueryOutcome(
        need.need_id,
        need.purpose,
        ObservationQueryDisposition.OBSERVED,
        (ObservationObservedItem(locator, tuple(subject_ids)),),
    )

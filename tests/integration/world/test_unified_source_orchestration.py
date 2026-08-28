from __future__ import annotations

import asyncio
import io
from dataclasses import FrozenInstanceError, dataclass, field, replace

import pytest
from PIL import Image

from affordance_runtime.actions import (
    ActionBinder,
    ActionBinding,
    ActionRisk,
    ActionSpaceBuilder,
    RouteSelectionCode,
    RouteSelector,
)
from affordance_runtime.agent.context.budgets import ContextProjectionBudget
from affordance_runtime.agent.context.grounding_projection import GroundingProjection
from affordance_runtime.agent.context.world_projection import project_model_world as _project_model_world
from affordance_runtime.execution import (
    ActionDispatchCancelled,
    ActionError,
    ActionResult,
    DispatchStatus,
    ExecutionCancelled,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    AcquisitionCancelled,
    AcquisitionOrigin,
    AcquisitionStage,
    AcquisitionStatus,
    CoverageState,
    EntityAlignmentBasis,
    EntityAlignmentDisposition,
    EntityAlignmentProposal,
    EntityAllocation,
    FusionStatus,
    ObservationAssurance,
    ObservationGroundingRegion,
    ObservationMedia,
    ObservationMediaVariant,
    ObservationModality,
    ObservationNeed,
    ObservationOffer,
    ObservationOrchestrator,
    ObservationPurpose,
    ObservationRequestKind,
    ObservationSourceProfile,
    SelectedObservationResult,
    SemanticTarget,
    SourceAcquisitionStatus,
    SourceEntityEndpoint,
    StateFact,
    SurfaceObservation,
    WorldFusion,
    WorldFusionResult,
    WorldObservationRequest,
    selected_observation_requests,
)
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment
from tests.support.agent.core_loop_support import _world
from tests.support.canonical_world import canonical_world
from tests.support.observation_acquisition import acquired_acquisition


def project_model_world(observation, budget, *args, **kwargs):
    return _project_model_world(
        observation, budget, *args, canonical_projection=canonical_world(observation), **kwargs
    )


def _task() -> TaskGoal:
    return TaskGoal(
        "task:any-name",
        "Enable it",
        allowed_effects=("enabled", "shared_state_enabled"),
        success_criteria=({"id": "enabled", "predicate": "enabled", "value": True},),
        risk_profile=RiskProfile.LOW,
    )


def _need(
    purpose: ObservationPurpose,
    modality: ObservationModality,
    assurance: ObservationAssurance,
) -> ObservationNeed:
    return ObservationNeed(
        f"test:{purpose.value}",
        purpose,
        required_modality=modality,
        required_assurance=assurance,
    )


def _source(
    surface: str,
    *,
    profile: ObservationSourceProfile | None = None,
    local_id: str = "target",
    observation_id: str = "",
    align_to: SourceEntityEndpoint | None = None,
    value: object = False,
    confidence: float = 1.0,
    media: tuple[ObservationMedia, ...] = (),
    acquisition_root_id: str = "root:shared",
) -> SurfaceObservation:
    observation_id = observation_id or f"{surface}:obs"
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
        alignment_proposals=(
            EntityAlignmentProposal(
                f"proposal:{observation_id}:{local_id}",
                SourceEntityEndpoint(observation_id, local_id),
                align_to,
                EntityAlignmentBasis.EXPLICIT_PROVIDER_CORRESPONDENCE,
                (f"evidence:{observation_id}:{local_id}",),
                confidence,
            ),
        )
        if align_to is not None
        else (),
        visual_only_target_ids=(local_id,)
        if (profile or ObservationSourceProfile.dom()).modality.value == "visual" and align_to is None
        else (),
    )


def test_selection_skips_expensive_visual_until_typed_visual_need() -> None:
    selector = ObservationOrchestrator()
    offers = (
        ObservationOffer("dom", "structural", "structural", "low"),
        ObservationOffer("visual", "visual", "weak", "high"),
    )

    ordinary = selector.select(
        offers,
        WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, "ordinary"),
    )
    visual = selector.select(
        offers,
        WorldObservationRequest(
            ObservationRequestKind.POLICY_REQUEST,
            "spatial gap",
            (_need(ObservationPurpose.ENTITY_DISCOVERY, ObservationModality.VISUAL, ObservationAssurance.WEAK),),
        ),
    )

    assert [item.source for item in ordinary.plan.selections] == ["dom"]  # type: ignore[union-attr]
    assert [item.source for item in visual.plan.selections] == ["dom", "visual"]  # type: ignore[union-attr]
    assert visual.plan.selections[1].requirement.value == "required"  # type: ignore[union-attr]


def test_visual_only_semantic_need_keeps_a_fresh_structural_baseline() -> None:
    selector = ObservationOrchestrator()
    offers = (
        ObservationOffer("dom", "structural", "structural", "low"),
        ObservationOffer("visual", "visual", "weak", "high"),
    )
    selected = selector.select(
        offers,
        WorldObservationRequest(
            ObservationRequestKind.POLICY_REQUEST,
            "discover entities not represented structurally",
            (
                ObservationNeed(
                    "test:open-world",
                    ObservationPurpose.ENTITY_DISCOVERY,
                    required_assurance=ObservationAssurance.WEAK,
                ),
            ),
        ),
    )

    assert selected.plan is not None
    assert [item.source for item in selected.plan.selections] == ["dom", "visual"]
    assert selected.plan.selections[0].reason_code == "structured_baseline"


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
            (
                _need(
                    ObservationPurpose.CRITERION_VERIFICATION,
                    ObservationModality.ENVIRONMENT_STATE,
                    ObservationAssurance.AUTHORITATIVE,
                ),
            ),
        ),
    )

    assert selected.plan is not None
    assert [item.source for item in selected.plan.selections] == ["wot"]
    assert [item.requirement.value for item in selected.plan.selections] == ["required"]


def test_selection_is_offer_order_invariant_and_plan_is_immutable() -> None:
    selector = ObservationOrchestrator()
    offers = (
        ObservationOffer("dom", "structural", "structural", "low"),
        ObservationOffer("visual", "visual", "weak", "high"),
    )
    request = WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        "discover visual entity",
        (_need(ObservationPurpose.ENTITY_DISCOVERY, ObservationModality.VISUAL, ObservationAssurance.WEAK),),
    )

    forward = selector.select(offers, request)
    reverse = selector.select(tuple(reversed(offers)), request)

    assert forward == reverse
    assert forward.plan is not None
    assert forward.plan.need_ids == (
        "baseline:test:entity_discovery",
        "test:entity_discovery",
    )
    assert [item.source for item in forward.plan.unselected] == []
    with pytest.raises(FrozenInstanceError):
        forward.plan.acquisition_budget = 3  # type: ignore[misc]


def test_first_version_budget_fails_closed_before_a_third_source() -> None:
    selector = ObservationOrchestrator()
    offers = (
        ObservationOffer("dom", "structural", "structural", "low"),
        ObservationOffer("state", "environment_state", "authoritative", "medium"),
        ObservationOffer("visual", "visual", "weak", "high"),
    )
    request = WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        "three independent evidence needs",
        (
            ObservationNeed(
                "need:structural",
                ObservationPurpose.WORLD_GROUNDING,
                required_modality=ObservationModality.STRUCTURAL,
                required_assurance=ObservationAssurance.STRUCTURAL,
            ),
            ObservationNeed(
                "need:state",
                ObservationPurpose.CRITERION_VERIFICATION,
                required_modality=ObservationModality.ENVIRONMENT_STATE,
                required_assurance=ObservationAssurance.AUTHORITATIVE,
            ),
            ObservationNeed(
                "need:visual",
                ObservationPurpose.ENTITY_DISCOVERY,
                required_modality=ObservationModality.VISUAL,
                required_assurance=ObservationAssurance.WEAK,
            ),
        ),
    )

    selected = selector.select(offers, request)

    assert selected.plan is None
    assert selected.status is AcquisitionStatus.CAPABILITY_UNAVAILABLE
    assert selected.reason_code == "source_budget_exhausted"


def test_candidate_plurality_does_not_trigger_visual_before_policy_intent() -> None:
    structured = _source("dom")
    second_target = replace(structured.targets[0], target_id="target:second")
    second_binding = replace(
        structured.bindings[0],
        binding_id="dom:binding:second",
        target_id=second_target.target_id,
        source_target_id=second_target.target_id,
    )
    structured = replace(
        structured,
        targets=structured.targets + (second_target,),
        bindings=structured.bindings + (second_binding,),
    )
    offers = (
        ObservationOffer("dom", "structural", "structural", "low"),
        ObservationOffer("visual", "visual", "weak", "high"),
    )

    selected = ObservationOrchestrator().select_after_baseline(
        offers,
        WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, "ordinary"),
        structured,
        terminal=False,
    )

    assert selected.plan is not None
    assert [item.source for item in selected.plan.selections] == ["dom"]


def test_typed_structural_truncation_does_not_infer_a_visual_query() -> None:
    structured = replace(_source("dom"), coverage=CoverageState.TRUNCATED)
    offers = (
        ObservationOffer("dom", "structural", "structural", "low"),
        ObservationOffer(
            "visual",
            "visual",
            "weak",
            "high",
            supported_purposes=(ObservationPurpose.ENTITY_DISCOVERY,),
        ),
    )

    selected = ObservationOrchestrator().select_after_baseline(
        offers,
        WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, "ordinary"),
        structured,
        terminal=False,
    )

    assert selected.plan is not None
    assert [item.source for item in selected.plan.selections] == ["dom"]
    assert all(item.need_id != "residual:entity_discovery" for item in selected.plan.needs)
    assert all(not item.need_id.startswith("baseline:") for item in selected.plan.needs)


def test_staged_post_action_does_not_turn_generic_truncation_into_visual_fallback() -> None:
    async def scenario() -> None:
        dom = OfferedAdapter(
            "dom",
            ObservationOffer("dom", "structural", "structural", "low"),
            replace(_source("dom"), coverage=CoverageState.TRUNCATED),
        )
        visual = OfferedAdapter(
            "visual",
            ObservationOffer(
                "visual",
                "visual",
                "weak",
                "high",
                supported_purposes=(ObservationPurpose.ENTITY_DISCOVERY,),
            ),
            _source("visual", profile=ObservationSourceProfile.visual()),
        )
        environment = UnifiedWorldEnvironment((dom, visual))
        await environment.reset(_task())
        verification = ObservationNeed(
            "verification:staged-post-action",
            ObservationPurpose.EFFECT_VERIFICATION,
            required_assurance=ObservationAssurance.WEAK,
        )

        acquired = await environment.capture(WorldObservationRequest(
            ObservationRequestKind.POST_ACTION_FALLBACK,
            "post action with a partial structural baseline",
            (verification,),
        ))

        assert acquired.status is AcquisitionStatus.ACQUIRED
        assert {
            activation.request.source: tuple(item.need_id for item in activation.request.needs)
            for activation in acquired.activations
        } == {
            "dom": (verification.need_id,),
        }
        assert all(
            {item.need_id for item in activation.request.needs}
            == {item.need_id for item in activation.result.need_results}
            for activation in acquired.activations
        )

    asyncio.run(scenario())


def test_public_state_distinction_closes_ambiguity_without_visual_source() -> None:
    structured = _source("dom")
    second_target = replace(structured.targets[0], target_id="target:second", state={"selected": True})
    second_binding = replace(
        structured.bindings[0],
        binding_id="dom:binding:second",
        target_id=second_target.target_id,
        source_target_id=second_target.target_id,
    )
    structured = replace(
        structured,
        targets=structured.targets + (second_target,),
        bindings=structured.bindings + (second_binding,),
    )
    offers = (
        ObservationOffer("dom", "structural", "structural", "low"),
        ObservationOffer("visual", "visual", "weak", "high"),
    )

    selected = ObservationOrchestrator().select_after_baseline(
        offers,
        WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, "ordinary"),
        structured,
        terminal=False,
    )

    assert selected.plan is not None
    assert [item.source for item in selected.plan.selections] == ["dom"]


@dataclass
class OfferedAdapter:
    surface: str
    offer: ObservationOffer
    observation: SurfaceObservation | None
    reset_calls: int = 0
    observe_calls: int = 0
    prepared: bool = False
    requests: list = field(default_factory=list)
    owns_physical_reset: bool = True
    physical_id: str = ""

    @property
    def physical_environment_id(self):
        return self.physical_id or f"fake:{self.surface}"

    @property
    def observation_offers(self):
        return (self.offer,)

    def initialize_task(self, task):
        del task
        self.prepared = True

    async def reset_physical(self):
        self.reset_calls += 1

    async def acquire(self, request):
        self.observe_calls += 1
        self.requests.append(request)
        if self.observation is None:
            raise RuntimeError("unavailable")
        return SelectedObservationResult.acquired(
            request,
            self.observation,
            fulfilled_need_ids=tuple(item.need_id for item in request.needs),
        )

    async def execute(self, request):
        return ActionResult(
            request.request_id,
            DispatchStatus.SENT,
            self.surface,
            True,
        )


@dataclass
class NoOfferAdapter:
    surface: str = "undeclared"
    reset_calls: int = 0
    observe_calls: int = 0
    owns_physical_reset: bool = True

    @property
    def physical_environment_id(self):
        return "fake:undeclared"

    @property
    def observation_offers(self):
        return ()

    def initialize_task(self, task):
        del task

    async def reset_physical(self):
        self.reset_calls += 1

    async def acquire(self, request):
        self.observe_calls += 1
        return SelectedObservationResult.acquired(
            request,
            _source(self.surface),
            fulfilled_need_ids=tuple(item.need_id for item in request.needs),
        )

    async def execute(self, request):
        raise AssertionError(f"unexpected execution: {request.request_id}")


def test_missing_offer_fails_closed_without_observing_every_adapter() -> None:
    async def scenario() -> None:
        adapter = NoOfferAdapter()
        environment = UnifiedWorldEnvironment((adapter,))

        acquired = await environment.reset(_task())

        assert acquired.status is AcquisitionStatus.CAPABILITY_UNAVAILABLE
        assert acquired.reason_code == "no_source_offer"
        assert adapter.reset_calls == adapter.observe_calls == 0

    asyncio.run(scenario())


def test_offer_source_alias_resolves_through_explicit_provider_registration() -> None:
    async def scenario() -> None:
        adapter = OfferedAdapter(
            "dom",
            ObservationOffer("semantic_dom", "structural", "structural", "low"),
            _source("dom"),
        )
        acquired = await UnifiedWorldEnvironment((adapter,)).reset(_task())

        assert acquired.status is AcquisitionStatus.ACQUIRED
        assert adapter.observe_calls == 1
        assert acquired.source_results[0].source == "semantic_dom"
        assert acquired.observation is not None
        assert acquired.observation.sources[0].surface == "dom"

    asyncio.run(scenario())


def test_coordinator_closes_initialization_provider_and_malformed_failures() -> None:
    class InitializationFailure(OfferedAdapter):
        def initialize_task(self, task):
            del task
            raise RuntimeError("private initialization detail")

    class ProviderFailure(OfferedAdapter):
        async def acquire(self, request):
            del request
            raise RuntimeError("private provider detail")

    class MalformedProvider(OfferedAdapter):
        async def acquire(self, request):
            del request
            return object()

    async def scenario() -> None:
        offer = ObservationOffer("dom", "structural", "structural", "low")
        initialization = await UnifiedWorldEnvironment((InitializationFailure("dom", offer, _source("dom")),)).reset(
            _task()
        )
        provider = await UnifiedWorldEnvironment((ProviderFailure("dom", offer, _source("dom")),)).reset(_task())
        malformed = await UnifiedWorldEnvironment((MalformedProvider("dom", offer, _source("dom")),)).reset(_task())

        assert initialization.stage is AcquisitionStage.INITIALIZATION_FAILED
        assert provider.stage is AcquisitionStage.SOURCE_ACQUISITION_FAILED
        assert malformed.stage is AcquisitionStage.SOURCE_ACQUISITION_FAILED
        assert malformed.activations[0].result.reason_code == "source_result_contract_mismatch"

    asyncio.run(scenario())


def test_coordinator_preserves_cancellation_and_fusion_failure() -> None:
    class CancellingProvider(OfferedAdapter):
        cancel = False

        async def acquire(self, request):
            if self.cancel:
                raise asyncio.CancelledError
            return await super().acquire(request)

    class FailedFusion:
        def fuse(self, sources):
            del sources
            return WorldFusionResult(FusionStatus.INCONCLUSIVE, None, "held_out_fusion_failure")

    async def scenario() -> None:
        offer = ObservationOffer("dom", "structural", "structural", "low")
        adapter = CancellingProvider("dom", offer, _source("dom"))
        environment = UnifiedWorldEnvironment((adapter,))
        await environment.reset(_task())
        adapter.cancel = True
        with pytest.raises(AcquisitionCancelled) as cancelled:
            await environment.capture(WorldObservationRequest(ObservationRequestKind.WAIT_REFRESH, "cancel"))
        assert cancelled.value.acquisition.stage is AcquisitionStage.CANCELLED
        assert cancelled.value.acquisition.status is AcquisitionStatus.CANCELLED

        fusion = await UnifiedWorldEnvironment(
            (OfferedAdapter("dom", offer, _source("dom")),),
            world_fusion=FailedFusion(),  # type: ignore[arg-type]
        ).reset(_task())
        assert fusion.stage is AcquisitionStage.FUSION_FAILED
        assert fusion.fusion_outcome is not None
        assert fusion.fusion_outcome.reason_code == "held_out_fusion_failure"

    asyncio.run(scenario())


def test_grouped_cancellation_closes_later_selected_groups_without_calling_them() -> None:
    @dataclass
    class GroupedAdapter(OfferedAdapter):
        cancel: bool = False
        grouped_calls: int = 0

        async def acquire_group(self, requests):
            self.grouped_calls += 1
            if self.cancel:
                raise asyncio.CancelledError
            return tuple(
                SelectedObservationResult.acquired(
                    request,
                    self.observation,
                    fulfilled_need_ids=tuple(item.need_id for item in request.needs),
                )
                for request in requests
            )

    async def scenario() -> None:
        discovery = GroupedAdapter(
            "visual-a-discovery",
            ObservationOffer(
                "visual-a-discovery",
                "visual",
                "weak",
                "low",
                "group:discovery",
                (ObservationPurpose.ENTITY_DISCOVERY,),
            ),
            _source("visual-a-discovery", profile=ObservationSourceProfile.visual()),
        )
        disambiguation = GroupedAdapter(
            "visual-z-disambiguation",
            ObservationOffer(
                "visual-z-disambiguation",
                "visual",
                "weak",
                "low",
                "group:disambiguation",
                (ObservationPurpose.TARGET_DISAMBIGUATION,),
            ),
            _source("visual-z-disambiguation", profile=ObservationSourceProfile.visual()),
        )
        environment = UnifiedWorldEnvironment((discovery, disambiguation))
        await environment.reset(_task())
        discovery.cancel = True
        calls_before = disambiguation.grouped_calls

        with pytest.raises(AcquisitionCancelled) as cancelled:
            await environment.capture(
                WorldObservationRequest(
                    ObservationRequestKind.POLICY_REQUEST,
                    "two independent visual needs",
                    (
                        _need(
                            ObservationPurpose.ENTITY_DISCOVERY,
                            ObservationModality.VISUAL,
                            ObservationAssurance.WEAK,
                        ),
                        _need(
                            ObservationPurpose.TARGET_DISAMBIGUATION,
                            ObservationModality.VISUAL,
                            ObservationAssurance.WEAK,
                        ),
                    ),
                )
            )

        acquisition = cancelled.value.acquisition
        assert acquisition.stage is AcquisitionStage.CANCELLED
        assert {item.request.source for item in acquisition.activations} == {
            "visual-a-discovery",
            "visual-z-disambiguation",
        }
        assert all(item.result.status is SourceAcquisitionStatus.CANCELLED for item in acquisition.activations)
        assert disambiguation.grouped_calls == calls_before

        structural = GroupedAdapter(
            "dom-a",
            ObservationOffer(
                "dom-a",
                "structural",
                "structural",
                "low",
                "group:dom",
                (ObservationPurpose.WORLD_GROUNDING,),
            ),
            _source("dom-a"),
        )
        deferred_visual = GroupedAdapter(
            "visual-z",
            ObservationOffer(
                "visual-z",
                "visual",
                "weak",
                "high",
                "group:visual",
                (ObservationPurpose.TARGET_DISAMBIGUATION,),
            ),
            _source("visual-z", profile=ObservationSourceProfile.visual()),
        )
        staged = UnifiedWorldEnvironment((structural, deferred_visual))
        await staged.reset(_task())
        structural.cancel = True
        visual_calls_before = deferred_visual.grouped_calls

        with pytest.raises(AcquisitionCancelled) as staged_cancelled:
            await staged.capture(
                WorldObservationRequest(
                    ObservationRequestKind.POLICY_REQUEST,
                    "structural first with deferred visual",
                    (
                        _need(
                            ObservationPurpose.WORLD_GROUNDING,
                            ObservationModality.STRUCTURAL,
                            ObservationAssurance.STRUCTURAL,
                        ),
                        _need(
                            ObservationPurpose.TARGET_DISAMBIGUATION,
                            ObservationModality.VISUAL,
                            ObservationAssurance.WEAK,
                        ),
                    ),
                )
            )

        staged_acquisition = staged_cancelled.value.acquisition
        assert {item.request.source for item in staged_acquisition.activations} == {
            "dom-a",
            "visual-z",
        }
        assert all(item.result.status is SourceAcquisitionStatus.CANCELLED for item in staged_acquisition.activations)
        assert deferred_visual.grouped_calls == visual_calls_before

    asyncio.run(scenario())


def test_late_activated_adapter_is_initialized_and_its_physical_environment_reset() -> None:
    async def scenario() -> None:
        dom = OfferedAdapter(
            "dom",
            ObservationOffer("dom", "structural", "structural", "low"),
            _source("dom"),
        )
        visual = OfferedAdapter(
            "visual",
            ObservationOffer("visual", "visual", "weak", "high"),
            _source("visual", profile=ObservationSourceProfile.visual()),
        )
        environment = UnifiedWorldEnvironment((dom, visual))

        initial = await environment.reset(_task())
        acquired = await environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "late visual activation",
                (
                    _need(
                        ObservationPurpose.ENTITY_DISCOVERY,
                        ObservationModality.VISUAL,
                        ObservationAssurance.WEAK,
                    ),
                ),
            )
        )

        assert initial.status is AcquisitionStatus.ACQUIRED
        assert dom.prepared is visual.prepared is True
        assert dom.reset_calls == visual.reset_calls == 1
        assert acquired.status is AcquisitionStatus.ACQUIRED
        assert visual.observe_calls == 1

    asyncio.run(scenario())


def test_shared_physical_environment_uses_its_explicit_reset_owner() -> None:
    async def scenario() -> None:
        dom = OfferedAdapter(
            "dom",
            ObservationOffer("dom", "structural", "structural", "low"),
            _source("dom"),
            owns_physical_reset=True,
            physical_id="fixture:shared-browser",
        )
        visual = OfferedAdapter(
            "visual",
            ObservationOffer("visual", "visual", "weak", "high"),
            _source("visual", profile=ObservationSourceProfile.visual()),
            owns_physical_reset=False,
            physical_id="fixture:shared-browser",
        )

        acquired = await UnifiedWorldEnvironment((visual, dom)).reset(_task())

        assert acquired.status is AcquisitionStatus.ACQUIRED
        assert dom.prepared is visual.prepared is True
        assert dom.reset_calls == 1
        assert visual.reset_calls == 0

    asyncio.run(scenario())


def test_acquired_source_can_truthfully_leave_one_selected_need_unfulfilled() -> None:
    needs = (
        _need(ObservationPurpose.ENTITY_DISCOVERY, ObservationModality.VISUAL, ObservationAssurance.WEAK),
        ObservationNeed(
            "test:visual_property",
            ObservationPurpose.VISUAL_PROPERTY,
            required_modality=ObservationModality.VISUAL,
            required_assurance=ObservationAssurance.WEAK,
            evidence_property="color",
        ),
    )
    offer = ObservationOffer(
        "visual",
        "visual",
        "weak",
        "high",
        supported_purposes=(
            ObservationPurpose.ENTITY_DISCOVERY,
            ObservationPurpose.VISUAL_PROPERTY,
        ),
    )
    request = WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        "two semantic needs",
        needs,
    )
    outcome = ObservationOrchestrator().select((offer,), request)
    assert outcome.plan is not None
    selected_request = selected_observation_requests(outcome.plan, request, (offer,), "acquisition:partial")[0]

    result = SelectedObservationResult.acquired(
        selected_request,
        _source("visual", profile=ObservationSourceProfile.visual()),
        fulfilled_need_ids=(needs[0].need_id,),
        unfulfilled_reason_code="visual_property_not_observed",
    )

    assert result.status is SourceAcquisitionStatus.ACQUIRED
    assert result.fulfilled_need_ids == (needs[0].need_id,)
    assert result.unfulfilled_need_ids == (needs[1].need_id,)


def test_public_acquisition_rejects_a_plan_without_conserved_source_results() -> None:
    request = WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        "public invariant",
    )
    outcome = ObservationOrchestrator().select(
        (ObservationOffer("dom", "structural", "structural", "low"),),
        request,
    )
    assert outcome.plan is not None

    acquired = acquired_acquisition(
        _world("contract", False),
        AcquisitionOrigin.INDEPENDENT_CAPTURE,
    )
    with pytest.raises(ValueError, match="illegal terminal stage shape"):
        replace(acquired, activations=())


def test_generic_environment_does_not_infer_disambiguation_from_duplicate_controls() -> None:
    async def scenario() -> None:
        structured = _source("dom")
        second_target = replace(structured.targets[0], target_id="target:second")
        second_binding = replace(
            structured.bindings[0],
            binding_id="dom:binding:second",
            target_id=second_target.target_id,
            source_target_id=second_target.target_id,
        )
        structured = replace(
            structured,
            targets=structured.targets + (second_target,),
            bindings=structured.bindings + (second_binding,),
        )
        dom = OfferedAdapter(
            "dom",
            ObservationOffer("dom", "structural", "structural", "low"),
            _source("dom"),
        )
        visual = OfferedAdapter(
            "visual",
            ObservationOffer("visual", "visual", "weak", "high"),
            _source("visual", profile=ObservationSourceProfile.visual()),
        )
        environment = UnifiedWorldEnvironment((dom, visual))
        await environment.reset(_task())
        dom.observation = structured

        acquired = await environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "held out ambiguity",
            )
        )

        assert acquired.status is AcquisitionStatus.ACQUIRED
        assert dom.observe_calls == 2 and visual.observe_calls == 0

    asyncio.run(scenario())


def test_required_visual_need_failure_returns_typed_failed_acquisition() -> None:
    async def scenario() -> None:
        dom = OfferedAdapter(
            "dom",
            ObservationOffer("dom", "structural", "structural", "low"),
            _source("dom"),
        )
        visual = OfferedAdapter(
            "visual",
            ObservationOffer("visual", "visual", "weak", "high"),
            None,
        )
        environment = UnifiedWorldEnvironment((dom, visual))
        initial = await environment.reset(_task())
        assert dom.observe_calls == 1 and visual.observe_calls == 0
        assert [item.status for item in initial.source_results] == [
            SourceAcquisitionStatus.ACQUIRED,
            SourceAcquisitionStatus.NOT_ACQUIRED,
        ]
        acquired = await environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "spatial gap",
                (_need(ObservationPurpose.ENTITY_DISCOVERY, ObservationModality.VISUAL, ObservationAssurance.WEAK),),
            )
        )

        assert acquired.status is AcquisitionStatus.FAILED
        assert acquired.reason_code == "required_source_exhausted"
        assert acquired.observation is None
        assert [item.status for item in acquired.source_results] == [
            SourceAcquisitionStatus.ACQUIRED,
            SourceAcquisitionStatus.FAILED,
        ]

    asyncio.run(scenario())


def test_post_action_visual_route_does_not_inherit_prior_structural_selection() -> None:
    async def scenario() -> None:
        dom = OfferedAdapter(
            "dom",
            ObservationOffer("dom", "structural", "structural", "low"),
            _source("dom"),
        )
        visual = OfferedAdapter(
            "visual",
            ObservationOffer("visual", "visual", "weak", "high"),
            _source("visual", profile=ObservationSourceProfile.visual()),
        )
        environment = UnifiedWorldEnvironment((dom, visual))
        task = _task()
        await environment.reset(task)
        acquired = await environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "spatial gap",
                (_need(ObservationPurpose.ENTITY_DISCOVERY, ObservationModality.VISUAL, ObservationAssurance.WEAK),),
            )
        )
        assert acquired.observation is not None
        option = next(
            item
            for item in ActionSpaceBuilder().build(task, acquired.observation).options
            if any(
                binding.binding_id in item.eligible_binding_ids and binding.surface == "visual"
                for binding in acquired.observation.bindings
            )
        )
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(option, {}),
            acquired.observation,
            "context:test",
        )

        outcome = await environment.execute(request)

        assert outcome.result.dispatch_status is DispatchStatus.SENT
        assert outcome.post_acquisition.selection_plan is not None
        assert [item.source for item in outcome.post_acquisition.selection_plan.selections] == ["visual"]
        assert dom.observe_calls == 2 and visual.observe_calls == 2

    asyncio.run(scenario())


def test_post_action_dom_route_does_not_reuse_prior_visual_selection() -> None:
    async def scenario() -> None:
        dom = OfferedAdapter(
            "dom",
            ObservationOffer("dom", "structural", "structural", "low"),
            _source("dom"),
        )
        visual = OfferedAdapter(
            "visual",
            ObservationOffer("visual", "visual", "weak", "high"),
            _source("visual", profile=ObservationSourceProfile.visual()),
        )
        environment = UnifiedWorldEnvironment((dom, visual))
        task = _task()
        await environment.reset(task)
        acquired = await environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "explicit visual discovery",
                (
                    _need(
                        ObservationPurpose.ENTITY_DISCOVERY,
                        ObservationModality.VISUAL,
                        ObservationAssurance.WEAK,
                    ),
                ),
            )
        )
        assert acquired.observation is not None
        option = next(
            item
            for item in ActionSpaceBuilder().build(task, acquired.observation).options
            if any(
                binding.binding_id in item.eligible_binding_ids and binding.surface == "dom"
                for binding in acquired.observation.bindings
            )
        )
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(option, {}),
            acquired.observation,
            "context:test",
        )

        outcome = await environment.execute(request)

        assert outcome.result.dispatch_status is DispatchStatus.SENT
        assert outcome.post_acquisition.selection_plan is not None
        assert [item.source for item in outcome.post_acquisition.selection_plan.selections] == ["dom"]
        assert dom.observe_calls == 3
        assert visual.observe_calls == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("crossed_dispatch", [False, True])
def test_execution_cancellation_closes_exact_dispatch_and_post_acquisition(
    crossed_dispatch: bool,
) -> None:
    class CancellingAdapter(OfferedAdapter):
        async def execute(self, request):
            if not crossed_dispatch:
                raise asyncio.CancelledError
            raise ActionDispatchCancelled(
                ActionResult(
                    request.request_id,
                    DispatchStatus.SENT_UNKNOWN,
                    self.surface,
                    False,
                    ActionError.CANCELLED,
                )
            )

    async def scenario() -> None:
        adapter = CancellingAdapter(
            "dom",
            ObservationOffer("dom", "structural", "structural", "low"),
            _source("dom"),
        )
        environment = UnifiedWorldEnvironment((adapter,))
        task = _task()
        acquired = await environment.reset(task)
        assert acquired.observation is not None
        option = ActionSpaceBuilder().build(task, acquired.observation).options[0]
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(option, {}),
            acquired.observation,
            "context:test",
        )

        with pytest.raises(ExecutionCancelled) as captured:
            await environment.execute(request)

        outcome = captured.value.outcome
        assert outcome.request is request
        assert outcome.result.error is ActionError.CANCELLED
        assert outcome.result.dispatch_status is (
            DispatchStatus.SENT_UNKNOWN if crossed_dispatch else DispatchStatus.NOT_SENT
        )
        if crossed_dispatch:
            assert outcome.post_acquisition is environment.last_acquisition
            assert outcome.post_acquisition is not None
            assert outcome.post_acquisition.origin is AcquisitionOrigin.POST_ACTION
            assert outcome.post_acquisition.status is AcquisitionStatus.CANCELLED
        else:
            assert outcome.post_acquisition is None

    asyncio.run(scenario())


def test_post_acquisition_cancellation_preserves_sent_execution_before_propagation() -> None:
    class PostCancellingAdapter(OfferedAdapter):
        cancel_acquisition = False

        async def acquire(self, request):
            if self.cancel_acquisition:
                raise asyncio.CancelledError
            return await super().acquire(request)

    async def scenario() -> None:
        adapter = PostCancellingAdapter(
            "dom",
            ObservationOffer("dom", "structural", "structural", "low"),
            _source("dom"),
        )
        environment = UnifiedWorldEnvironment((adapter,))
        task = _task()
        acquired = await environment.reset(task)
        assert acquired.observation is not None
        option = ActionSpaceBuilder().build(task, acquired.observation).options[0]
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(option, {}),
            acquired.observation,
            "context:test",
        )
        adapter.cancel_acquisition = True

        with pytest.raises(ExecutionCancelled) as captured:
            await environment.execute(request)

        outcome = captured.value.outcome
        assert outcome.request is request
        assert outcome.result.dispatch_status is DispatchStatus.SENT
        assert outcome.result.error is None
        assert outcome.post_acquisition is environment.last_acquisition
        assert outcome.post_acquisition is not None
        assert outcome.post_acquisition.status is AcquisitionStatus.CANCELLED

    asyncio.run(scenario())


def test_fusion_merges_only_explicit_correspondence_and_conserves_provenance() -> None:
    left = _source(
        "dom",
        local_id="dom-target",
        acquisition_root_id="root:shared",
    )
    right = _source(
        "wot",
        profile=ObservationSourceProfile.wot(),
        local_id="wot-target",
        align_to=SourceEntityEndpoint(left.observation_id, "dom-target"),
        acquisition_root_id="root:shared",
    )
    result = WorldFusion().fuse((left, right))

    assert result.observation is not None
    assert len(result.observation.targets) == 1
    canonical_id = result.observation.targets[0].target_id
    assert {item.target_id for item in result.observation.bindings} == {canonical_id}
    assert {(item.source_observation_id, item.source_target_id) for item in result.observation.entity_source_links} == {
        ("dom:obs", "dom-target"),
        ("wot:obs", "wot-target"),
    }
    assert all(item.allocation is EntityAllocation.EQUIVALENT for item in result.observation.entity_source_links)
    assert all(
        item.disposition is EntityAlignmentDisposition.ACCEPTED
        for item in result.observation.entity_alignment_decisions
    )


def test_visual_correspondence_adds_non_overlapping_state_without_replacing_dom_identity() -> None:
    dom = _source(
        "dom",
        local_id="dom-target",
        acquisition_root_id="root:shared",
    )
    visual = replace(
        _source(
            "visual",
            profile=ObservationSourceProfile.visual(),
            local_id="visual-target",
            align_to=SourceEntityEndpoint(dom.observation_id, "dom-target"),
            acquisition_root_id="root:shared",
        ),
        bindings=(),
        targets=(
            SemanticTarget(
                "visual-target",
                dom.targets[0].role,
                dom.targets[0].label,
                {"visually_selected": True},
            ),
        ),
    )

    result = WorldFusion().fuse((dom, visual))

    assert result.observation is not None
    target = result.observation.targets[0]
    assert target.state["visually_selected"] is True


def test_duplicate_labels_without_explicit_link_never_merge() -> None:
    result = WorldFusion().fuse(
        (
            _source("dom", local_id="same"),
            _source("visual", profile=ObservationSourceProfile.visual(), local_id="same"),
        )
    )

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

    result = WorldFusion().fuse(
        (
            _source("dom", acquisition_root_id="root:dom"),
            visual,
        )
    )

    assert result.observation is None
    assert result.reason_code == "visual_binding_requires_shared_acquisition"


def test_visual_coordinate_binding_cannot_bypass_missing_structural_root() -> None:
    result = WorldFusion().fuse(
        (
            _source("dom", acquisition_root_id=""),
            _source("visual", profile=ObservationSourceProfile.visual()),
        )
    )

    assert result.observation is None
    assert result.reason_code == "visual_binding_requires_shared_acquisition"


def test_visual_correspondence_with_different_acquisition_is_rejected_and_retained() -> None:
    dom = _source("dom", local_id="dom-target", acquisition_root_id="root:dom")
    visual = replace(
        _source(
            "visual",
            profile=ObservationSourceProfile.visual(),
            align_to=SourceEntityEndpoint(dom.observation_id, "dom-target"),
            acquisition_root_id="root:visual",
        ),
        bindings=(),
    )

    result = WorldFusion().fuse(
        (
            dom,
            visual,
        )
    )

    assert result.observation is not None
    assert len(result.observation.targets) == 2
    visual_link = next(
        item for item in result.observation.entity_source_links if item.source_observation_id == visual.observation_id
    )
    assert visual_link.allocation is EntityAllocation.INDEPENDENT
    assert result.observation.entity_alignment_decisions[0].disposition is EntityAlignmentDisposition.REJECTED


def test_visual_correspondence_with_missing_endpoint_is_rejected_and_retained() -> None:
    visual = replace(
        _source(
            "visual",
            profile=ObservationSourceProfile.visual(),
            align_to=SourceEntityEndpoint("dom:obs", "missing"),
        ),
        bindings=(),
    )

    result = WorldFusion().fuse((_source("dom"), visual))

    assert result.observation is not None
    assert len(result.observation.targets) == 2
    assert (
        next(
            item
            for item in result.observation.entity_source_links
            if item.source_observation_id == visual.observation_id
        ).allocation
        is EntityAllocation.INDEPENDENT
    )
    assert result.observation.entity_alignment_decisions[0].disposition is EntityAlignmentDisposition.REJECTED


def test_corresponded_visual_entity_cannot_retain_coordinate_binding() -> None:
    visual = _source(
        "visual",
        profile=ObservationSourceProfile.visual(),
        align_to=SourceEntityEndpoint("dom:obs", "target"),
    )

    result = WorldFusion().fuse(
        (
            _source("dom"),
            visual,
        )
    )

    assert result.observation is None
    assert result.reason_code == "proposed_visual_binding_forbidden"


def test_material_conflict_blocks_only_affected_action_option() -> None:
    dom = _source("dom", local_id="dom", value=False)
    conflicted = (
        WorldFusion()
        .fuse(
            (
                dom,
                _source(
                    "wot",
                    profile=ObservationSourceProfile.wot(),
                    local_id="wot",
                    align_to=SourceEntityEndpoint(dom.observation_id, "dom"),
                    value=True,
                ),
            )
        )
        .observation
    )
    assert conflicted is not None and conflicted.conflicts

    action_space = ActionSpaceBuilder().build(_task(), conflicted)

    assert action_space.options == ()


def test_route_selector_is_deterministic_and_model_never_selects_private_route() -> None:
    dom = _source("dom", local_id="dom", confidence=0.8)
    world = (
        WorldFusion()
        .fuse(
            (
                dom,
                _source(
                    "wot",
                    profile=ObservationSourceProfile.wot(),
                    local_id="wot",
                    align_to=SourceEntityEndpoint(dom.observation_id, "dom"),
                    confidence=0.9,
                ),
            )
        )
        .observation
    )
    assert world is not None
    option = ActionSpaceBuilder().build(_task(), world).options[0]
    selection = ActionSpaceBuilder().admit(option, {})

    selected = RouteSelector().select(selection, world)
    alternate = RouteSelector().select(
        selection,
        world,
        excluded_binding_ids=frozenset({selected.binding.binding_id}),  # type: ignore[union-attr]
    )

    assert selected.code is RouteSelectionCode.SELECTED
    assert selected.binding.surface == "wot"  # type: ignore[union-attr]
    assert alternate.binding.surface == "dom"  # type: ignore[union-attr]
    assert set(option.eligible_binding_ids) == {"dom:binding", "wot:binding"}
    assert option.resource_ref == option.target_id


def test_fusion_preserves_explicit_resource_identity_while_rewriting_default_identity() -> None:
    dom = _source("dom", local_id="dom")
    wot = _source(
        "wot",
        profile=ObservationSourceProfile.wot(),
        local_id="wot",
        align_to=SourceEntityEndpoint(dom.observation_id, "dom"),
    )
    explicit = replace(
        wot.bindings[0],
        resource_ref="account:stable",
    )

    world = WorldFusion().fuse((dom, replace(wot, bindings=(explicit,)))).observation

    assert world is not None
    dom_binding = next(item for item in world.bindings if item.surface == "dom")
    wot_binding = next(item for item in world.bindings if item.surface == "wot")
    assert dom_binding.resource_ref == dom_binding.target_id
    assert wot_binding.resource_ref == "account:stable"


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="PNG")
    return output.getvalue()


def test_marked_truth_depends_only_on_media_selected_for_this_model_call() -> None:
    marked_media = ObservationMedia(
        "marked",
        "screenshot",
        "image/png",
        _png(),
        (ObservationGroundingRegion("target", (1, 1, 5, 5), coordinate_space_id="viewport"),),
        "capture:marked",
        ObservationMediaVariant.RAW,
        (20, 20),
        "viewport",
    )
    plain_media = ObservationMedia(
        "plain",
        "screenshot",
        "image/png",
        _png(),
        capture_group_id="capture:plain",
        variant=ObservationMediaVariant.RAW,
        dimensions=(20, 20),
        coordinate_space_id="viewport",
    )
    source = _source("dom", media=(marked_media, plain_media))
    world = WorldFusion().fuse((source,)).observation
    assert world is not None
    action_space = ActionSpaceBuilder().build(_task(), world)
    projection = canonical_world(world, action_space)
    model_world = _project_model_world(
        world, ContextProjectionBudget(), canonical_projection=projection
    )
    dropped = GroundingProjection().project(
        world,
        projection,
        model_world,
        selected_media_ids=("plain",),
    )
    emitted = GroundingProjection().project(
        world,
        projection,
        model_world,
        selected_media_ids=("marked",),
    )
    not_delivered = GroundingProjection().project(
        world,
        projection,
        model_world,
        selected_media_ids=("marked",),
    )

    assert dropped.index.entities[0].marked is False
    assert emitted.index.entities[0].marked is True
    assert not_delivered.index.entities[0].marked is True
    assert not_delivered.images[0].marks == emitted.images[0].marks
    assert len(dropped.images) == len(emitted.images) == 1


@dataclass
class SharedCaptureAdapter:
    surface: str
    offers: tuple[ObservationOffer, ...]
    group_observations: dict[str, SurfaceObservation]
    reset_calls: int = 0
    group_calls: int = 0
    physical_capture_calls: int = 0
    acquisition_ids: list[str] = field(default_factory=list)
    prepared: bool = False
    owns_physical_reset: bool = True

    @property
    def physical_environment_id(self):
        return "fake:shared-browser"

    @property
    def observation_offers(self):
        return self.offers

    def initialize_task(self, task):
        del task
        self.prepared = True

    async def reset_physical(self):
        self.reset_calls += 1

    async def acquire(self, request):
        raise AssertionError("typed group port must own shared acquisition")

    async def acquire_group(self, requests):
        self.group_calls += 1
        self.acquisition_ids.extend(request.acquisition_id for request in requests)
        if any(request.offer.modality is ObservationModality.STRUCTURAL for request in requests):
            self.physical_capture_calls += 1
        return tuple(
            SelectedObservationResult.acquired(
                request,
                self.group_observations[request.source],
                fulfilled_need_ids=tuple(item.need_id for item in request.needs),
            )
            for request in requests
        )

    async def execute(self, request):
        return ActionResult(request.request_id, DispatchStatus.SENT, self.surface, True)


def test_shared_acquisition_group_has_one_reset_owner_and_one_group_capture() -> None:
    async def scenario() -> None:
        group = "browser:shared"
        dom_observation = _source("dom")
        visual_observation = _source("visual", profile=ObservationSourceProfile.visual())
        adapter = SharedCaptureAdapter(
            "browser",
            (
                ObservationOffer("dom", "structural", "structural", "low", group),
                ObservationOffer("visual", "visual", "weak", "high", group),
            ),
            {"dom": dom_observation, "visual": visual_observation},
        )
        environment = UnifiedWorldEnvironment((adapter,))
        await environment.reset(_task())
        acquired = await environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "spatial gap",
                (_need(ObservationPurpose.ENTITY_DISCOVERY, ObservationModality.VISUAL, ObservationAssurance.WEAK),),
            )
        )

        assert acquired.status is AcquisitionStatus.ACQUIRED
        assert adapter.group_calls == 2  # reset grounding, then one coherent structural+visual group
        assert adapter.physical_capture_calls == 2
        assert adapter.acquisition_ids[-2:] == [
            adapter.acquisition_ids[-1],
            adapter.acquisition_ids[-1],
        ]
        assert adapter.reset_calls == 1
        assert adapter.prepared is True

    asyncio.run(scenario())


def _equivalent_route_world(observation_id: str, enabled: bool):
    base = _world(observation_id, enabled)
    dom_source = base.sources[0]
    root_id = f"root:{observation_id}"
    dom_binding = replace(dom_source.bindings[0], confidence=0.8)
    dom_source = replace(dom_source, bindings=(dom_binding,), acquisition_root_id=root_id)
    wot_source_id = f"wot:{observation_id}"
    wot_binding = replace(
        dom_binding,
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
        dom_source.targets,
        tuple(replace(item, source_id=wot_source_id) for item in dom_source.facts),
        (wot_binding,),
        acquisition_root_id=root_id,
        alignment_proposals=(
            EntityAlignmentProposal(
                f"proposal:{wot_source_id}",
                SourceEntityEndpoint(wot_source_id, dom_source.targets[0].target_id),
                SourceEntityEndpoint(dom_source.observation_id, dom_source.targets[0].target_id),
                EntityAlignmentBasis.EXPLICIT_PROVIDER_CORRESPONDENCE,
                (f"evidence:{wot_source_id}",),
                1.0,
            ),
        ),
    )
    fused = WorldFusion().fuse((dom_source, wot_source))
    assert fused.observation is not None
    return fused.observation

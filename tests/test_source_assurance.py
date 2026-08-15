from affordance_runtime.model.context.acquisition_projection import project_acquisition_offers
from affordance_runtime.model.context.budgets import ContextProjectionBudget
from affordance_runtime.model.context.world_projection import project_model_world
from affordance_runtime.world import (
    AcquisitionCost,
    CoverageState,
    ObservationAssurance,
    ObservationCapabilities,
    ObservationModality,
    ObservationOffer,
    ObservationSourceProfile,
    SurfaceObservation,
    VerificationStrength,
    WorldObservation,
)
from affordance_runtime.world.source_profile import assurance_satisfies


def test_dom_visual_wot_source_profiles_are_truthful_and_distinct() -> None:
    dom = ObservationSourceProfile.dom()
    visual = ObservationSourceProfile.visual()
    wot = ObservationSourceProfile.wot()

    assert (dom.modality, dom.assurance, dom.verification_strength, dom.acquisition_cost) == (
        ObservationModality.STRUCTURAL,
        ObservationAssurance.STRUCTURAL,
        VerificationStrength.STRUCTURAL,
        AcquisitionCost.LOW,
    )
    assert (visual.modality, visual.assurance, visual.verification_strength, visual.acquisition_cost) == (
        ObservationModality.VISUAL,
        ObservationAssurance.WEAK,
        VerificationStrength.VISUAL,
        AcquisitionCost.HIGH,
    )
    assert (wot.modality, wot.assurance, wot.verification_strength) == (
        ObservationModality.ENVIRONMENT_STATE,
        ObservationAssurance.AUTHORITATIVE,
        VerificationStrength.AUTHORITATIVE,
    )
    assert dom.debug_source == "dom" and visual.debug_source == "visual" and wot.debug_source == "wot"


def test_source_assurance_profile_contains_no_action_or_risk_authority() -> None:
    names = set(ObservationSourceProfile.__dataclass_fields__)

    assert not names.intersection({"allowed_effects", "write_capability", "risk", "confirmation"})


def test_model_source_summary_excludes_debug_source_and_private_payload() -> None:
    profile = ObservationSourceProfile(
        ObservationModality.STRUCTURAL,
        ObservationAssurance.STRUCTURAL,
        VerificationStrength.STRUCTURAL,
        AcquisitionCost.LOW,
        "private-dom-backend",
    )
    source = SurfaceObservation(
        "source:1",
        "dom",
        "revision:1",
        profile,
        coverage=CoverageState.COMPLETE,
        artifacts={"selector": "#private", "summary": "private-value"},
    )
    world = WorldObservation("world:1", (), (), (), {"dom": CoverageState.COMPLETE}, sources=(source,))

    view = project_model_world(world, ContextProjectionBudget())

    assert view.sources[0].modality == ObservationModality.STRUCTURAL
    assert view.sources[0].assurance == ObservationAssurance.STRUCTURAL
    assert "private-dom-backend" not in repr(view)
    assert "#private" not in repr(view)
    assert "private-value" not in repr(view)
    assert view.sources[0].freshness == "current"
    assert view.sources[0].conflict_status == "clear"


def test_failed_source_evidence_and_operational_capability_are_independent() -> None:
    source = SurfaceObservation(
        "source:failed",
        "visual",
        "revision:1",
        ObservationSourceProfile.visual(),
        coverage=CoverageState.FAILED,
    )
    world = WorldObservation("world:failed", (), (), (), {"visual": CoverageState.FAILED}, sources=(source,))

    capabilities = ObservationCapabilities(
        True,
        False,
        (ObservationOffer("visual", "visual", "weak", "high"),),
    )
    view = project_model_world(
        world,
        ContextProjectionBudget(),
        observation_capabilities=project_acquisition_offers(capabilities),
    )

    assert tuple((item.modality, item.assurance) for item in view.observation_capabilities) == (
        (ObservationModality.VISUAL, ObservationAssurance.WEAK),
    )
    assert view.sources[0].coverage == CoverageState.FAILED


def test_assurance_dominance_allows_authoritative_for_structural_request() -> None:
    assert assurance_satisfies(ObservationAssurance.AUTHORITATIVE, ObservationAssurance.STRUCTURAL)
    assert not assurance_satisfies(ObservationAssurance.WEAK, ObservationAssurance.STRUCTURAL)

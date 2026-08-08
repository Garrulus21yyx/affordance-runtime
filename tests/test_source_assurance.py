from affordance_runtime.model_boundary.budgets import ContextProjectionBudget
from affordance_runtime.model_boundary.world_projection import project_model_world
from affordance_runtime.world import (
    AcquisitionCost,
    CoverageState,
    ObservationAssurance,
    ObservationModality,
    ObservationSourceProfile,
    SurfaceObservation,
    VerificationStrength,
    WorldObservation,
)


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

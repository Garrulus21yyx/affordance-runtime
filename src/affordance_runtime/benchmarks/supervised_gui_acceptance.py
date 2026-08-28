"""Controlled cross-domain acceptance and public read-only shadow preflight."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NotRequired, TypedDict
from urllib.parse import urlsplit

from affordance_runtime.actions.grounding import EvidenceKind, GroundingSource, PerceptionRequirements
from affordance_runtime.agent.decisions import (
    InteractionAttribute,
    InteractionOptionDraft,
    InteractionRequestDraft,
    InteractionResponseKind,
    PublicArtifactDraft,
    PublicArtifactItemDraft,
)
from affordance_runtime.agent.interactions import (
    SingleSelectionResponse,
    admit_interaction_request,
    admit_interaction_response,
    materialize_public_artifact,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.surfaces.dom.adapter import DomSurfaceAdapter
from affordance_runtime.surfaces.dom.browser_session import BrowserSession
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    ObservationModality,
    ObservationNeed,
    ObservationPurpose,
    ObservationRequestKind,
    SelectedObservationRequest,
    SourceRequirement,
    SourceSelection,
    WorldFusion,
)

SCHEMA_VERSION = "supervised-gui-acceptance.v1"
PROFILE_ID = "general-supervised-gui-controlled.v1"
DEFAULT_FIXTURE_ROOT = Path("docs/benchmarks/fixtures/supervised-gui")
PUBLIC_SHADOW_ENVIRONMENT = (
    ("public_shopping", "SUPERVISED_GUI_SHADOW_SHOPPING_URL"),
    ("public_content", "SUPERVISED_GUI_SHADOW_CONTENT_URL"),
)


class _ControlledScenario(TypedDict):
    scenario_id: str
    fixture: str
    cohort: str
    required_capabilities: tuple[str, ...]
    minimum_controls: int
    repeated_control: NotRequired[tuple[str, int]]
    required_text: tuple[str, ...]


_CONTROLLED_SCENARIOS: tuple[_ControlledScenario, ...] = (
    {
        "scenario_id": "candidate_comparison_flagship",
        "fixture": "candidate-comparison.html",
        "cohort": "flagship",
        "required_capabilities": (
            "generic_candidates",
            "visual_predicate",
            "generic_option_interaction",
            "public_artifact",
            "user_control",
        ),
        "minimum_controls": 3,
        "repeated_control": ("Choose", 3),
        "required_text": ("Harbor jacket", "Field jacket", "Cedar jacket", "$72"),
    },
    {
        "scenario_id": "chart_analysis_heldout",
        "fixture": "chart-analysis.html",
        "cohort": "heldout",
        "required_capabilities": ("svg_target", "text_in_image", "visual_predicate"),
        "minimum_controls": 4,
        "required_text": ("Quarterly support volume", "Q3", "81"),
    },
    {
        "scenario_id": "map_spatial_heldout",
        "fixture": "map-spatial.html",
        "cohort": "heldout",
        "required_capabilities": ("svg_target", "spatial_relationship", "generic_candidates"),
        "minimum_controls": 3,
        "required_text": ("Park map", "Marker A", "Marker C"),
    },
    {
        "scenario_id": "file_list_heldout",
        "fixture": "file-list.html",
        "cohort": "heldout",
        "required_capabilities": ("generic_candidates", "text_in_image", "public_artifact"),
        "minimum_controls": 3,
        "repeated_control": ("Choose", 3),
        "required_text": ("survey.csv", "results.csv", "2026-08-28 07:45"),
    },
)


def supervised_gui_acceptance_manifest() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "profile_id": PROFILE_ID,
        "production_specialization_prohibited": True,
        "controlled": {
            "content_filter_profile": "off",
            "agent_calls": 0,
            "visual_provider_calls": 0,
            "scenarios": [_public_scenario(item) for item in _CONTROLLED_SCENARIOS],
        },
        "public_shadow": {
            "required_content_filter_profile": "ads_and_cosmetic.v1",
            "mode": "read_only",
            "allowed_effects": [],
            "forbidden_effects": [
                "login",
                "credential_use",
                "form_submission",
                "purchase",
                "download",
            ],
            "live_authorization_required": True,
            "cases": [
                {"case_id": case_id, "url_environment_variable": variable}
                for case_id, variable in PUBLIC_SHADOW_ENVIRONMENT
            ],
        },
    }


def supervised_gui_acceptance_manifest_digest() -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(supervised_gui_acceptance_manifest())).hexdigest()


def write_supervised_gui_acceptance_manifest(path: Path) -> dict[str, Any]:
    payload = {
        **supervised_gui_acceptance_manifest(),
        "manifest_digest": supervised_gui_acceptance_manifest_digest(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def validate_controlled_supervised_gui(
    output_path: Path,
    *,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
) -> dict[str, Any]:
    """Capture local fixtures with the product BrowserSession and zero model calls."""

    results = tuple(_capture_scenario(fixture_root, scenario) for scenario in _CONTROLLED_SCENARIOS)
    errors = tuple(error for result in results for error in result["errors"])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "profile_id": PROFILE_ID,
        "manifest_digest": supervised_gui_acceptance_manifest_digest(),
        "content_filter_profile": "off",
        "agent_calls": 0,
        "visual_provider_calls": 0,
        "scenarios": results,
        "accepted": not errors,
        "acceptance_errors": errors,
        "live_capability_claimed": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def preflight_public_shadow(
    environment: Mapping[str, str],
    output_path: Path,
) -> dict[str, Any]:
    """Validate read-only inputs without opening a browser or resolving a host."""

    cases = []
    errors = []
    for case_id, variable in PUBLIC_SHADOW_ENVIRONMENT:
        value = environment.get(variable, "").strip()
        origin = _public_origin(value)
        ready = bool(origin)
        if not ready:
            errors.append(f"{case_id}: missing or invalid {variable}")
        cases.append({
            "case_id": case_id,
            "url_environment_variable": variable,
            "configured_origin": origin,
            "ready": ready,
        })
    payload = {
        "schema_version": SCHEMA_VERSION,
        "manifest_digest": supervised_gui_acceptance_manifest_digest(),
        "preflight_scope": "url_inputs_only",
        "required_content_filter_profile": "ads_and_cosmetic.v1",
        "surface_filter_admission_required": True,
        "mode": "read_only",
        "browser_opened": False,
        "network_requests": 0,
        "live_authorization_required": True,
        "input_ready": not errors,
        "live_execution_ready": False,
        "cases": cases,
        "errors": errors,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _capture_scenario(fixture_root: Path, scenario: _ControlledScenario) -> dict[str, Any]:
    path = (fixture_root / str(scenario["fixture"])).resolve()
    errors: list[str] = []
    if not path.is_file():
        return {
            "scenario_id": scenario["scenario_id"],
            "fixture": str(scenario["fixture"]),
            "errors": [f"{scenario['scenario_id']}: fixture missing"],
        }
    with BrowserSession.launch(path.as_uri(), headless=True) as session:
        snapshot = session.capture(
            page_id=str(scenario["scenario_id"]),
            perception_requirements=PerceptionRequirements(
                required_properties=frozenset({EvidenceKind.VISUAL_APPEARANCE, EvidenceKind.SPATIAL}),
                acceptable_evidence=frozenset({
                    GroundingSource.DOM,
                    GroundingSource.ACCESSIBILITY,
                    GroundingSource.SVG,
                    GroundingSource.VISUAL,
                }),
            ),
            task_terms=tuple(str(item) for item in scenario["required_text"]),
        )
        labels = tuple(item.label for item in snapshot.affordance_model.affordances)
        visible_text = str(snapshot.observation.metadata.get("visible_text") or "")
        minimum_controls = int(scenario["minimum_controls"])
        if len(labels) < minimum_controls:
            errors.append(f"{scenario['scenario_id']}: insufficient projected controls")
        repeated = scenario.get("repeated_control")
        if isinstance(repeated, tuple):
            label, minimum = repeated
            if Counter(labels)[str(label)] < int(minimum):
                errors.append(f"{scenario['scenario_id']}: repeated controls collapsed")
        for required in scenario["required_text"]:
            if str(required) not in visible_text:
                errors.append(f"{scenario['scenario_id']}: required visible text missing")
        if snapshot.visual_frame is None:
            errors.append(f"{scenario['scenario_id']}: visual frame missing")

        interaction, artifact = _exercise_presentation_contract(session, snapshot, scenario)
        if not interaction:
            errors.append(f"{scenario['scenario_id']}: option response was not admitted")
        if not artifact:
            errors.append(f"{scenario['scenario_id']}: public artifact was not materialized")
        frame = snapshot.visual_frame
        return {
            "scenario_id": scenario["scenario_id"],
            "cohort": scenario["cohort"],
            "fixture": str(scenario["fixture"]),
            "fixture_sha256": _sha256(path),
            "browser_version": session.browser_version,
            "control_count": len(labels),
            "control_labels": labels,
            "screenshot_digest": frame.screenshot_digest if frame is not None else "",
            "screenshot_dimensions": (
                [frame.image_width, frame.image_height] if frame is not None else []
            ),
            "option_response_admitted": interaction,
            "public_artifact_materialized": artifact,
            "required_capabilities": scenario["required_capabilities"],
            "errors": errors,
        }


def _exercise_presentation_contract(
    session: BrowserSession,
    snapshot: object,
    scenario: _ControlledScenario,
) -> tuple[bool, bool]:
    adapter = DomSurfaceAdapter(session)
    adapter.initialize_task(TaskGoal(
        f"controlled:{scenario['scenario_id']}",
        "Compare the visible entities and present a user-selectable result.",
    ))
    need = ObservationNeed(
        "need:controlled-world",
        ObservationPurpose.WORLD_GROUNDING,
        required_modality=ObservationModality.STRUCTURAL,
        required_assurance=adapter.observation_offers[0].assurance,
    )
    offer = adapter.observation_offers[0]
    request = SelectedObservationRequest(
        "acquisition:controlled-world",
        ObservationRequestKind.POLICY_REQUEST,
        "controlled fixture projection",
        offer,
        SourceSelection("dom", SourceRequirement.REQUIRED, "controlled_fixture", (need.need_id,)),
        (need,),
    )
    projected = adapter.project_snapshot(request, snapshot)
    if projected.observation is None:
        return False, False
    fused = WorldFusion().fuse((projected.observation,))
    world = fused.observation
    if world is None:
        return False, False
    records = WorldEvidenceIndex.from_observation(world).records
    refs_by_subject: dict[str, list[str]] = {}
    for record in records:
        refs_by_subject.setdefault(record.subject_id, []).append(record.evidence_ref)
    candidates = tuple(
        target
        for target in world.targets
        if target.role in {"button", "option", "link", "checkbox", "radio"}
        and refs_by_subject.get(target.target_id)
    )
    if not candidates:
        return False, False
    option_drafts = tuple(
        InteractionOptionDraft(
            target.label or f"Visible {target.role}",
            "Current visible entity.",
            attributes=(InteractionAttribute("Role", target.role),),
            evidence_refs=(refs_by_subject[target.target_id][0],),
        )
        for target in candidates[:8]
    )
    admission = admit_interaction_request(
        world,
        InteractionRequestDraft(
            "context:controlled-fixture",
            "Choose one visible entity.",
            InteractionResponseKind.SINGLE_SELECT,
            option_drafts=option_drafts,
        ),
    )
    if admission.request is None:
        return False, False
    selected = admission.request.options[0]
    response = admit_interaction_response(
        admission.request,
        SingleSelectionResponse(admission.request.request_id, selected.option_id),
    )
    evidence_ref = selected.evidence_refs[0]
    artifact = materialize_public_artifact(
        world,
        PublicArtifactDraft(
            "Controlled result",
            "One user-selected current entity.",
            (
                PublicArtifactItemDraft(
                    selected.title,
                    "Selected from the generic option set.",
                    selected.attributes,
                    (evidence_ref,),
                ),
            ),
            (evidence_ref,),
        ),
        response_identity="controlled-fixture",
    )
    return response.admitted, artifact is not None


def _public_scenario(value: _ControlledScenario) -> dict[str, Any]:
    return {
        "scenario_id": value["scenario_id"],
        "fixture": value["fixture"],
        "cohort": value["cohort"],
        "required_capabilities": list(value["required_capabilities"]),
    }


def _public_origin(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError:
        return ""
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return ""
    return f"{parsed.scheme}://{hostname}"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


__all__ = [
    "DEFAULT_FIXTURE_ROOT",
    "PROFILE_ID",
    "PUBLIC_SHADOW_ENVIRONMENT",
    "SCHEMA_VERSION",
    "preflight_public_shadow",
    "supervised_gui_acceptance_manifest",
    "supervised_gui_acceptance_manifest_digest",
    "validate_controlled_supervised_gui",
    "write_supervised_gui_acceptance_manifest",
]

"""Task-level perception requirement derivation."""

from __future__ import annotations

import re

from affordance_runtime.contracts import RiskLevel
from affordance_runtime.grounding import EvidenceKind, GroundingSource, PerceptionRequirements
from affordance_runtime.task_intake import OperationClass, TaskSpec

_VISUAL_TERMS = frozenset(
    {
        "appearance",
        "canvas",
        "chart",
        "circle",
        "diagram",
        "image",
        "look",
        "screenshot",
        "shape",
        "svg",
        "visual",
    }
)
_SPATIAL_TERMS = frozenset(
    {
        "above",
        "below",
        "bottom",
        "center",
        "coordinate",
        "inside",
        "left",
        "move",
        "point",
        "position",
        "right",
        "outside",
        "spatial",
        "top",
    }
)
_DEVICE_TERMS = frozenset({"device", "property", "sensor", "thing", "wot"})


def derive_perception_requirements(
    task: TaskSpec,
    *,
    active_subgoal: str = "",
) -> PerceptionRequirements:
    """Derive bounded evidence needs without selecting a concrete backend."""

    text = " ".join(
        (
            task.objective,
            active_subgoal,
            *task.targets,
            *task.success_criteria,
            *task.evidence_requirements,
        )
    ).lower()
    terms = frozenset(
        {
            *re.findall(r"[a-z0-9_-]+", text),
            *re.findall(r"[a-z0-9]+", text.replace("-", " ").replace("_", " ")),
        }
    )
    visual_required = bool(terms.intersection(_VISUAL_TERMS))
    ordered_collection_required = "order" in terms and bool(terms.intersection({"ascending", "descending"}))
    spatial_required = bool(terms.intersection(_SPATIAL_TERMS)) or ordered_collection_required
    device_required = bool(terms.intersection(_DEVICE_TERMS))
    required: set[EvidenceKind] = set()
    acceptable: set[GroundingSource] = set()
    preferred: tuple[GroundingSource, ...] = ()
    model_call_budget = 0
    cost_budget = 0.0
    if visual_required or spatial_required:
        required.add(EvidenceKind.VISUAL_APPEARANCE)
        acceptable.update({GroundingSource.SVG, GroundingSource.SOM, GroundingSource.VISUAL})
        preferred = (GroundingSource.SVG, GroundingSource.SOM, GroundingSource.VISUAL)
        model_call_budget = 1
        cost_budget = 1.0
    if spatial_required:
        required.add(EvidenceKind.SPATIAL)
        acceptable.update(
            {
                GroundingSource.DOM,
                GroundingSource.ACCESSIBILITY,
                GroundingSource.SVG,
                GroundingSource.SOM,
                GroundingSource.VISUAL,
            }
        )
        preferred = (GroundingSource.SVG, GroundingSource.DOM, GroundingSource.SOM, GroundingSource.VISUAL)
        model_call_budget = 1
        cost_budget = 1.0
    if device_required:
        required.update({EvidenceKind.DEVICE_STATE, EvidenceKind.STRUCTURAL})
        acceptable.update({GroundingSource.WOT, GroundingSource.API})
        preferred = (GroundingSource.WOT, GroundingSource.API, *preferred)
    if not required:
        required.update({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL})
        acceptable.update({GroundingSource.DOM, GroundingSource.ACCESSIBILITY})
        preferred = (GroundingSource.DOM, GroundingSource.ACCESSIBILITY)
    return PerceptionRequirements(
        required_properties=frozenset(required),
        acceptable_evidence=frozenset(acceptable),
        preferred_sources=tuple(dict.fromkeys(preferred)),
        minimum_confidence=0.5 if EvidenceKind.VISUAL_APPEARANCE in required else 0.0,
        minimum_verifier_strength=1,
        observation_budget=3 if EvidenceKind.SPATIAL in required else 1,
        model_call_budget=model_call_budget,
        latency_budget_ms=15_000 if model_call_budget else 5_000,
        cost_budget=cost_budget,
        risk=task_risk(task),
    )


def perception_task_terms(task: TaskSpec, *, active_subgoal: str = "") -> tuple[str, ...]:
    """Return bounded semantic terms for selective structured observers."""

    text = " ".join((task.objective, active_subgoal, *task.targets)).lower()
    whole = re.findall(r"[a-z0-9_-]+", text)
    parts = re.findall(r"[a-z0-9]+", text.replace("-", " ").replace("_", " "))
    return tuple(dict.fromkeys([*whole, *parts]))[:32]


def task_risk(task: TaskSpec) -> RiskLevel:
    return {
        OperationClass.READ_ONLY: RiskLevel.LOW,
        OperationClass.NAVIGATION: RiskLevel.LOW,
        OperationClass.REVERSIBLE_WRITE: RiskLevel.MEDIUM,
        OperationClass.EXTERNAL_SIDE_EFFECT: RiskLevel.HIGH,
        OperationClass.IRREVERSIBLE: RiskLevel.IRREVERSIBLE,
    }[task.operation_class]

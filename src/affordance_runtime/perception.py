"""Task-level perception requirement derivation."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from affordance_runtime.contracts import RiskLevel
from affordance_runtime.grounding import EvidenceKind, GroundingSource, PerceptionRequirements
from affordance_runtime.simplified_runtime_contracts import StepSpec
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.visual_grounding import (
    VisualGrounderPort,
    VisualGroundingRequest,
    VisualRegion,
    VisualRegionProposalRequest,
    VisualRegionProposerPort,
)

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
_VISUAL_TARGET_ROLES = frozenset({"canvas", "graphic", "image", "point", "region", "svg"})
_VISUAL_TARGET_TERMS = _VISUAL_TERMS | frozenset({"color", "colored", "icon", "pattern", "pixel"})


class PerceptionOrchestratorPort(Protocol):
    """Generic task-aware visual proposal boundary for one captured epoch."""

    def propose_visual_regions(
        self,
        *,
        observation_epoch_id: str,
        screenshot_path: Path | None,
        screenshot_bytes: bytes,
        image_size: tuple[int, int],
        instruction: str,
        requirements: PerceptionRequirements,
    ) -> tuple[VisualRegion, ...]: ...


@dataclass(frozen=True)
class GenericPerceptionOrchestrator:
    region_proposer: VisualRegionProposerPort | None = None
    point_grounder: VisualGrounderPort | None = None
    max_regions: int = 16

    def __post_init__(self) -> None:
        if self.region_proposer is None and self.point_grounder is None:
            raise ValueError("perception orchestrator requires a visual proposal adapter")

    def propose_visual_regions(
        self,
        *,
        observation_epoch_id: str,
        screenshot_path: Path | None,
        screenshot_bytes: bytes,
        image_size: tuple[int, int],
        instruction: str,
        requirements: PerceptionRequirements,
    ) -> tuple[VisualRegion, ...]:
        if requirements.model_call_budget < 1:
            return ()
        request = VisualRegionProposalRequest(
            sample_id=observation_epoch_id,
            image_path=screenshot_path,
            image_bytes=screenshot_bytes,
            image_size=image_size,
            instruction=instruction,
            max_regions=self.max_regions,
        )
        if self.region_proposer is not None:
            regions = self.region_proposer.propose(request)
        else:
            if self.point_grounder is None:  # guarded by __post_init__
                return ()
            point = self.point_grounder.ground(
                VisualGroundingRequest(
                    sample_id=observation_epoch_id,
                    image_path=screenshot_path,
                    image_bytes=screenshot_bytes,
                    image_size=image_size,
                    instruction=instruction,
                )
            )
            x, y = point.pixel_coordinates(image_size)
            regions = [
                VisualRegion(
                    (x - 0.5, y - 0.5, 1.0, 1.0),
                    label="current visually grounded target",
                    confidence=1.0,
                    normalized=False,
                )
            ]
        if len(regions) > self.max_regions:
            raise ValueError("visual region proposer exceeded the bounded region count")
        return tuple(regions)


@dataclass(frozen=True)
class PerceptionEscalation:
    """Evidence-driven request to widen perception after a failed route.

    This carries only typed source classes and a generic failure reason.  It
    deliberately contains no task-family name, selector, coordinate, backend handle, or
    backend action syntax.
    """

    reason: str
    failed_sources: frozenset[GroundingSource] = frozenset()
    requested_sources: frozenset[GroundingSource] = frozenset()

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("perception escalation requires a reason")


def derive_perception_requirements(
    task: TaskSpec,
    *,
    active_subgoal: StepSpec | str | None = None,
    escalation: PerceptionEscalation | None = None,
) -> PerceptionRequirements:
    """Derive bounded evidence needs without selecting a concrete backend."""

    text = _perception_text(task, active_subgoal)
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
    if visual_required:
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
    if escalation is not None:
        acceptable.update(escalation.requested_sources)
        if escalation.failed_sources.intersection({GroundingSource.DOM, GroundingSource.ACCESSIBILITY}):
            # A structured route was disproved.  Acquire an independent visual
            # grounding route on the next coherent epoch instead of retrying
            # the same handle or teaching a task-specific exception.
            required.discard(EvidenceKind.STRUCTURAL)
            required.add(EvidenceKind.VISUAL_APPEARANCE)
            acceptable.update({GroundingSource.SVG, GroundingSource.SOM, GroundingSource.VISUAL})
            preferred = (
                GroundingSource.SVG,
                GroundingSource.SOM,
                GroundingSource.VISUAL,
                *tuple(item for item in preferred if item not in escalation.failed_sources),
            )
            model_call_budget = max(model_call_budget, 1)
            cost_budget = max(cost_budget, 1.0)
        elif escalation.requested_sources:
            preferred = (
                *tuple(escalation.requested_sources),
                *tuple(item for item in preferred if item not in escalation.requested_sources),
            )
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


def route_perception_requirements(
    requirements: PerceptionRequirements,
    *,
    action: str,
    target_role: str,
    target_label: str,
    target_context: str = "",
    target_evidence: frozenset[EvidenceKind] = frozenset(),
) -> PerceptionRequirements:
    """Narrow task-level acquisition needs to one semantic action target.

    Task-level requirements decide what a coherent epoch may need to collect.
    Route hard gates must not force evidence about an earlier visual/spatial
    target onto a later ordinary control such as Submit. Gesture endpoints
    retain spatial requirements, and intrinsically visual targets retain visual
    appearance evidence.
    """

    required = set(requirements.required_properties)
    role = target_role.casefold().strip().replace("-", "_")
    label_terms = set(re.findall(r"[a-z0-9]+", target_label.casefold().replace("-", " ")))
    context_terms = set(re.findall(r"[a-z0-9]+", target_context.casefold().replace("-", " ")))
    spatial_action = action in {"drag", "point_activate"}
    visual_target = (
        action == "point_activate"
        or role in _VISUAL_TARGET_ROLES
        or bool(label_terms.intersection(_VISUAL_TARGET_TERMS))
        or bool(context_terms.intersection(_VISUAL_TARGET_TERMS))
        or EvidenceKind.VISUAL_APPEARANCE in target_evidence
    )
    device_target = EvidenceKind.DEVICE_STATE in target_evidence
    if not spatial_action:
        required.discard(EvidenceKind.SPATIAL)
    if not visual_target:
        required.discard(EvidenceKind.VISUAL_APPEARANCE)
    else:
        required.discard(EvidenceKind.TEXTUAL)
        required.discard(EvidenceKind.STRUCTURAL)
        required.add(EvidenceKind.VISUAL_APPEARANCE)
        if spatial_action:
            required.add(EvidenceKind.SPATIAL)
    if device_target:
        required.discard(EvidenceKind.TEXTUAL)
        required.add(EvidenceKind.DEVICE_STATE)
        required.add(EvidenceKind.STRUCTURAL)
    projected_to_structured_default = not required
    if projected_to_structured_default:
        required.update({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL})
    acceptable = set(requirements.acceptable_evidence)
    preferred = requirements.preferred_sources
    if visual_target:
        acceptable.update({GroundingSource.SVG, GroundingSource.SOM, GroundingSource.VISUAL})
        preferred = (
            GroundingSource.SVG,
            GroundingSource.SOM,
            GroundingSource.VISUAL,
            *preferred,
        )
    if device_target:
        acceptable.update({GroundingSource.WOT, GroundingSource.API})
        preferred = (GroundingSource.WOT, GroundingSource.API, *preferred)
    if projected_to_structured_default:
        acceptable.update({GroundingSource.DOM, GroundingSource.ACCESSIBILITY})
        preferred = (
            GroundingSource.DOM,
            GroundingSource.ACCESSIBILITY,
            *tuple(
                source
                for source in preferred
                if source not in {GroundingSource.DOM, GroundingSource.ACCESSIBILITY}
            ),
        )
    return replace(
        requirements,
        required_properties=frozenset(required),
        acceptable_evidence=frozenset(acceptable),
        preferred_sources=tuple(dict.fromkeys(preferred)),
        minimum_confidence=(
            requirements.minimum_confidence
            if EvidenceKind.VISUAL_APPEARANCE in required
            else 0.0
        ),
    )


def perception_task_terms(
    task: TaskSpec,
    *,
    active_subgoal: StepSpec | str | None = None,
) -> tuple[str, ...]:
    """Return bounded semantic terms for selective structured observers."""

    text = _perception_text(task, active_subgoal)
    whole = re.findall(r"[a-z0-9_-]+", text)
    parts = re.findall(r"[a-z0-9]+", text.replace("-", " ").replace("_", " "))
    return tuple(dict.fromkeys([*whole, *parts]))[:32]


def _perception_text(task: TaskSpec, active_subgoal: StepSpec | str | None) -> str:
    subgoal_parts: tuple[str, ...]
    if isinstance(active_subgoal, StepSpec):
        from affordance_runtime.criteria import PredicateExpr, criterion_nodes

        subgoal_parts = (
            active_subgoal.objective,
            *(
                " ".join(
                    (
                        criterion.subject.reference,
                        criterion.operator.value,
                        *(item.value for item in criterion.policy.allowed_source_kinds),
                    )
                )
                for expression in active_subgoal.completion_criteria
                for criterion in criterion_nodes(expression)
                if isinstance(criterion, PredicateExpr)
            ),
        )
    elif isinstance(active_subgoal, str):
        subgoal_parts = (active_subgoal,)
    else:
        subgoal_parts = ()
    admitted_requirement_parts = tuple(
        " ".join(
            part
            for part in (
                requirement.payload.kind,
                requirement.payload.subject,
                requirement.payload.relation,
                requirement.payload.value,
                requirement.payload.capability,
            )
            if part
        )
        for requirement in task.requirements
    )
    return " ".join(
        (
            *subgoal_parts,
            *admitted_requirement_parts,
        )
    ).lower()


def task_risk(task: TaskSpec) -> RiskLevel:
    return {
        OperationClass.READ_ONLY: RiskLevel.LOW,
        OperationClass.NAVIGATION: RiskLevel.LOW,
        OperationClass.REVERSIBLE_WRITE: RiskLevel.MEDIUM,
        OperationClass.EXTERNAL_SIDE_EFFECT: RiskLevel.HIGH,
        OperationClass.IRREVERSIBLE: RiskLevel.IRREVERSIBLE,
    }[task.operation_class]

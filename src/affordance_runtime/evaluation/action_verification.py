"""Runtime-derived bounded verification scope for one post-action evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    ParameterContractKind,
)
from affordance_runtime.actions.classification import EffectCategory
from affordance_runtime.evaluation.criterion_contracts import CriterionAdjudicator
from affordance_runtime.evaluation.criterion_normalization import normalize_task_criteria
from affordance_runtime.execution.contracts import BoundActionRequest
from affordance_runtime.immutable import freeze_json
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.source_profile import ObservationAssurance


class VerificationObligationKind(StrEnum):
    FACT_TRANSITION_TO = "fact_transition_to"
    CRITERION_PROGRESS = "criterion_progress"
    ARTIFACT_CREATED = "artifact_created"
    STRUCTURAL_WORLD_CHANGE = "structural_world_change"


@dataclass(frozen=True)
class RuntimeVerificationObligation:
    kind: VerificationObligationKind
    subject_id: str = ""
    predicate: str = ""
    expected_value: object = None
    criterion_id: str = ""
    output_id: str = ""
    required_assurance: str = ""

    def __post_init__(self) -> None:
        fields = (self.subject_id, self.predicate, self.criterion_id, self.output_id, self.required_assurance)
        if any(len(item) > 240 for item in fields):
            raise ValueError("verification obligation field exceeds its bound")
        if self.kind == VerificationObligationKind.STRUCTURAL_WORLD_CHANGE:
            if any((self.subject_id, self.predicate, self.criterion_id, self.output_id)):
                raise ValueError("structural world-change verification has no preselected subject")
        elif self.kind == VerificationObligationKind.ARTIFACT_CREATED:
            if not self.output_id:
                raise ValueError("artifact verification requires an output ID")
        elif not self.subject_id or not self.predicate or not self.criterion_id:
            raise ValueError("fact verification requires criterion, subject, and predicate")
        if self.required_assurance:
            ObservationAssurance(self.required_assurance)
        object.__setattr__(self, "expected_value", freeze_json(self.expected_value))


def derive_action_verification_obligations(
    task: TaskGoal,
    request: BoundActionRequest,
    before: WorldObservation,
) -> tuple[RuntimeVerificationObligation, ...]:
    subjects = {request.intent.target_id, request.intent.destination_id} - {""}
    obligations: list[RuntimeVerificationObligation] = []
    selection = getattr(request, "selection", None)
    if getattr(selection, "effect_category", "") == EffectCategory.INTERACTION:
        obligations.append(RuntimeVerificationObligation(
            VerificationObligationKind.STRUCTURAL_WORLD_CHANGE,
        ))
    primitive = _primitive_value_obligation(request)
    if primitive is not None:
        obligations.append(primitive)
    try:
        criteria = normalize_task_criteria(task)
    except ValueError:
        criteria = ()
    for criterion in criteria:
        if criterion.adjudicator not in {CriterionAdjudicator.MECHANICAL, CriterionAdjudicator.HYBRID}:
            continue
        predicate = criterion.state_key if criterion.kind == "target_state_equals" else criterion.predicate
        subject = criterion.subject_id or _unique_subject(before, predicate, subjects)
        if not predicate or subject not in subjects:
            continue
        if _already_satisfied(before, subject, predicate, criterion.expected_value):
            continue
        kind = (
            VerificationObligationKind.FACT_TRANSITION_TO
            if criterion.kind == "target_state_equals"
            else VerificationObligationKind.CRITERION_PROGRESS
        )
        obligations.append(RuntimeVerificationObligation(
            kind, subject, predicate, criterion.expected_value, criterion.criterion_id,
            required_assurance=criterion.required_assurance,
        ))
    output_id = request.intent.expected_outcome.get("output_id")
    if isinstance(output_id, str) and output_id.strip():
        obligations.append(RuntimeVerificationObligation(
            VerificationObligationKind.ARTIFACT_CREATED, output_id=output_id,
        ))
    return tuple(obligations)


def _primitive_value_obligation(request: BoundActionRequest) -> RuntimeVerificationObligation | None:
    semantic = request.intent.semantic_action
    definition = INTERACTION_CAPABILITY_REGISTRY.require(semantic)
    if definition.parameter_contract not in {
        ParameterContractKind.TEXT,
        ParameterContractKind.OPTION_VALUE,
    }:
        return None
    parameter_name = definition.parameter_names[0]
    value = request.intent.parameters.get(parameter_name)
    if not isinstance(value, str):
        return None
    return RuntimeVerificationObligation(
        VerificationObligationKind.FACT_TRANSITION_TO,
        request.intent.target_id,
        "value",
        value,
        f"action-postcondition:{semantic}:value",
        required_assurance="structural",
    )


def _unique_subject(before: WorldObservation, predicate: str, allowed: set[str]) -> str:
    matches = {fact.subject_id for fact in before.facts if fact.predicate == predicate}
    return next(iter(matches)) if len(matches) == 1 and matches.issubset(allowed) else ""


def _already_satisfied(before: WorldObservation, subject: str, predicate: str, expected: object) -> bool:
    values = tuple(
        fact.value for fact in before.facts
        if fact.subject_id == subject and fact.predicate == predicate
    )
    return len(values) == 1 and values[0] == expected

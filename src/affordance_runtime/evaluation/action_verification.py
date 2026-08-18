"""Runtime-derived bounded verification scope for one post-action outcome."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    ParameterContractKind,
    VerificationFamily,
)
from affordance_runtime.actions.classification import EffectCategory
from affordance_runtime.execution.contracts import BoundActionRequest
from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.observation_needs import (
    FreshnessRequirement,
    ObservationNeed,
    ObservationPurpose,
)
from affordance_runtime.world.source_profile import ObservationAssurance, ObservationModality


class VerificationObligationKind(StrEnum):
    FACT_TRANSITION_TO = "fact_transition_to"
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
        elif not self.subject_id or not self.predicate or not self.criterion_id:
            raise ValueError("fact verification requires criterion, subject, and predicate")
        if self.required_assurance:
            ObservationAssurance(self.required_assurance)
        object.__setattr__(self, "expected_value", freeze_json(self.expected_value))


def derive_action_verification_obligations(
    request: BoundActionRequest,
) -> tuple[RuntimeVerificationObligation, ...]:
    obligations: list[RuntimeVerificationObligation] = []
    family = request.selection.verification_contract.family
    if (
        getattr(request.selection, "effect_category", "") == EffectCategory.INTERACTION
        or family is VerificationFamily.NAVIGATION_CONTEXT
    ):
        obligations.append(RuntimeVerificationObligation(
            VerificationObligationKind.STRUCTURAL_WORLD_CHANGE,
            required_assurance=ObservationAssurance.WEAK,
        ))
    primitive = _primitive_value_obligation(request)
    if primitive is not None:
        obligations.append(primitive)
    return tuple(obligations)


def observation_needs_for_verification(
    request_id: str,
    obligations: tuple[RuntimeVerificationObligation, ...],
) -> tuple[ObservationNeed, ...]:
    """Project sealed evaluator obligations into acquisition needs once."""

    needs: list[ObservationNeed] = []
    for index, obligation in enumerate(obligations):
        purpose = ObservationPurpose.EFFECT_VERIFICATION
        assurance = ObservationAssurance(
            obligation.required_assurance or ObservationAssurance.STRUCTURAL
        )
        modality = (
            ObservationModality.ENVIRONMENT_STATE
            if assurance is ObservationAssurance.AUTHORITATIVE
            else None
        )
        needs.append(ObservationNeed(
            f"verification:{request_id}:{index}",
            purpose,
            tuple(item for item in (obligation.subject_id,) if item),
            modality,
            assurance,
            FreshnessRequirement.FRESH_ACQUISITION,
        ))
    return tuple(needs)


def _primitive_value_obligation(request: BoundActionRequest) -> RuntimeVerificationObligation | None:
    semantic = request.intent.semantic_action
    if request.selection.verification_contract.family is not VerificationFamily.VALUE_STATE:
        return None
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

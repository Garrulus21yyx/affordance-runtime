"""Immutable surface-neutral values exposed across the model boundary."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.actions.space_contracts import ActionRisk
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.world_projection import PublicFactView
from affordance_runtime.immutable import freeze_json
from affordance_runtime.task.contracts import RiskProfile

_GENERATION_REF = re.compile(r"\b[ENFR][1-9][0-9]{0,3}\b")
_LEGACY_EXPIRED_REF = re.compile(r"<expired-ref-[1-9][0-9]{0,3}>", re.IGNORECASE)
_PRIVATE_HISTORY_KEYS = frozenset({"subject_id", "target_id", "destination_id"})


def sanitize_history_value(value: object) -> object:
    """Remove observation-generation identity before a value enters episode history."""

    return _sanitize_history_value(value)


def _sanitize_history_value(value: object) -> object:
    if isinstance(value, str):
        return _strip_generation_refs(value)
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            raw_key = str(key)
            if (
                raw_key in _PRIVATE_HISTORY_KEYS
                or raw_key.endswith("_ref")
                or _GENERATION_REF.fullmatch(raw_key)
            ):
                continue
            clean_key = _strip_generation_refs(raw_key)
            if not clean_key:
                continue
            if isinstance(item, str) and _ref_only(item):
                continue
            sanitized[clean_key] = _sanitize_history_value(item)
        return sanitized
    if isinstance(value, tuple | list):
        return tuple(
            _sanitize_history_value(item)
            for item in value
            if not isinstance(item, str) or not _ref_only(item)
        )
    return value


def _strip_generation_refs(value: str) -> str:
    cleaned = _LEGACY_EXPIRED_REF.sub("", value)
    cleaned = _GENERATION_REF.sub("", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\[\s*\]", "", cleaned)
    cleaned = re.sub(r"\s+([,;:)\]])", r"\1", cleaned)
    cleaned = re.sub(r"([(\[])\s+", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" ,;:-")


def _ref_only(value: str) -> bool:
    return bool(
        _GENERATION_REF.search(value) or _LEGACY_EXPIRED_REF.search(value)
    ) and not _strip_generation_refs(value)


@dataclass(frozen=True)
class AgentSuccessCriterionView:
    criterion_id: str
    definition: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "definition", freeze_json(self.definition))


@dataclass(frozen=True)
class AgentMaterialBindingView:
    name: str
    media_type: str
    public_reference: str


@dataclass(frozen=True)
class AgentCriterionEvaluationView:
    criterion_id: str
    status: str


@dataclass(frozen=True)
class AgentEvaluatedOutputView:
    output_id: str
    value: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", freeze_json(self.value))


@dataclass(frozen=True)
class AgentTaskEvaluationView:
    status: str
    criteria: tuple[AgentCriterionEvaluationView, ...] = ()
    outputs: tuple[AgentEvaluatedOutputView, ...] = ()
    verified_public_facts: tuple[PublicFactView, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "criteria", tuple(self.criteria))
        object.__setattr__(self, "outputs", tuple(self.outputs))
        object.__setattr__(self, "verified_public_facts", tuple(self.verified_public_facts))


class EvidenceRequirementStatus(StrEnum):
    MISSING = "missing"
    CURRENTLY_VISIBLE = "currently_visible"
    RETAINED = "retained"


@dataclass(frozen=True)
class AgentEvidenceRequirementView:
    key: str
    description: str
    status: EvidenceRequirementStatus

    def __post_init__(self) -> None:
        if not self.key or not self.description:
            raise ValueError("active subtask evidence requirement is incomplete")
        if not isinstance(self.status, EvidenceRequirementStatus):
            object.__setattr__(self, "status", EvidenceRequirementStatus(self.status))


@dataclass(frozen=True)
class AgentSubtaskContractView:
    """Bounded semantic contract stored by the episode, without progress state."""

    objective: str
    done_when: str
    task_link: str
    outcome_kind: str
    constraints: tuple[str, ...] = ()
    required_evidence: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "constraints", tuple(self.constraints))
        object.__setattr__(self, "required_evidence", tuple(self.required_evidence))
        if self.outcome_kind not in {"state_change", "evidence_packet"}:
            raise ValueError("active subtask outcome kind is unsupported")
        if len(self.required_evidence) > 32 or len({item[0] for item in self.required_evidence}) != len(
            self.required_evidence
        ):
            raise ValueError("active subtask evidence requirements are invalid")


@dataclass(frozen=True)
class AgentSubtaskView:
    objective: str
    done_when: str
    task_link: str
    outcome_kind: str
    constraints: tuple[str, ...] = ()
    required_evidence: tuple[AgentEvidenceRequirementView, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "constraints", tuple(self.constraints))
        object.__setattr__(self, "required_evidence", tuple(self.required_evidence))
        if self.outcome_kind not in {"state_change", "evidence_packet"}:
            raise ValueError("active subtask outcome kind is unsupported")


@dataclass(frozen=True)
class AgentTaskView:
    task_id: str
    instruction: str
    constraints: BoundedSection[str]
    allowed_effects: BoundedSection[str]
    forbidden_effects: BoundedSection[str]
    success_criteria: BoundedSection[AgentSuccessCriterionView]
    requested_output_ids: BoundedSection[str]
    risk_profile: RiskProfile
    public_inputs: Mapping[str, object] = field(default_factory=dict)
    material_bindings: BoundedSection[AgentMaterialBindingView] = field(
        default_factory=lambda: BoundedSection((), 0, False)
    )
    public_inputs_total_count: int = 0
    public_inputs_truncated: bool = False
    evaluation: AgentTaskEvaluationView = field(
        default_factory=lambda: AgentTaskEvaluationView("unknown")
    )
    final_response_contract: Mapping[str, object] = field(default_factory=dict)
    active_subtask: AgentSubtaskView | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "public_inputs", freeze_json(self.public_inputs))
        object.__setattr__(self, "final_response_contract", freeze_json(self.final_response_contract))
        if self.active_subtask is not None and not isinstance(self.active_subtask, AgentSubtaskView):
            raise TypeError("Task active_subtask must be typed")
        if self.public_inputs_total_count < len(self.public_inputs):
            raise ValueError("public input total cannot be smaller than its projection")
        if self.public_inputs_truncated != (self.public_inputs_total_count > len(self.public_inputs)):
            raise ValueError("public input truncation metadata is untruthful")


@dataclass(frozen=True)
class AgentDestinationView:
    destination_id: str
    label: str
    grounding_ref: str = ""
    semantics: Mapping[str, object] = field(default_factory=dict)
    grounding_rendered: bool = False
    grounding_context_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "semantics", freeze_json(self.semantics))
        if self.grounding_ref and re.fullmatch(r"E[1-9][0-9]{0,2}", self.grounding_ref) is None:
            raise ValueError("destination grounding ref is invalid")
        if any((self.grounding_ref, self.semantics, self.grounding_context_id)) and not all(
            (self.grounding_ref, self.semantics, self.grounding_context_id)
        ):
            raise ValueError("destination candidate projection is incomplete")


@dataclass(frozen=True)
class AgentActionOptionView:
    action_id: str
    semantic_action: str
    target_id: str
    target_label: str
    destination_required: bool
    destinations: BoundedSection[AgentDestinationView]
    parameter_schema: Mapping[str, object]
    description: str
    semantic_effects: tuple[str, ...]
    risk: ActionRisk
    observation_barrier: bool
    effect_category: str = ""
    consequence_class: str = ""
    reversible: bool = True
    relevance_role: str = "other"
    relevance_score: float = 0.0
    relevance_reason_codes: tuple[str, ...] = ()
    operation: str = ""
    target_ref: str = ""
    target_semantics: Mapping[str, object] = field(default_factory=dict)
    target_role: str = ""
    target_state: Mapping[str, object] = field(default_factory=dict)
    target_marked: bool = False
    destination_mode: str = ""
    grounding_context_id: str = ""
    subject_kind: str = "entity"
    verification_family: str = ""
    verification_contract_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameter_schema", freeze_json(self.parameter_schema))
        object.__setattr__(self, "semantic_effects", tuple(self.semantic_effects))
        object.__setattr__(self, "relevance_reason_codes", tuple(self.relevance_reason_codes))
        object.__setattr__(self, "target_semantics", freeze_json(self.target_semantics))
        object.__setattr__(self, "target_state", freeze_json(self.target_state))
        closed = bool(
            self.operation
            and self.target_ref
            and self.target_semantics
            and self.target_role
            and self.destination_mode
            and self.grounding_context_id
        )
        if any(
            (
                self.operation,
                self.target_ref,
                self.target_semantics,
                self.target_role,
                self.target_state,
                self.destination_mode,
                self.grounding_context_id,
            )
        ) and not closed:
            raise ValueError("action candidate target projection is incomplete")
        if self.target_ref and re.fullmatch(r"E[1-9][0-9]{0,2}", self.target_ref) is None:
            raise ValueError("action candidate target ref is invalid")
        if self.destination_mode and self.destination_mode not in {"forbidden", "required", "optional"}:
            raise ValueError("action candidate destination mode is invalid")
        if self.destination_mode == "required" and not self.destination_required:
            raise ValueError("required destination mode must conserve the ActionOption contract")
        if self.destination_mode == "forbidden" and self.destination_required:
            raise ValueError("forbidden destination mode cannot require a destination")


@dataclass(frozen=True)
class AgentActionSpaceView:
    options: tuple[AgentActionOptionView, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", tuple(self.options))


@dataclass(frozen=True)
class AgentActionPageView:
    options: tuple[AgentActionOptionView, ...]
    total_count: int
    page_size: int
    truncated: bool
    has_more: bool
    available_filters: tuple[str, ...] = ()
    active_query: str = ""
    active_target_filter: str = ""
    active_relevance_filter: str = ""
    next_cursor: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", tuple(self.options))
        object.__setattr__(self, "available_filters", tuple(self.available_filters))
        if self.total_count < len(self.options) or self.page_size != len(self.options):
            raise ValueError("action page counts are inconsistent")
        if self.truncated != (self.total_count > len(self.options)):
            raise ValueError("action page truncation metadata is untruthful")
        if self.has_more != bool(self.next_cursor):
            raise ValueError("action page has_more requires a usable next cursor")


@dataclass(frozen=True)
class AgentHistoricalTargetView:
    """A ref-free semantic description safe to carry across observation generations."""

    role: str
    label: str
    context: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", tuple(self.context))
        if any(not isinstance(item, str) or len(item) > 240 for item in self.context):
            raise ValueError("historical target context must contain bounded strings")


@dataclass(frozen=True)
class AgentTurnView:
    decision_kind: str
    semantic_action: str = ""
    target: AgentHistoricalTargetView | None = None
    destination: AgentHistoricalTargetView | None = None
    public_parameters: Mapping[str, object] = field(default_factory=dict)
    expected_outcome: str = ""
    dispatch_status: str = ""
    local_postcondition: str = ""
    transition: Mapping[str, object] = field(default_factory=dict)
    task_evaluation_status: str = ""
    reason: str = ""
    semantic_summary: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.target is not None and not isinstance(self.target, AgentHistoricalTargetView):
            raise TypeError("turn target must be a ref-free semantic description")
        if self.destination is not None and not isinstance(self.destination, AgentHistoricalTargetView):
            raise TypeError("turn destination must be a ref-free semantic description")
        object.__setattr__(self, "public_parameters", freeze_json(self.public_parameters))
        if not isinstance(self.expected_outcome, str) or len(self.expected_outcome) > 240:
            raise ValueError("turn expected outcome must be one bounded string")
        object.__setattr__(self, "expected_outcome", self.expected_outcome.strip())
        object.__setattr__(self, "transition", freeze_json(self.transition))
        object.__setattr__(self, "semantic_summary", freeze_json(self.semantic_summary))

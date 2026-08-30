"""Immutable surface-neutral values exposed across the model boundary."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from affordance_runtime.actions.effect_semantics import Reversibility
from affordance_runtime.actions.space_contracts import ActionRisk
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.world_projection import PublicFactView
from affordance_runtime.immutable import freeze_json
from affordance_runtime.task.contracts import RiskProfile
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind

_LEGACY_EXPIRED_REF = re.compile(r"<expired-ref-[1-9][0-9]*>", re.IGNORECASE)
HISTORY_ARGUMENT_PATHS_METADATA_KEY = "affordance_runtime.history.argument_paths.v1"
HISTORY_RETURN_PATHS_METADATA_KEY = "affordance_runtime.history.return_paths.v1"
HISTORY_CANONICAL_METADATA_KEY = "affordance_runtime.history.canonical.v1"
def sanitize_history_value(value: object) -> object:
    """Preserve producer-owned semantics while removing legacy tombstones.

    This function is deliberately not an authority detector.  A mapping key
    such as ``target_ref`` can be legitimate business data, just as ``E6`` can
    be a product code.  Operational values expire only through producer-owned
    paths passed to :func:`sanitize_history_arguments` or through a dedicated
    semantic projection at the producer boundary.
    """

    return _sanitize_legacy_value(value)


def sanitize_history_arguments(
    value: object,
    *,
    ephemeral_paths: Iterable[tuple[str, ...]] = (),
) -> object:
    """Project one call/result using paths declared by its owning producer."""

    stripped = _strip_history_paths(value, tuple(tuple(path) for path in ephemeral_paths))
    return {} if stripped is _DROP_HISTORY_VALUE else _sanitize_legacy_value(stripped)


def history_operational_refs(
    value: object,
    *,
    ephemeral_paths: Iterable[tuple[str, ...]] = (),
) -> frozenset[str]:
    """Collect refs only from explicit ref-bearing protocol fields.

    This is deliberately not a lexical scan.  Values under ``label``, ``text``,
    ``query`` and other semantic fields remain ordinary data even when they
    look like a public ref.
    """

    refs: set[str] = set()

    def add(item: object) -> None:
        if isinstance(item, str) and PublicRefCodec.accepts(item):
            refs.add(item)
        elif isinstance(item, Mapping):
            for key, child in item.items():
                if PublicRefCodec.accepts(str(key)):
                    refs.add(str(key))
                add(child)
        elif isinstance(item, tuple | list):
            for child in item:
                add(child)

    for item in _history_path_values(value, tuple(tuple(path) for path in ephemeral_paths)):
        add(item)
    return frozenset(refs)


def sanitize_history_prose(value: str) -> str:
    """Preserve semantic prose; free text never carries ref authority."""

    return _LEGACY_EXPIRED_REF.sub("", value).strip()


_DROP_HISTORY_VALUE = object()


def _strip_history_paths(
    value: object,
    paths: tuple[tuple[str, ...], ...],
) -> object:
    if () in paths:
        return _DROP_HISTORY_VALUE
    if isinstance(value, Mapping):
        projected: dict[str, object] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            child_paths = tuple(path[1:] for path in paths if path and path[0] == key)
            child_value = _strip_history_paths(child, child_paths)
            if child_value is not _DROP_HISTORY_VALUE:
                projected[key] = child_value
        return projected
    if isinstance(value, tuple | list):
        child_paths = tuple(path[1:] for path in paths if path and path[0] == "*")
        projected_items = tuple(
            child_value
            for item in value
            for child_value in (_strip_history_paths(item, child_paths),)
            if child_value is not _DROP_HISTORY_VALUE
        )
        return projected_items
    return value


def _history_path_values(
    value: object,
    paths: tuple[tuple[str, ...], ...],
) -> tuple[object, ...]:
    found: list[object] = []
    for path in paths:
        frontier = (value,)
        for segment in path:
            next_frontier: list[object] = []
            for item in frontier:
                if segment == "*" and isinstance(item, tuple | list):
                    next_frontier.extend(item)
                elif isinstance(item, Mapping) and segment in item:
                    next_frontier.append(item[segment])
            frontier = tuple(next_frontier)
        found.extend(frontier)
    return tuple(found)


def _sanitize_legacy_value(value: object) -> object:
    if isinstance(value, str):
        return _LEGACY_EXPIRED_REF.sub("", value)
    if isinstance(value, Mapping):
        return {
            _LEGACY_EXPIRED_REF.sub("", str(key)): _sanitize_legacy_value(item)
            for key, item in value.items()
            if _LEGACY_EXPIRED_REF.sub("", str(key))
        }
    if isinstance(value, tuple | list):
        return tuple(_sanitize_legacy_value(item) for item in value)
    return value


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
    evaluation: AgentTaskEvaluationView = field(default_factory=lambda: AgentTaskEvaluationView("unknown"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "public_inputs", freeze_json(self.public_inputs))
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
        if self.grounding_ref and not PublicRefCodec.accepts(self.grounding_ref, expected=PublicRefKind.EXECUTABLE):
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
    reversibility: Reversibility = Reversibility.UNKNOWN
    resource_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameter_schema", freeze_json(self.parameter_schema))
        object.__setattr__(self, "semantic_effects", tuple(self.semantic_effects))
        object.__setattr__(self, "relevance_reason_codes", tuple(self.relevance_reason_codes))
        object.__setattr__(self, "target_semantics", freeze_json(self.target_semantics))
        object.__setattr__(self, "target_state", freeze_json(self.target_state))
        if not isinstance(self.reversibility, Reversibility):
            raise TypeError("model action reversibility must be typed")
        object.__setattr__(self, "resource_ref", self.resource_ref.strip() or self.target_id)
        closed = bool(
            self.operation
            and self.target_ref
            and self.target_semantics
            and self.target_role
            and self.destination_mode
            and self.grounding_context_id
        )
        if (
            any(
                (
                    self.operation,
                    self.target_ref,
                    self.target_semantics,
                    self.target_role,
                    self.target_state,
                    self.destination_mode,
                    self.grounding_context_id,
                )
            )
            and not closed
        ):
            raise ValueError("action candidate target projection is incomplete")
        if self.target_ref and not PublicRefCodec.accepts(self.target_ref, expected=PublicRefKind.EXECUTABLE):
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
    active_query: str = ""
    next_cursor: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", tuple(self.options))
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

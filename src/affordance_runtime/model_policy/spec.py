"""Canonical closed structured model decision specification."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, RootModel, StrictInt, StringConstraints, field_validator

from affordance_runtime.agent.decisions import (
    MAX_RESULT_SUMMARY_CHARS,
    Abort,
    AgentDecision,
    AgentDecisionPackage,
    AskUser,
    EstablishAggregateObjective,
    EstablishObjectiveSequence,
    EstablishSetObjective,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    SetPredicateAssessmentDecision,
    SubmitSetPredicateAssessments,
    Wait,
)
from affordance_runtime.model_policy.strict_json import strict_json_loads, validate_json_tree
from affordance_runtime.task.aggregate_objective import (
    AggregateObjective,
    AggregateOperator,
    AggregateOutputFormat,
    ValueExtractor,
    ValueExtractorKind,
)
from affordance_runtime.task.frontier_contracts import (
    FactAvailable,
    FactReferenceExpected,
    LiteralExpected,
    NoObjectiveOperation,
    ProposeObjective,
    ReplaceObjective,
    RetainObjective,
    TargetAbsent,
    TargetFieldEquals,
    TargetPresent,
    TaskOutcomeIs,
    TaskOutcomeStatus,
)
from affordance_runtime.task.objective_sequence import (
    EntitySelector,
    ObjectiveSequence,
    ObjectiveStep,
)
from affordance_runtime.task.predicate_transport import predicate_from_public_value
from affordance_runtime.task.set_objective import (
    ActionTemplate,
    PredicateTruth,
    ScopeEntityDomain,
    ScopeExtent,
    ScopeSpec,
    SetQuantifier,
)
from affordance_runtime.world.schema_validation import reject_private_parameter_values

SCHEMA_VERSION = "agent-decision-package.v2"

ContextId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Id240 = Annotated[str, StringConstraints(min_length=1, max_length=240)]
Optional120 = Annotated[str, StringConstraints(max_length=120)]
Optional240 = Annotated[str, StringConstraints(max_length=240)]
Optional512 = Annotated[str, StringConstraints(max_length=512)]
Reason500 = Annotated[str, StringConstraints(min_length=1, max_length=500)]
Question1000 = Annotated[str, StringConstraints(min_length=1, max_length=1_000)]
Summary1024 = Annotated[str, StringConstraints(min_length=1, max_length=MAX_RESULT_SUMMARY_CHARS)]
Item120 = Annotated[str, StringConstraints(min_length=1, max_length=120)]
Item240 = Annotated[str, StringConstraints(min_length=1, max_length=240)]
Item500 = Annotated[str, StringConstraints(min_length=1, max_length=500)]
Item512 = Annotated[str, StringConstraints(min_length=1, max_length=512)]


class _Payload(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    context_id: ContextId


class SelectActionPayload(_Payload):
    type: Literal["select_action"]
    action_id: Id240
    parameters: dict[str, Any]
    destination_id: Optional240

    @field_validator("parameters")
    @classmethod
    def _bounded_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_json_tree(value)
        reject_private_parameter_values(value)
        return value


class EstablishSetObjectivePayload(_Payload):
    type: Literal["establish_set_objective"]
    predicate: dict[str, Any]
    quantifier: Literal["exactly_one", "all_in_closed_scope"]
    semantic_action: Id240
    candidate_target_ids: Annotated[list[Id240], Field(max_length=256)]
    parameters: dict[str, Any]
    scope_extent: Literal[
        "current_viewport",
        "current_container",
        "current_document",
        "current_application_state",
    ] = "current_viewport"
    scope_root_target_id: Id240 = "current-viewport"

    @field_validator("predicate")
    @classmethod
    def _supported_predicate(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_json_tree(value)
        predicate_from_public_value(value)
        return value

    @field_validator("parameters")
    @classmethod
    def _bounded_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_json_tree(value)
        reject_private_parameter_values(value)
        return value


class ObjectiveSequenceStepPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    step_id: Id240
    selector: dict[str, Any]
    semantic_action: Id240
    parameters: dict[str, Any]
    postcondition: dict[str, Any] | None = None

    @field_validator("selector")
    @classmethod
    def _selector(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_json_tree(value)
        predicate_from_public_value(value)
        return value

    @field_validator("postcondition")
    @classmethod
    def _postcondition(cls, value: dict[str, Any] | None):
        if value is not None:
            validate_json_tree(value)
            predicate_from_public_value(value)
        return value

    @field_validator("parameters")
    @classmethod
    def _parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_json_tree(value)
        reject_private_parameter_values(value)
        return value


class EstablishObjectiveSequencePayload(_Payload):
    type: Literal["establish_objective_sequence"]
    sequence_id: Id240
    steps: Annotated[list[ObjectiveSequenceStepPayload], Field(min_length=1, max_length=8)]


class EstablishAggregateObjectivePayload(_Payload):
    type: Literal["establish_aggregate_objective"]
    objective_id: Id240
    scope_id: Id240
    scope_extent: Literal[
        "current_viewport",
        "current_container",
        "current_document",
        "current_application_state",
    ]
    scope_root_target_id: Id240
    scope_entity_domain: Literal["structured", "all_visible", "fused"]
    member_predicate: dict[str, Any]
    value_extractor_kind: Literal["constant", "fact"]
    value_field: Optional120
    constant: float
    operator: Literal["count", "sum", "min", "max"]
    destination_predicate: dict[str, Any]
    semantic_action: Id240
    parameter_name: Item120
    output_format: Literal["integer_string", "decimal_string", "number"]

    @field_validator("member_predicate", "destination_predicate")
    @classmethod
    def _predicate(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_json_tree(value)
        predicate_from_public_value(value)
        return value


class SetPredicateAssessmentPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    target_id: Id240
    truth: Literal["true", "false", "unknown"]


class SubmitSetPredicateAssessmentsPayload(_Payload):
    type: Literal["submit_set_predicate_assessments"]
    predicate_digest: Annotated[str, StringConstraints(pattern=r"[0-9a-f]{64}")]
    assessments: Annotated[
        list[SetPredicateAssessmentPayload],
        Field(min_length=1, max_length=256),
    ]


class RequestObservationPayload(_Payload):
    type: Literal["request_observation"]
    subject_id: Id240
    modality: Literal["structural", "visual", "environment_state", "user"]
    required_assurance: Literal["weak", "structural", "authoritative"]
    reason: Reason500
    cursor: Optional512 = ""


class RequestActionPagePayload(_Payload):
    type: Literal["request_action_page"]
    query: Optional120
    target_id: Optional240
    relevance_role: Literal["direct", "enabling", "information", "other", ""]
    cursor: Optional512


class AskUserPayload(_Payload):
    type: Literal["ask_user"]
    question: Question1000
    requested_fields: Annotated[list[Item120], Field(max_length=32)]


class ProposeDonePayload(_Payload):
    type: Literal["propose_done"]
    claimed_criteria: Annotated[list[Item240], Field(max_length=32)]
    evidence_refs: Annotated[list[Item512], Field(max_length=32)]
    result_summary: Summary1024
    unresolved_items: Annotated[list[Item500], Field(max_length=32)]


class WaitPayload(_Payload):
    type: Literal["wait"]
    reason: Reason500
    max_wait_ms: Annotated[StrictInt, Field(ge=1, le=60_000)]

    @field_validator("max_wait_ms", mode="before")
    @classmethod
    def _strict_wait_duration(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("wait duration must be a JSON integer")
        return value


class AbortPayload(_Payload):
    type: Literal["abort"]
    reason: Reason500
    category: Literal["policy", "safety", "unsupported", "no_progress", "user_request"]


DecisionPayload: TypeAlias = Annotated[
    SelectActionPayload
    | EstablishAggregateObjectivePayload
    | EstablishObjectiveSequencePayload
    | EstablishSetObjectivePayload
    | SubmitSetPredicateAssessmentsPayload
    | RequestObservationPayload
    | RequestActionPagePayload
    | AskUserPayload
    | ProposeDonePayload
    | WaitPayload
    | AbortPayload,
    Field(discriminator="type"),
]


class AgentDecisionPayload(RootModel[DecisionPayload]):
    model_config = ConfigDict(
        frozen=True,
        revalidate_instances="always",
    )

    @classmethod
    def model_validate(cls, obj, **kwargs):
        # The discriminated union must first construct its strict frozen payload
        # model from a JSON object (or an immutable mapping used by deterministic
        # ports). Field contracts remain strict; no legacy object fallback exists.
        _require_json_collection_types(obj)
        kwargs.setdefault("strict", False)
        return super().model_validate(obj, **kwargs)

    @classmethod
    def model_validate_json(cls, json_data: str | bytes | bytearray, **kwargs):
        del kwargs
        raw = bytes(json_data).decode() if isinstance(json_data, bytes | bytearray) else json_data
        return cls.model_validate(strict_json_loads(raw))


class _ObjectivePayload(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )


class FactAvailablePayload(_ObjectivePayload):
    kind: Literal["fact_available"]
    fact_ref: Id240


class LiteralExpectedPayload(_ObjectivePayload):
    kind: Literal["literal"]
    value: str | StrictInt | float | bool | None


class FactReferenceExpectedPayload(_ObjectivePayload):
    kind: Literal["fact_ref"]
    fact_ref: Id240


ExpectedPayload: TypeAlias = Annotated[
    LiteralExpectedPayload | FactReferenceExpectedPayload,
    Field(discriminator="kind"),
]


class TargetFieldEqualsPayload(_ObjectivePayload):
    kind: Literal["target_field_equals"]
    target_id: Id240
    field_name: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    expected: ExpectedPayload


class TargetPresentPayload(_ObjectivePayload):
    kind: Literal["target_present"]
    target_id: Id240


class TargetAbsentPayload(_ObjectivePayload):
    kind: Literal["target_absent"]
    target_id: Id240


class TaskOutcomeIsPayload(_ObjectivePayload):
    kind: Literal["task_outcome_is"]
    status: Literal["complete", "incomplete", "unknown", "blocked"]


PredicatePayload: TypeAlias = Annotated[
    FactAvailablePayload | TargetFieldEqualsPayload | TargetPresentPayload | TargetAbsentPayload | TaskOutcomeIsPayload,
    Field(discriminator="kind"),
]


class NoObjectiveOperationPayload(_ObjectivePayload):
    kind: Literal["none"]


class ProposeObjectivePayload(_ObjectivePayload):
    kind: Literal["propose"]
    intended_requirement_ids: Annotated[list[Id240], Field(min_length=1, max_length=32)]
    predicate: PredicatePayload


class RetainObjectivePayload(_ObjectivePayload):
    kind: Literal["retain"]
    active_objective_id: Id240


class ReplaceObjectivePayload(_ObjectivePayload):
    kind: Literal["replace"]
    replaces_objective_id: Id240
    intended_requirement_ids: Annotated[list[Id240], Field(min_length=1, max_length=32)]
    predicate: PredicatePayload


ObjectiveOperationPayload: TypeAlias = Annotated[
    NoObjectiveOperationPayload | ProposeObjectivePayload | RetainObjectivePayload | ReplaceObjectivePayload,
    Field(discriminator="kind"),
]


class AgentDecisionPackagePayload(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
    )

    objective_operation: ObjectiveOperationPayload
    decision: DecisionPayload

    @classmethod
    def model_validate(cls, obj, **kwargs):
        _require_json_collection_types(obj)
        if isinstance(obj, dict) and "objective_operation" not in obj and "type" in obj:
            obj = {"objective_operation": {"kind": "none"}, "decision": obj}
        kwargs.setdefault("strict", False)
        return super().model_validate(obj, **kwargs)

    @classmethod
    def model_validate_json(cls, json_data: str | bytes | bytearray, **kwargs):
        del kwargs
        raw = bytes(json_data).decode() if isinstance(json_data, bytes | bytearray) else json_data
        return cls.model_validate(strict_json_loads(raw))


def decision_response_schema() -> dict[str, Any]:
    return AgentDecisionPackagePayload.model_json_schema()


def _require_json_collection_types(value: object) -> None:
    """Allow immutable mappings at deterministic ports, but never sequence coercion."""

    from collections.abc import Mapping, Sequence

    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, Sequence) and not isinstance(item, str | bytes | bytearray):
            raise TypeError("structured decision arrays must be JSON lists")
        elif isinstance(item, set | frozenset):
            raise TypeError("structured decision arrays must be JSON lists")


def payload_to_decision(payload: AgentDecisionPayload, expected_context_id: str) -> AgentDecision:
    value = payload.root
    if value.context_id != expected_context_id:
        raise ValueError("decision context is stale")
    if isinstance(value, SelectActionPayload):
        return SelectAction(value.context_id, value.action_id, value.parameters, value.destination_id)
    if isinstance(value, EstablishObjectiveSequencePayload):
        return EstablishObjectiveSequence(
            value.context_id,
            ObjectiveSequence(
                value.sequence_id,
                tuple(
                    ObjectiveStep(
                        item.step_id,
                        EntitySelector(predicate_from_public_value(item.selector)),
                        ActionTemplate(item.semantic_action, parameters=item.parameters),
                        (
                            EntitySelector(predicate_from_public_value(item.postcondition))
                            if item.postcondition is not None
                            else None
                        ),
                    )
                    for item in value.steps
                ),
            ),
        )
    if isinstance(value, EstablishAggregateObjectivePayload):
        return EstablishAggregateObjective(
            value.context_id,
            AggregateObjective(
                value.objective_id,
                ScopeSpec(
                    value.scope_id,
                    value.scope_root_target_id,
                    ScopeExtent(value.scope_extent),
                    entity_domain=ScopeEntityDomain(value.scope_entity_domain),
                ),
                predicate_from_public_value(value.member_predicate),
                ValueExtractor(
                    ValueExtractorKind(value.value_extractor_kind),
                    value.value_field,
                    value.constant,
                ),
                AggregateOperator(value.operator),
                predicate_from_public_value(value.destination_predicate),
                value.semantic_action,
                value.parameter_name,
                AggregateOutputFormat(value.output_format),
            ),
        )
    if isinstance(value, EstablishSetObjectivePayload):
        return EstablishSetObjective(
            value.context_id,
            predicate_from_public_value(value.predicate),
            SetQuantifier(value.quantifier),
            value.semantic_action,
            tuple(value.candidate_target_ids),
            value.parameters,
            ScopeExtent(value.scope_extent),
            value.scope_root_target_id,
        )
    if isinstance(value, SubmitSetPredicateAssessmentsPayload):
        return SubmitSetPredicateAssessments(
            value.context_id,
            value.predicate_digest,
            tuple(
                SetPredicateAssessmentDecision(
                    item.target_id,
                    PredicateTruth(item.truth),
                    None,
                )
                for item in value.assessments
            ),
        )
    if isinstance(value, RequestObservationPayload):
        return RequestObservation(
            value.context_id,
            value.subject_id,
            value.modality,
            value.required_assurance,
            value.reason,
            value.cursor,
        )
    if isinstance(value, RequestActionPagePayload):
        return RequestActionPage(
            value.context_id,
            value.query,
            value.target_id,
            value.relevance_role,
            value.cursor,
        )
    if isinstance(value, AskUserPayload):
        return AskUser(value.context_id, value.question, tuple(value.requested_fields))
    if isinstance(value, ProposeDonePayload):
        return ProposeDone(
            value.context_id,
            tuple(value.claimed_criteria),
            tuple(value.evidence_refs),
            value.result_summary,
            tuple(value.unresolved_items),
        )
    if isinstance(value, WaitPayload):
        return Wait(value.context_id, value.reason, value.max_wait_ms)
    return Abort(value.context_id, value.reason, value.category)


def payload_to_package(
    payload: AgentDecisionPackagePayload,
    expected_context_id: str,
) -> AgentDecisionPackage:
    decision = payload_to_decision(
        AgentDecisionPayload(root=payload.decision),
        expected_context_id,
    )
    return AgentDecisionPackage(
        _payload_to_objective_operation(payload.objective_operation),
        decision,
    )


def _payload_to_objective_operation(payload):
    if isinstance(payload, NoObjectiveOperationPayload):
        return NoObjectiveOperation()
    if isinstance(payload, RetainObjectivePayload):
        return RetainObjective(payload.active_objective_id)
    predicate = _payload_to_predicate(payload.predicate)
    if isinstance(payload, ProposeObjectivePayload):
        return ProposeObjective(tuple(payload.intended_requirement_ids), predicate)
    assert isinstance(payload, ReplaceObjectivePayload)
    return ReplaceObjective(
        payload.replaces_objective_id,
        tuple(payload.intended_requirement_ids),
        predicate,
    )


def _payload_to_predicate(payload):
    if isinstance(payload, FactAvailablePayload):
        return FactAvailable(payload.fact_ref)
    if isinstance(payload, TargetPresentPayload):
        return TargetPresent(payload.target_id)
    if isinstance(payload, TargetAbsentPayload):
        return TargetAbsent(payload.target_id)
    if isinstance(payload, TaskOutcomeIsPayload):
        return TaskOutcomeIs(TaskOutcomeStatus(payload.status))
    assert isinstance(payload, TargetFieldEqualsPayload)
    expected = (
        LiteralExpected(payload.expected.value)
        if isinstance(payload.expected, LiteralExpectedPayload)
        else FactReferenceExpected(payload.expected.fact_ref)
    )
    return TargetFieldEquals(payload.target_id, payload.field_name, expected)

"""Closed model transport for authority-free LocalObjective proposals."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, RootModel, StringConstraints, field_validator

from affordance_runtime.agent.local_objective_proposal import (
    LocalObjectiveNeedsInput,
    LocalObjectiveNotRequired,
    LocalObjectiveProposal,
    LocalObjectiveResolvedOutcome,
    LocalObjectiveUnsupported,
    LocalObjectiveUnsupportedReason,
)
from affordance_runtime.model_policy.strict_json import (
    require_json_collection_types,
    strict_json_loads,
    validate_json_tree,
)
from affordance_runtime.task.aggregate_objective import (
    AggregateObjective,
    AggregateOperator,
    AggregateOutputFormat,
    ValueExtractor,
    ValueExtractorKind,
)
from affordance_runtime.task.objective_sequence import EntitySelector, ObjectiveSequence, ObjectiveStep
from affordance_runtime.task.predicate_transport import (
    NormalizedPredicatePayload,
    predicate_from_transport,
)
from affordance_runtime.task.set_objective import (
    ActionTemplate,
    SchedulingPolicy,
    ScopeEntityDomain,
    ScopeExtent,
    ScopeSpec,
    SetObjective,
    SetQuantifier,
)
from affordance_runtime.world.schema_validation import reject_private_parameter_values

OBJECTIVE_SCHEMA_VERSION = "local-objective-proposal.v2"

ContextId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Id240 = Annotated[str, StringConstraints(min_length=1, max_length=240)]
Optional120 = Annotated[str, StringConstraints(max_length=120)]
Item120 = Annotated[str, StringConstraints(min_length=1, max_length=120)]


class LocalObjectiveStepPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    predicate: NormalizedPredicatePayload
    entity_domain: Literal["structured", "all_visible", "fused"] = "structured"
    semantic_action: Id240
    parameters: dict[str, Any] = Field(default_factory=dict)
    postcondition: NormalizedPredicatePayload | None = None

    @field_validator("parameters")
    @classmethod
    def _parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_json_tree(value)
        reject_private_parameter_values(value)
        return value


class SequenceLocalObjectivePayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    kind: Literal["sequence"]
    steps: Annotated[list[LocalObjectiveStepPayload], Field(min_length=1, max_length=8)]


class SetLocalObjectivePayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    kind: Literal["set"]
    scope_extent: Literal[
        "current_viewport", "current_container", "current_document", "current_application_state"
    ] = "current_viewport"
    entity_domain: Literal["structured", "all_visible", "fused"] = "structured"
    predicate: NormalizedPredicatePayload
    quantifier: Literal[
        "exactly_one", "all_in_closed_scope", "all_currently_visible", "all_discovered_under_budget"
    ]
    semantic_action: Id240
    parameters: dict[str, Any] = Field(default_factory=dict)
    postcondition: NormalizedPredicatePayload | None = None

    @field_validator("parameters")
    @classmethod
    def _parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_json_tree(value)
        reject_private_parameter_values(value)
        return value


class AggregateLocalObjectivePayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    kind: Literal["aggregate"]
    scope_extent: Literal[
        "current_viewport", "current_container", "current_document", "current_application_state"
    ] = "current_viewport"
    entity_domain: Literal["structured", "all_visible", "fused"] = "structured"
    predicate: NormalizedPredicatePayload
    value_extractor_kind: Literal["constant", "fact"]
    value_field: Optional120 = ""
    constant: float = 1
    operator: Literal["count", "sum", "min", "max"]
    destination_predicate: NormalizedPredicatePayload
    semantic_action: Id240 = "type_text"
    parameter_name: Item120 = "text"
    output_format: Literal["integer_string", "decimal_string", "number"] = "integer_string"


LocalObjectiveSpecPayload: TypeAlias = Annotated[
    SequenceLocalObjectivePayload | SetLocalObjectivePayload | AggregateLocalObjectivePayload,
    Field(discriminator="kind"),
]


class LocalObjectiveProposalPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, revalidate_instances="always")
    type: Literal["local_objective_proposal"]
    context_id: ContextId
    objective: LocalObjectiveSpecPayload


class LocalObjectiveNotRequiredPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    type: Literal["local_objective_not_required"]
    context_id: ContextId


class LocalObjectiveNeedsInputPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    type: Literal["local_objective_needs_input"]
    context_id: ContextId
    question: Annotated[str, StringConstraints(min_length=1, max_length=1_000)]
    requested_fields: Annotated[list[Item120], Field(max_length=32)] = Field(default_factory=list)


class LocalObjectiveUnsupportedPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    type: Literal["local_objective_unsupported"]
    context_id: ContextId
    reason_code: Literal["no_resolvable_objective", "task_semantics_unsupported"]
    reason: Annotated[str, StringConstraints(min_length=1, max_length=500)]


LocalObjectiveOutcomePayload: TypeAlias = Annotated[
    LocalObjectiveProposalPayload
    | LocalObjectiveNotRequiredPayload
    | LocalObjectiveNeedsInputPayload
    | LocalObjectiveUnsupportedPayload,
    Field(discriminator="type"),
]


class LocalObjectiveOutcomeResponse(RootModel[LocalObjectiveOutcomePayload]):
    model_config = ConfigDict(frozen=True, revalidate_instances="always")

    @classmethod
    def model_validate(cls, obj, **kwargs):
        require_json_collection_types(obj)
        kwargs.setdefault("strict", False)
        return super().model_validate(obj, **kwargs)

    @classmethod
    def model_validate_json(cls, json_data: str | bytes | bytearray, **kwargs):
        del kwargs
        raw = bytes(json_data).decode() if isinstance(json_data, bytes | bytearray) else json_data
        return cls.model_validate(strict_json_loads(raw))


def local_objective_response_schema() -> dict[str, Any]:
    return LocalObjectiveOutcomeResponse.model_json_schema()


def payload_to_local_objective_proposal(
    payload: LocalObjectiveOutcomeResponse,
    expected_context_id: str,
) -> LocalObjectiveProposal:
    value = payload.root
    if not isinstance(value, LocalObjectiveProposalPayload):
        raise ValueError("objective outcome is not a proposal")
    if value.context_id != expected_context_id:
        raise ValueError("local objective proposal context is stale")
    return LocalObjectiveProposal(value.context_id, local_objective_from_payload(value.objective))


def payload_to_local_objective_outcome(
    payload: LocalObjectiveOutcomeResponse,
    expected_context_id: str,
) -> LocalObjectiveResolvedOutcome:
    value = payload.root
    if value.context_id != expected_context_id:
        raise ValueError("local objective outcome context is stale")
    if isinstance(value, LocalObjectiveProposalPayload):
        return LocalObjectiveProposal(
            value.context_id,
            local_objective_from_payload(value.objective),
        )
    if isinstance(value, LocalObjectiveNotRequiredPayload):
        return LocalObjectiveNotRequired(value.context_id)
    if isinstance(value, LocalObjectiveNeedsInputPayload):
        return LocalObjectiveNeedsInput(
            value.context_id,
            value.question,
            tuple(value.requested_fields),
        )
    return LocalObjectiveUnsupported(
        value.context_id,
        LocalObjectiveUnsupportedReason(value.reason_code),
        value.reason,
    )


# Temporary transport-schema name compatibility for callers that only construct
# the proposed branch. New code should use LocalObjectiveOutcomeResponse.
LocalObjectiveProposalResponse = LocalObjectiveOutcomeResponse


def local_objective_from_payload(payload: LocalObjectiveSpecPayload):
    if isinstance(payload, SequenceLocalObjectivePayload):
        digest = _local_objective_payload_digest(payload)
        return ObjectiveSequence(
            f"sequence:{digest}",
            tuple(
                ObjectiveStep(
                    f"step:{index + 1}",
                    EntitySelector(
                        predicate_from_transport(item.predicate),
                        ScopeEntityDomain(item.entity_domain),
                    ),
                    ActionTemplate(item.semantic_action, parameters=item.parameters),
                    EntitySelector(
                        predicate_from_transport(item.postcondition),
                        ScopeEntityDomain(item.entity_domain),
                    )
                    if item.postcondition is not None
                    else None,
                )
                for index, item in enumerate(payload.steps)
            ),
        )
    digest = _local_objective_payload_digest(payload)
    scope = ScopeSpec(
        f"scope:{digest}",
        _scope_root(payload.scope_extent),
        ScopeExtent(payload.scope_extent),
        entity_domain=ScopeEntityDomain(payload.entity_domain),
    )
    if isinstance(payload, SetLocalObjectivePayload):
        return SetObjective(
            f"set-objective:{digest}",
            scope,
            predicate_from_transport(payload.predicate),
            SetQuantifier(payload.quantifier),
            ActionTemplate(
                payload.semantic_action,
                item_postcondition=(
                    predicate_from_transport(payload.postcondition)
                    if payload.postcondition is not None
                    else None
                ),
                parameters=payload.parameters,
            ),
            SchedulingPolicy(),
        )
    return AggregateObjective(
        f"aggregate-objective:{digest}",
        scope,
        predicate_from_transport(payload.predicate),
        ValueExtractor(
            ValueExtractorKind(payload.value_extractor_kind),
            payload.value_field,
            payload.constant,
        ),
        AggregateOperator(payload.operator),
        predicate_from_transport(payload.destination_predicate),
        payload.semantic_action,
        payload.parameter_name,
        AggregateOutputFormat(payload.output_format),
    )


def _local_objective_payload_digest(payload: LocalObjectiveSpecPayload) -> str:
    encoded = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()[:24]


def _scope_root(extent: str) -> str:
    return {
        "current_viewport": "current-viewport",
        "current_container": "current-container",
        "current_document": "current-document",
        "current_application_state": "current-application-state",
    }[extent]

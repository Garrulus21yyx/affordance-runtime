"""Immutable contracts for the current runtime-owned ActionSpace."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    DestinationMode,
    InteractionCapabilityError,
    InteractionCapabilityIssueCode,
    VerificationContract,
    VerificationFamily,
    verification_contract_for_action,
)
from affordance_runtime.immutable import freeze_json, to_json_compatible

_PRIVATE_DESTINATION_MARKERS = (
    "selector",
    "coordinate",
    "bbox",
    "href",
    "http://",
    "https://",
)


class ActionRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IRREVERSIBLE = "irreversible"


class ActionSpaceIssueCode(StrEnum):
    ACTION_ROUTE_CONFLICT = "action_route_conflict"


@dataclass(frozen=True)
class ActionSpaceIssue:
    code: ActionSpaceIssueCode
    operation: str
    source_target_id: str
    destination_ids: tuple[str, ...] = ()
    conflicting_contract_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.operation.strip() or not self.source_target_id.strip():
            raise ValueError("action-space issue requires one public route selector")
        object.__setattr__(self, "destination_ids", canonical_destination_ids(self.destination_ids))
        fields = tuple(sorted(set(self.conflicting_contract_fields)))
        if not fields:
            raise ValueError("action-space route conflict requires conflicting contract fields")
        object.__setattr__(self, "conflicting_contract_fields", fields)


@dataclass(frozen=True)
class ActionOption:
    action_id: str
    observation_id: str
    semantic_action: str
    target_id: str
    effect_category: str
    parameter_schema: dict[str, Any]
    schema_digest: str
    eligible_binding_ids: tuple[str, ...]
    description: str
    semantic_effects: tuple[str, ...] = ()
    risk: ActionRisk = ActionRisk.LOW
    destination_required: bool = False
    eligible_destination_ids: tuple[str, ...] = ()
    observation_barrier: bool = True
    verification_contract_digest: str = ""
    verification_family: str = ""

    def __post_init__(self) -> None:
        if (
            not all(
                value.strip()
                for value in (
                    self.action_id,
                    self.observation_id,
                    self.semantic_action,
                    self.target_id,
                    self.effect_category,
                    self.schema_digest,
                )
            )
            or not self.eligible_binding_ids
        ):
            raise ValueError("action option requires current semantic identity")
        definition = INTERACTION_CAPABILITY_REGISTRY.require(self.semantic_action)
        INTERACTION_CAPABILITY_REGISTRY.validate_parameter_schema(
            self.semantic_action,
            self.parameter_schema,
        )
        if not self.verification_family or not self.verification_contract_digest:
            raise ValueError("action option requires a binding-selected verification contract")
        if VerificationFamily(self.verification_family) not in definition.verification_families:
            raise ValueError("option verification family is not supported by the action")
        object.__setattr__(self, "parameter_schema", freeze_json(self.parameter_schema))
        object.__setattr__(self, "eligible_binding_ids", tuple(self.eligible_binding_ids))
        object.__setattr__(self, "semantic_effects", tuple(self.semantic_effects))
        object.__setattr__(
            self,
            "eligible_destination_ids",
            canonical_destination_ids(self.eligible_destination_ids),
        )
        if self.destination_required and not self.eligible_destination_ids:
            raise ValueError("destination-required action must offer semantic destination IDs")
        destination_mode = (
            DestinationMode.REQUIRED
            if self.destination_required
            else DestinationMode.OPTIONAL
            if self.eligible_destination_ids
            else DestinationMode.FORBIDDEN
        )
        if destination_mode is not definition.destination_mode:
            raise InteractionCapabilityError(
                InteractionCapabilityIssueCode.DESTINATION_MODE_MISMATCH,
                self.semantic_action,
            )
        contract = self.verification_contract
        if self.verification_family != contract.family.value:
            raise ValueError("option verification family does not match sealed contract")
        if self.verification_contract_digest != contract.digest:
            raise ValueError("option verification contract does not match sealed contract")

    @property
    def verification_contract(self) -> VerificationContract:
        return verification_contract_for_action(
            self.semantic_action,
            self.schema_digest,
            self.semantic_effects,
            self.observation_barrier,
            family=VerificationFamily(self.verification_family) if self.verification_family else None,
        )


@dataclass(frozen=True)
class AdmittedActionSelection:
    action_id: str
    observation_id: str
    semantic_action: str
    target_id: str
    effect_category: str
    semantic_effects: tuple[str, ...]
    schema_digest: str
    eligible_binding_ids: tuple[str, ...]
    risk: ActionRisk
    observation_barrier: bool
    parameters: dict[str, Any] = field(default_factory=dict)
    destination_id: str = ""
    destination_required: bool = False
    eligible_destination_ids: tuple[str, ...] = ()
    verification_contract_digest: str = ""
    verification_family: str = ""
    expected_outcome: str = ""

    def __post_init__(self) -> None:
        required = (
            self.action_id,
            self.observation_id,
            self.semantic_action,
            self.target_id,
            self.effect_category,
            self.schema_digest,
        )
        if not all(value.strip() for value in required) or not self.eligible_binding_ids:
            raise ValueError("admitted selection requires exact option and binding-group identity")
        object.__setattr__(self, "semantic_effects", tuple(self.semantic_effects))
        object.__setattr__(self, "eligible_binding_ids", tuple(self.eligible_binding_ids))
        object.__setattr__(self, "parameters", freeze_json(self.parameters))
        if not isinstance(self.expected_outcome, str) or len(self.expected_outcome) > 240:
            raise ValueError("admitted selection expected outcome must be one bounded string")
        object.__setattr__(self, "expected_outcome", self.expected_outcome.strip())
        object.__setattr__(
            self,
            "eligible_destination_ids",
            canonical_destination_ids(self.eligible_destination_ids),
        )
        validate_selected_destination(
            self.destination_id,
            self.destination_required,
            self.eligible_destination_ids,
        )
        definition = INTERACTION_CAPABILITY_REGISTRY.require(self.semantic_action)
        if not self.verification_family or not self.verification_contract_digest:
            raise ValueError("admitted selection requires an option verification contract")
        if VerificationFamily(self.verification_family) not in definition.verification_families:
            raise ValueError("selection verification family is not supported by the action")
        contract = self.verification_contract
        if self.verification_family != contract.family.value:
            raise ValueError("selection verification family does not match sealed contract")
        if self.verification_contract_digest != contract.digest:
            raise ValueError("selection verification contract does not match sealed contract")

    @property
    def verification_contract(self) -> VerificationContract:
        return verification_contract_for_action(
            self.semantic_action,
            self.schema_digest,
            self.semantic_effects,
            self.observation_barrier,
            family=VerificationFamily(self.verification_family) if self.verification_family else None,
        )


@dataclass(frozen=True)
class ActionSpace:
    observation_id: str
    options: tuple[ActionOption, ...]
    issues: tuple[ActionSpaceIssue, ...] = ()
    action_space_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("action space requires observation identity")
        if any(option.observation_id != self.observation_id for option in self.options):
            raise ValueError("action-space option belongs to another observation")
        if len({option.action_id for option in self.options}) != len(self.options):
            raise ValueError("action ids must be unique within an action space")
        object.__setattr__(self, "options", tuple(self.options))
        object.__setattr__(self, "issues", tuple(self.issues))
        if any(not isinstance(issue, ActionSpaceIssue) for issue in self.issues):
            raise TypeError("action-space issues must be typed")
        semantic_membership = tuple(
            (
                option.action_id,
                option.semantic_action,
                option.target_id,
                option.effect_category,
                option.schema_digest,
                option.description,
                option.semantic_effects,
                option.risk,
                option.destination_required,
                option.eligible_destination_ids,
                option.observation_barrier,
                option.verification_family,
                option.verification_contract_digest,
                to_json_compatible(option.parameter_schema),
            )
            for option in self.options
        )
        encoded = json.dumps(
            (self.observation_id, semantic_membership, to_json_compatible(self.issues)),
            sort_keys=True,
            separators=(",", ":"),
        )
        object.__setattr__(
            self,
            "action_space_id",
            f"action-space:{hashlib.sha256(encoded.encode()).hexdigest()}",
        )

    def find(self, action_id: str) -> ActionOption | None:
        return next((option for option in self.options if option.action_id == action_id), None)


def canonical_destination_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    destinations = tuple(values)
    if any(not item.strip() for item in destinations):
        raise ValueError("destination IDs cannot be blank")
    if len(set(destinations)) != len(destinations):
        raise ValueError("destination IDs must be unique")
    if any(_destination_is_private(item) for item in destinations):
        raise ValueError("destination contains runtime-private route identity")
    return tuple(sorted(destinations))


def validate_selected_destination(
    destination_id: str,
    destination_required: bool,
    eligible_destination_ids: tuple[str, ...],
) -> None:
    if destination_id and _destination_is_private(destination_id):
        raise ValueError("destination contains runtime-private route identity")
    if destination_required and not destination_id:
        raise ValueError("semantic destination is required")
    if destination_id and destination_id not in eligible_destination_ids:
        raise ValueError("semantic destination was not offered by the current ActionSpace")


def _destination_is_private(destination_id: str) -> bool:
    lowered = destination_id.casefold()
    return any(marker in lowered for marker in _PRIVATE_DESTINATION_MARKERS)

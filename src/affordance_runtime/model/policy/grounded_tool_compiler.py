"""Compile current semantic actions into stable public tools and private bindings."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.actions.capabilities import INTERACTION_CAPABILITY_REGISTRY
from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent.context.contracts import AgentActionOptionView, AgentDestinationView
from affordance_runtime.agent.decisions import AgentDecision, SelectAction
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.tool_contracts import ToolSpec

_EXPECTED_OUTCOME_FIELD = "expected_outcome"
_RESERVED_NAMES = frozenset({"target", "source", "destination", _EXPECTED_OUTCOME_FIELD})


class SelectorMode(StrEnum):
    CURRENT_TARGET = "current_target"
    CURRENT_ENDPOINTS = "current_endpoints"


@dataclass(frozen=True)
class ConcreteActionCandidateRow:
    option: AgentActionOptionView
    destination: AgentDestinationView | None


@dataclass(frozen=True)
class CompiledSelectorField:
    public_name: str
    semantic_paths: tuple[str, ...]
    input_schema: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "semantic_paths", tuple(self.semantic_paths))
        object.__setattr__(self, "input_schema", freeze_json(self.input_schema))


@dataclass(frozen=True)
class PrivateResolutionEntry:
    selector_values: Mapping[str, object]
    action_id: str
    destination_id: str | None
    target_ref: str = ""
    parameter_schema: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "selector_values", freeze_json(self.selector_values))
        object.__setattr__(self, "parameter_schema", freeze_json(self.parameter_schema))


@dataclass(frozen=True)
class CompiledGroundedTool:
    canonical_operation: str
    public_spec: ToolSpec
    selector_mode: SelectorMode
    selector_fields: tuple[CompiledSelectorField, ...]
    private_resolutions: tuple[PrivateResolutionEntry, ...]

    def resolve(
        self,
        arguments: Mapping[str, object],
        context_id: str,
        tool_call_id: str,
    ) -> AgentDecision:
        selector_names = tuple(item.public_name for item in self.selector_fields)
        selector_values = {name: arguments[name] for name in selector_names}
        matches = tuple(
            item
            for item in self.private_resolutions
            if dict(item.selector_values) == selector_values
        )
        if len(matches) != 1:
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.INVALID_ARGUMENTS
            )
        match = matches[0]
        expected_outcome = _expected_outcome(arguments.get(_EXPECTED_OUTCOME_FIELD, ""))
        parameters = {
            name: value
            for name, value in arguments.items()
            if name not in selector_names and name != _EXPECTED_OUTCOME_FIELD
        }
        try:
            validate_value(parameters, match.parameter_schema, path="command")
        except ValueError as exc:
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.INVALID_ARGUMENTS
            ) from exc
        return SelectAction(
            context_id,
            match.action_id,
            parameters,
            match.destination_id or "",
            tool_call_id,
            expected_outcome,
        )


class GroundedToolCompiler:
    """Publish one registry-owned tool per operation for the current action page."""

    def compile(
        self,
        options: tuple[AgentActionOptionView, ...],
        *,
        context_id: str,
    ) -> tuple[CompiledGroundedTool, ...]:
        grouped: dict[str, list[ConcreteActionCandidateRow]] = defaultdict(list)
        for option in options:
            INTERACTION_CAPABILITY_REGISTRY.require(option.operation)
            for row in self.expand_rows(option):
                grouped[option.operation].append(row)
        return tuple(
            self._compile_operation(
                operation,
                tuple(sorted(grouped[operation], key=_row_order)),
                context_id,
            )
            for operation in sorted(grouped)
        )

    @staticmethod
    def expand_rows(option: AgentActionOptionView) -> tuple[ConcreteActionCandidateRow, ...]:
        if option.destination_mode == "forbidden":
            return (ConcreteActionCandidateRow(option, None),)
        if option.destination_mode == "optional":
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.UNSUPPORTED_DESTINATION_MODE
            )
        if option.destination_mode != "required":
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        if option.destinations.truncated or not option.destinations.items:
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.DESTINATION_UNAVAILABLE
            )
        return tuple(
            ConcreteActionCandidateRow(option, destination)
            for destination in option.destinations.items
        )

    def _compile_operation(
        self,
        operation: str,
        rows: tuple[ConcreteActionCandidateRow, ...],
        context_id: str,
    ) -> CompiledGroundedTool:
        if not rows or {row.option.destination_mode for row in rows} not in (
            {"forbidden"},
            {"required"},
        ):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        self._validate_current_refs(rows, context_id)
        fields, selector_values, mode = _current_reference_selectors(rows)
        business_schema = _merge_business_schemas(
            tuple(row.option.parameter_schema for row in rows)
        )
        business_properties, business_required = _business_schema(business_schema)
        if set(business_properties).intersection(_RESERVED_NAMES):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        selector_properties = {
            field.public_name: to_json_compatible(field.input_schema) for field in fields
        }
        schema = {
            "type": "object",
            "properties": {
                **selector_properties,
                **business_properties,
                _EXPECTED_OUTCOME_FIELD: {
                    "type": "string",
                    "description": "optional local outcome intent for this action; advisory, not task completion",
                    "maxLength": 240,
                },
            },
            "required": [*(field.public_name for field in fields), *business_required],
            "additionalProperties": False,
        }
        resolutions = tuple(
            PrivateResolutionEntry(
                selector,
                row.option.action_id,
                row.destination.destination_id if row.destination else None,
                row.option.target_ref,
                row.option.parameter_schema,
            )
            for row, selector in zip(rows, selector_values, strict=True)
        )
        if len({_token(item.selector_values) for item in resolutions}) != len(resolutions):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
        return CompiledGroundedTool(
            operation,
            ToolSpec(operation, _description(operation, rows, fields), schema),
            mode,
            fields,
            resolutions,
        )

    @staticmethod
    def _validate_current_refs(
        rows: tuple[ConcreteActionCandidateRow, ...],
        context_id: str,
    ) -> None:
        for row in rows:
            if not row.option.target_ref or row.option.grounding_context_id != context_id:
                raise GroundedToolResolutionError(
                    GroundedToolResolutionCode.GROUNDING_FALLBACK_UNAVAILABLE
                )
            if row.destination is not None and (
                not row.destination.grounding_ref
                or row.destination.grounding_context_id != context_id
            ):
                raise GroundedToolResolutionError(
                    GroundedToolResolutionCode.GROUNDING_FALLBACK_UNAVAILABLE
                )


def _current_reference_selectors(
    rows: tuple[ConcreteActionCandidateRow, ...],
) -> tuple[
    tuple[CompiledSelectorField, ...],
    tuple[Mapping[str, object], ...],
    SelectorMode,
]:
    if rows[0].destination is None:
        targets = tuple(dict.fromkeys(row.option.target_ref for row in rows))
        field = CompiledSelectorField(
            "target",
            ("target.ref",),
            {
                "type": "string",
                "description": "currently offered target reference",
                "enum": list(targets),
            },
        )
        return (
            (field,),
            tuple({"target": row.option.target_ref} for row in rows),
            SelectorMode.CURRENT_TARGET,
        )
    sources = tuple(dict.fromkeys(row.option.target_ref for row in rows))
    destinations = tuple(dict.fromkeys(
        row.destination.grounding_ref
        for row in rows
        if row.destination is not None
    ))
    fields = (
        CompiledSelectorField(
            "source",
            ("source.ref",),
            {
                "type": "string",
                "description": "currently offered source reference",
                "enum": list(sources),
            },
        ),
        CompiledSelectorField(
            "destination",
            ("destination.ref",),
            {
                "type": "string",
                "description": "currently offered destination reference",
                "enum": list(destinations),
            },
        ),
    )
    return (
        fields,
        tuple(
            {
                "source": row.option.target_ref,
                "destination": row.destination.grounding_ref,
            }
            for row in rows
            if row.destination is not None
        ),
        SelectorMode.CURRENT_ENDPOINTS,
    )


def _expected_outcome(value: object) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or len(value) > 240:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
    return value.strip()


def _merge_business_schemas(
    schemas: tuple[Mapping[str, object], ...],
) -> Mapping[str, object]:
    if not schemas:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    parsed = tuple(_business_schema(schema) for schema in schemas)
    property_names = tuple(parsed[0][0])
    required = tuple(parsed[0][1])
    if any(tuple(properties) != property_names or tuple(required_names) != required for properties, required_names in parsed[1:]):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    merged = {
        name: _merge_property_schemas(tuple(properties[name] for properties, _ in parsed))
        for name in property_names
    }
    return {
        "type": "object",
        "properties": merged,
        "required": list(required),
        "additionalProperties": False,
    }


def _merge_property_schemas(schemas: tuple[object, ...]) -> dict[str, object]:
    if not all(isinstance(schema, Mapping) for schema in schemas):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    mappings = tuple(schema for schema in schemas if isinstance(schema, Mapping))
    types = {schema.get("type") for schema in mappings}
    if len(types) != 1:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    result: dict[str, object] = {"type": next(iter(types))}
    descriptions = {schema.get("description") for schema in mappings}
    if len(descriptions) == 1 and None not in descriptions:
        result["description"] = next(iter(descriptions))
    if all("enum" in schema for schema in mappings):
        result["enum"] = list(
            dict.fromkeys(
                value
                for schema in mappings
                for value in schema.get("enum", ())
            )
        )
    minimums = tuple(schema["minimum"] for schema in mappings if "minimum" in schema)
    maximums = tuple(schema["maximum"] for schema in mappings if "maximum" in schema)
    if minimums:
        result["minimum"] = min(minimums)
    if maximums:
        result["maximum"] = max(maximums)
    return result


def _business_schema(schema: Mapping[str, object]) -> tuple[dict[str, object], list[str]]:
    if schema.get("type") != "object" or schema.get("additionalProperties", False) is not False:
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    properties = schema.get("properties", {})
    required = schema.get("required", ())
    if (
        not isinstance(properties, Mapping)
        or not isinstance(required, Sequence)
        or isinstance(required, str | bytes)
        or any(not isinstance(item, str) for item in required)
        or not set(required).issubset(properties)
    ):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    return (
        {str(name): to_json_compatible(value) for name, value in properties.items()},
        list(required),
    )


def _description(
    operation: str,
    rows: tuple[ConcreteActionCandidateRow, ...],
    fields: tuple[CompiledSelectorField, ...],
) -> str:
    endpoints = " and ".join(field.public_name for field in fields)
    effects = ", ".join(rows[0].option.semantic_effects) or rows[0].option.effect_category
    return (
        f"{operation} using current observation {endpoints}. "
        "Choose a reference whose current observation affordances include this operation; Runtime revalidates "
        f"existence, currentness, and legality. Effect: {effects}; risk: {rows[0].option.risk}."
    )[:500]


def _row_order(row: ConcreteActionCandidateRow) -> tuple[str, str]:
    return (
        row.option.target_ref,
        row.destination.grounding_ref if row.destination else "",
    )


def _token(value: object) -> str:
    return json.dumps(
        to_json_compatible(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

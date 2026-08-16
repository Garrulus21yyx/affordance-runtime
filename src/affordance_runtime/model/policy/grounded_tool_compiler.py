"""Compile current semantic actions into stable public tools and private bindings."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.actions.capabilities import INTERACTION_CAPABILITY_REGISTRY
from affordance_runtime.agent.context.contracts import AgentActionOptionView, AgentDestinationView
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.tool_contracts import ToolSpec

_RESERVED_NAMES = frozenset({"target", "source", "destination"})


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
            "properties": {**selector_properties, **business_properties},
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
                "description": "current target reference from observation",
                "enum": list(targets),
            },
        )
        return (
            (field,),
            tuple({"target": row.option.target_ref} for row in rows),
            SelectorMode.CURRENT_TARGET,
        )
    sources = tuple(dict.fromkeys(row.option.target_ref for row in rows))
    destinations = tuple(
        dict.fromkeys(
            row.destination.grounding_ref
            for row in rows
            if row.destination is not None
        )
    )
    fields = (
        CompiledSelectorField(
            "source",
            ("source.ref",),
            {
                "type": "string",
                "description": "current source reference from observation",
                "enum": list(sources),
            },
        ),
        CompiledSelectorField(
            "destination",
            ("destination.ref",),
            {
                "type": "string",
                "description": "current destination reference from observation",
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
        f"Choose only listed references. Effect: {effects}; risk: {rows[0].option.risk}."
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

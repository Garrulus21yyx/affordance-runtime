"""Compile current semantic actions into stable public tools and private bindings."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    ParameterContractKind,
)
from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent.context.contracts import AgentActionOptionView, AgentDestinationView
from affordance_runtime.agent.decisions import AgentDecision, SelectAction
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.tool_contracts import ToolSpec
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind

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
        if not matches:
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.GROUNDING_GAP,
                "executable reference is unavailable for this operation in the current World",
            )
        if len(matches) != 1:
            raise GroundedToolResolutionError(
                GroundedToolResolutionCode.CATALOG_INVALID
            )
        match = matches[0]
        parameters = {
            name: value
            for name, value in arguments.items()
            if name not in selector_names
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
            "",
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
        if not option.destinations.items:
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
        self._validate_private_parameter_contracts(operation, rows)
        fields, selector_values, mode = _current_reference_selectors(rows)
        schema = _public_operation_schema(operation, fields)
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

    @staticmethod
    def _validate_private_parameter_contracts(
        operation: str,
        rows: tuple[ConcreteActionCandidateRow, ...],
    ) -> None:
        for row in rows:
            properties, _required = _business_schema(row.option.parameter_schema)
            if set(properties).intersection(_RESERVED_NAMES):
                raise GroundedToolResolutionError(
                    GroundedToolResolutionCode.CATALOG_INVALID
                )
            try:
                INTERACTION_CAPABILITY_REGISTRY.validate_parameter_schema(
                    operation,
                    row.option.parameter_schema,
                )
            except ValueError as exc:
                raise GroundedToolResolutionError(
                    GroundedToolResolutionCode.CATALOG_INVALID
                ) from exc


def _current_reference_selectors(
    rows: tuple[ConcreteActionCandidateRow, ...],
) -> tuple[
    tuple[CompiledSelectorField, ...],
    tuple[Mapping[str, object], ...],
    SelectorMode,
]:
    if rows[0].destination is None:
        field = CompiledSelectorField(
            "target",
            ("target.ref",),
            {
                "type": "string",
                "description": "current executable E-ref",
                "pattern": PublicRefCodec.pattern(PublicRefKind.EXECUTABLE),
            },
        )
        return (
            (field,),
            tuple({"target": row.option.target_ref} for row in rows),
            SelectorMode.CURRENT_TARGET,
        )
    fields = (
        CompiledSelectorField(
            "source",
            ("source.ref",),
            {
                "type": "string",
                "description": "current executable source E-ref",
                "pattern": PublicRefCodec.pattern(PublicRefKind.EXECUTABLE),
            },
        ),
        CompiledSelectorField(
            "destination",
            ("destination.ref",),
            {
                "type": "string",
                "description": "current executable destination E-ref",
                "pattern": PublicRefCodec.pattern(PublicRefKind.EXECUTABLE),
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


def _public_operation_schema(
    operation: str,
    fields: tuple[CompiledSelectorField, ...],
) -> Mapping[str, object]:
    branches = tuple(
        _public_operation_branch(schema, fields)
        for schema in _public_business_schemas(operation)
    )
    return branches[0] if len(branches) == 1 else {"anyOf": list(branches)}


def _public_operation_branch(
    parameter_schema: Mapping[str, object],
    fields: tuple[CompiledSelectorField, ...],
) -> dict[str, object]:
    properties, required = _business_schema(parameter_schema)
    if set(properties).intersection(_RESERVED_NAMES):
        raise GroundedToolResolutionError(GroundedToolResolutionCode.CATALOG_INVALID)
    selector_properties = {
        field.public_name: to_json_compatible(field.input_schema)
        for field in fields
    }
    return {
        "type": "object",
        "properties": {**selector_properties, **properties},
        "required": [*(field.public_name for field in fields), *required],
        "additionalProperties": False,
    }


def _public_business_schemas(operation: str) -> tuple[Mapping[str, object], ...]:
    """Return the stable public parameter family; exact domains stay private."""

    definition = INTERACTION_CAPABILITY_REGISTRY.require(operation)
    if definition.parameter_contract is ParameterContractKind.NATIVE_VALUE:
        return tuple(
            INTERACTION_CAPABILITY_REGISTRY.parameter_schema(
                operation,
                current_value_schema={"type": schema_type},
            )
            for schema_type in ("boolean", "integer", "number", "string")
        )
    if definition.parameter_contract is ParameterContractKind.TAB_INDEX:
        return (
            INTERACTION_CAPABILITY_REGISTRY.parameter_schema(
                operation,
                current_value_schema={"type": "integer", "minimum": 0},
            ),
        )
    return (INTERACTION_CAPABILITY_REGISTRY.parameter_schema(operation),)


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
    return (
        f"Use {operation} on current executable {endpoints} from the current World "
        "or a same-World find_controls result."
    )


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

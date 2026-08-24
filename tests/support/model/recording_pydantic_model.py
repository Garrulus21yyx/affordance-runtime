"""Test-only recorder for the real PydanticAI ``FunctionModel`` boundary.

The recorder snapshots only the typed values PydanticAI supplies to a
``FunctionModel`` callback.  It does not build, normalize, or admit requests.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import TypeAlias

from pydantic_ai import BinaryContent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from affordance_runtime.immutable import to_json_compatible


@dataclass(frozen=True)
class FrozenMapping(Mapping[str, object]):
    """Insertion-ordered, immutable mapping used by boundary snapshots."""

    items_in_order: tuple[tuple[str, object], ...]

    def __getitem__(self, key: str) -> object:
        for candidate, value in self.items_in_order:
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _value in self.items_in_order)

    def __len__(self) -> int:
        return len(self.items_in_order)


@dataclass(frozen=True)
class FrozenBoundaryObject:
    """All public dataclass fields of one PydanticAI boundary object."""

    type_name: str
    fields_in_order: tuple[tuple[str, object], ...]

    def field(self, name: str) -> object:
        for candidate, value in self.fields_in_order:
            if candidate == name:
                return value
        raise KeyError(name)


def freeze_boundary_value(value: object) -> object:
    """Freeze a boundary value without filtering, sorting, or JSON coercion."""

    if is_dataclass(value) and not isinstance(value, type):
        return FrozenBoundaryObject(
            f"{type(value).__module__}.{type(value).__qualname__}",
            tuple((item.name, freeze_boundary_value(getattr(value, item.name))) for item in fields(value)),
        )
    if isinstance(value, Mapping):
        return FrozenMapping(tuple((str(key), freeze_boundary_value(item)) for key, item in value.items()))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(freeze_boundary_value(item) for item in value)
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, Enum):
        return value
    return copy.deepcopy(value)


@dataclass(frozen=True)
class RecordedToolDefinition:
    name: str
    description: str | None
    parameters_json_schema: FrozenMapping
    strict: bool | None
    boundary_snapshot: FrozenBoundaryObject

    @classmethod
    def from_boundary(cls, tool: object) -> RecordedToolDefinition:
        schema = freeze_boundary_value(getattr(tool, "parameters_json_schema"))
        snapshot = freeze_boundary_value(tool)
        assert isinstance(schema, FrozenMapping)
        assert isinstance(snapshot, FrozenBoundaryObject)
        return cls(
            name=str(getattr(tool, "name")),
            description=getattr(tool, "description"),
            parameters_json_schema=schema,
            strict=getattr(tool, "strict"),
            boundary_snapshot=snapshot,
        )


@dataclass(frozen=True)
class RecordedProviderInvocation:
    ordinal: int
    scripted_phase: str
    messages: tuple[ModelMessage, ...]
    message_snapshot: tuple[FrozenBoundaryObject, ...]
    instructions: str | None
    instruction_parts: tuple[object, ...] | None
    function_tools: tuple[RecordedToolDefinition, ...]
    output_tools: tuple[RecordedToolDefinition, ...]
    allow_text_output: bool
    model_settings: FrozenMapping | None
    model_request_parameters: FrozenBoundaryObject


DecisionScript: TypeAlias = list[tuple[str, dict[str, object]] | str | Exception]


@dataclass
class RecordingPydanticModel:
    """Scripted PydanticAI model whose only observations are callback arguments."""

    decisions: DecisionScript
    scripted_phases: list[str] = field(default_factory=list)
    records: list[RecordedProviderInvocation] = field(default_factory=list, init=False)
    last_gui_call: tuple[str, dict[str, object]] | None = field(default=None, init=False)

    @property
    def calls(self) -> int:
        return len(self.records)

    @property
    def messages(self) -> list[object]:
        return [record.messages for record in self.records]

    @property
    def offered_tools(self) -> list[tuple[str, ...]]:
        return [tuple(tool.name for tool in record.function_tools) for record in self.records]

    @property
    def model_settings(self) -> list[object]:
        return [
            ({key: value for key, value in record.model_settings.items()} if record.model_settings is not None else None)
            for record in self.records
        ]

    def build(self) -> FunctionModel:
        async def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            ordinal = len(self.records) + 1
            phase = self.scripted_phases.pop(0) if self.scripted_phases else "unspecified"
            copied_messages = tuple(copy.deepcopy(messages))
            message_snapshot = tuple(freeze_boundary_value(message) for message in messages)
            settings = freeze_boundary_value(info.model_settings)
            request_parameters = freeze_boundary_value(info.model_request_parameters)
            instruction_parts = info.model_request_parameters.instruction_parts
            assert all(isinstance(item, FrozenBoundaryObject) for item in message_snapshot)
            assert settings is None or isinstance(settings, FrozenMapping)
            assert isinstance(request_parameters, FrozenBoundaryObject)
            self.records.append(
                RecordedProviderInvocation(
                    ordinal=ordinal,
                    scripted_phase=phase,
                    messages=copied_messages,
                    message_snapshot=message_snapshot,  # type: ignore[arg-type]
                    instructions=info.instructions,
                    instruction_parts=(
                        tuple(freeze_boundary_value(item) for item in instruction_parts)
                        if instruction_parts is not None
                        else None
                    ),
                    function_tools=tuple(RecordedToolDefinition.from_boundary(tool) for tool in info.function_tools),
                    output_tools=tuple(RecordedToolDefinition.from_boundary(tool) for tool in info.output_tools),
                    allow_text_output=info.allow_text_output,
                    model_settings=settings,
                    model_request_parameters=request_parameters,
                )
            )

            scripted = self.decisions.pop(0)
            if isinstance(scripted, Exception):
                raise scripted
            if isinstance(scripted, str) and scripted in {"final_response", "zero_calls"}:
                content = "Shared state is enabled." if scripted == "final_response" else "no tool call"
                return ModelResponse(
                    parts=[TextPart(content)],
                    provider_response_id=f"recording-response:{ordinal}",
                )
            if scripted == "malformed_tool_call":
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            info.function_tools[0].name,
                            "{not-json",
                            tool_call_id=f"recording-call:{ordinal}",
                        )
                    ],
                    provider_response_id=f"recording-response:{ordinal}",
                )
            if isinstance(scripted, str) and scripted in {
                "first_gui_action",
                "first_gui_action_invalid_extra",
                "multiple_gui_actions",
                "multiple_distinct_gui_actions",
            }:
                name, arguments = _select_current_tool_call(messages, info)
                self.last_gui_call = (name, dict(arguments))
                if scripted == "first_gui_action_invalid_extra":
                    arguments["unexpected"] = "remove-me"
            elif isinstance(scripted, str) and scripted in {
                "first_schema_action",
                "last_schema_action",
            }:
                name, arguments = _select_schema_action(
                    info,
                    last=scripted == "last_schema_action",
                )
                self.last_gui_call = (name, dict(arguments))
            elif isinstance(scripted, str) and scripted.startswith("schema_action_label:"):
                name, arguments = _select_schema_action_for_label(
                    messages,
                    info,
                    scripted.removeprefix("schema_action_label:"),
                )
                self.last_gui_call = (name, dict(arguments))
            elif scripted == "continue_until_action":
                continuation = next(
                    (
                        tool
                        for tool in info.function_tools
                        if tool.name == "action_results_next_page"
                    ),
                    None,
                )
                if continuation is not None:
                    name = continuation.name
                    sampled = _schema_example(continuation.parameters_json_schema)
                    assert isinstance(sampled, dict)
                    arguments = sampled
                    self.decisions.insert(0, scripted)
                else:
                    name, arguments = _select_schema_action(info)
                    self.last_gui_call = (name, dict(arguments))
            elif scripted == "repeat_last_gui_call":
                assert self.last_gui_call is not None
                name, remembered_arguments = self.last_gui_call
                arguments = dict(remembered_arguments)
            else:
                assert isinstance(scripted, tuple)
                name, arguments = scripted
            parts = [ToolCallPart(name, arguments, tool_call_id=f"recording-call:{ordinal}")]
            if scripted == "multiple_gui_actions":
                parts.append(
                    ToolCallPart(name, arguments, tool_call_id=f"recording-call:{ordinal}:second")
                )
            elif scripted == "multiple_distinct_gui_actions":
                alternate = next(item for item in info.function_tools if item.name != name)
                parts.append(
                    ToolCallPart(
                        alternate.name,
                        _schema_example(alternate.parameters_json_schema),
                        tool_call_id=f"recording-call:{ordinal}:discarded",
                    )
                )
            return ModelResponse(
                parts=parts,
                provider_response_id=f"recording-response:{ordinal}",
            )

        return FunctionModel(respond, model_name="recording-scripted")


def normalize_recorded_provider_input(record: RecordedProviderInvocation) -> Mapping[str, object]:
    """Normalize only fields exposed at the FunctionModel boundary."""

    return {
        "instructions": (record.instructions,) if record.instructions else (),
        "messages": tuple(_normalize_message(item) for item in record.messages),
        "function_tools": tuple(
            {
                "name": item.name,
                "description": item.description,
                "parameters_json_schema": to_json_compatible(_thaw(item.parameters_json_schema)),
                "strict": item.strict,
            }
            for item in record.function_tools
        ),
        "model_settings": _thaw(record.model_settings) if record.model_settings is not None else None,
        "output_mode": record.model_request_parameters.field("output_mode"),
        "allow_text_output": record.allow_text_output,
        "allow_image_output": record.model_request_parameters.field("allow_image_output"),
        "output_tools": tuple(
            {
                "name": item.name,
                "description": item.description,
                "parameters_json_schema": to_json_compatible(_thaw(item.parameters_json_schema)),
                "strict": item.strict,
            }
            for item in record.output_tools
        ),
    }


def _normalize_message(message: ModelMessage) -> Mapping[str, object]:
    if isinstance(message, ModelResponse):
        return {
            "kind": "response",
            "parts": tuple(
                {
                    "part_kind": "tool-call",
                    "tool_name": part.tool_name,
                    "arguments": _thaw(part.args_as_dict()),
                    "tool_call_id": part.tool_call_id,
                }
                for part in message.parts
                if isinstance(part, ToolCallPart)
            ),
        }
    if not isinstance(message, ModelRequest):
        raise TypeError("recorder expected a PydanticAI model message")
    parts = []
    for part in message.parts:
        if isinstance(part, ToolReturnPart):
            parts.append(
                {
                    "part_kind": "tool-return",
                    "tool_name": part.tool_name,
                    "tool_call_id": part.tool_call_id,
                    "content": _thaw(part.content),
                }
            )
            continue
        if not isinstance(part, UserPromptPart):
            raise TypeError("recorder expected user prompt or tool return request parts")
        content = part.content
        items = (content,) if isinstance(content, str) else tuple(content)
        normalized = []
        for item in items:
            if isinstance(item, str):
                normalized.append({"part_kind": "text", "content": item})
            elif isinstance(item, BinaryContent):
                normalized.append(
                    {
                        "part_kind": "binary",
                        "media_type": item.media_type,
                        "data": item.data,
                        "digest": hashlib.sha256(item.data).hexdigest(),
                    }
                )
            else:
                raise TypeError(f"unsupported recorded user content: {type(item).__name__}")
        parts.append({"part_kind": "user-prompt", "content": tuple(normalized)})
    return {"kind": "request", "parts": tuple(parts)}


def _thaw(value: object) -> object:
    if isinstance(value, FrozenMapping):
        return {key: _thaw(item) for key, item in value.items_in_order}
    if isinstance(value, FrozenBoundaryObject):
        return {key: _thaw(item) for key, item in value.fields_in_order}
    if isinstance(value, tuple):
        return tuple(_thaw(item) for item in value)
    return value


def _select_current_tool_call(
    messages: list[ModelMessage],
    info: AgentInfo,
) -> tuple[str, dict[str, object]]:
    """Select a target-bearing route solely from the actual current callback input."""

    public_text = _latest_public_text(messages)
    public_payload = json.loads(public_text)
    observation = str(public_payload["observation"])
    for tool in info.function_tools:
        properties = tool.parameters_json_schema.get("properties", {})
        if not isinstance(properties, Mapping) or "target" not in properties:
            continue
        match = re.search(
            rf"\[(E[1-9][0-9]{{0,2}})\][^\n]*verbs=[^\n]*\b{re.escape(tool.name)}\b",
            observation,
        )
        if match is not None:
            return tool.name, {"target": match.group(1)}
    raise AssertionError("actual PydanticAI request offered no current target-bearing route")


def _select_schema_action(
    info: AgentInfo,
    *,
    last: bool = False,
) -> tuple[str, dict[str, object]]:
    """Choose one action solely from the actual provider-visible schema."""

    tools = reversed(info.function_tools) if last else info.function_tools
    for tool in tools:
        schema = tool.parameters_json_schema
        if not _schema_has_action_operand(schema):
            continue
        value = _schema_example(schema, last=last)
        if isinstance(value, dict):
            return tool.name, value
    raise AssertionError("actual PydanticAI request offered no schema-described action route")


def _schema_has_action_operand(schema: Mapping[str, object]) -> bool:
    properties = schema.get("properties", {})
    if isinstance(properties, Mapping) and ({"target", "source"} & set(properties)):
        return True
    return any(
        isinstance(branch, Mapping) and _schema_has_action_operand(branch)
        for keyword in ("oneOf", "anyOf")
        for branch in schema.get(keyword, ())
        if isinstance(schema.get(keyword), Sequence)
    )


def _select_schema_action_for_label(
    messages: list[ModelMessage],
    info: AgentInfo,
    label: str,
) -> tuple[str, dict[str, object]]:
    """Resolve a public label to a ref in actual text, then use only an accepting schema row."""

    public_text = _latest_public_text(messages)
    matching_line = next((line for line in public_text.splitlines() if label in line), "")
    match = re.search(r"\[(E[1-9][0-9]*)\]", matching_line)
    if match is None:
        raise AssertionError("actual provider text omitted the requested public label")
    ref = match.group(1)
    for tool in info.function_tools:
        arguments = _schema_example_for_operand_ref(tool.parameters_json_schema, ref)
        if arguments is not None:
            return tool.name, arguments
    raise AssertionError("actual provider schema omitted the requested public route")


def _schema_example_for_operand_ref(
    schema: Mapping[str, object],
    ref: str,
) -> dict[str, object] | None:
    for keyword in ("oneOf", "anyOf"):
        branches = schema.get(keyword)
        if isinstance(branches, Sequence) and not isinstance(branches, (str, bytes, bytearray)):
            for branch in branches:
                if isinstance(branch, Mapping):
                    result = _schema_example_for_operand_ref(branch, ref)
                    if result is not None:
                        return result
    if schema.get("type") != "object":
        return None
    properties = schema.get("properties", {})
    required = schema.get("required", ())
    if not isinstance(properties, Mapping) or not isinstance(required, Sequence):
        return None
    operand_name = next(
        (
            name
            for name in ("target", "source")
            if isinstance(properties.get(name), Mapping)
            and (
                properties[name].get("const") == ref
                or ref in properties[name].get("enum", ())
            )
        ),
        None,
    )
    if operand_name is None:
        return None
    result = {
        str(name): _schema_example(properties[str(name)])
        for name in required
        if isinstance(properties.get(str(name)), Mapping)
    }
    result[operand_name] = ref
    return result


def _schema_example(schema: Mapping[str, object], *, last: bool = False) -> object:
    for keyword in ("oneOf", "anyOf"):
        branches = schema.get(keyword)
        if isinstance(branches, Sequence) and not isinstance(branches, (str, bytes, bytearray)):
            choices = tuple(item for item in branches if isinstance(item, Mapping))
            branch = choices[-1 if last else 0] if choices else None
            if branch is not None:
                return _schema_example(branch, last=last)
    if "const" in schema:
        return copy.deepcopy(schema["const"])
    enum = schema.get("enum")
    if isinstance(enum, Sequence) and not isinstance(enum, (str, bytes, bytearray)) and enum:
        return copy.deepcopy(enum[-1 if last else 0])
    kind = schema.get("type")
    if kind == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", ())
        assert isinstance(properties, Mapping)
        assert isinstance(required, Sequence)
        return {
            str(name): _schema_example(properties[str(name)], last=last)
            for name in required
            if isinstance(properties.get(str(name)), Mapping)
        }
    if kind == "array":
        items = schema.get("items", {})
        count = int(schema.get("minItems", 0))
        return (
            [_schema_example(items, last=last) for _ in range(count)]
            if isinstance(items, Mapping)
            else []
        )
    if kind == "integer":
        return int(schema.get("minimum", 0))
    if kind == "number":
        return float(schema.get("minimum", 0.0))
    if kind == "boolean":
        return False
    if kind == "string":
        minimum = int(schema.get("minLength", 0))
        return "x" * max(1, minimum)
    raise AssertionError(f"cannot sample provider-visible schema kind: {kind!r}")


def _latest_public_text(messages: list[ModelMessage]) -> str:
    latest = messages[-1]
    for part in latest.parts:
        content = getattr(part, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
            for item in content:
                if isinstance(item, str):
                    return item
    raise AssertionError("actual PydanticAI request contained no public text part")


__all__ = [
    "DecisionScript",
    "FrozenBoundaryObject",
    "FrozenMapping",
    "RecordedProviderInvocation",
    "RecordedToolDefinition",
    "RecordingPydanticModel",
    "freeze_boundary_value",
    "normalize_recorded_provider_input",
]

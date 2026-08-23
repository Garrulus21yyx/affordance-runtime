"""Test-only recorder for the real PydanticAI ``FunctionModel`` boundary.

The recorder snapshots only the typed values PydanticAI supplies to a
``FunctionModel`` callback.  It does not build, normalize, or admit requests.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import TypeAlias

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


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
            }:
                name, arguments = _select_current_tool_call(messages, info)
                self.last_gui_call = (name, dict(arguments))
                if scripted == "first_gui_action_invalid_extra":
                    arguments["unexpected"] = "remove-me"
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
            return ModelResponse(
                parts=parts,
                provider_response_id=f"recording-response:{ordinal}",
            )

        return FunctionModel(respond, model_name="recording-scripted")


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
]

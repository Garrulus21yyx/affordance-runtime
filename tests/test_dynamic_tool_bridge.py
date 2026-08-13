from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field, replace

from test_model_port_decision_bridge import _context, _zero_retry_config

from affordance_runtime.agent import SelectAction
from affordance_runtime.model_boundary import ModelFailure, ModelFailureKind
from affordance_runtime.model_policy.policy import _build_request
from affordance_runtime.model_policy.tool_contracts import ToolCall, ToolResolutionCode
from affordance_runtime.model_policy.tool_port_bridge import (
    CompactToolCallPayload,
    DynamicToolDecisionAdapter,
)
from affordance_runtime.model_port import (
    ModelCallRecord,
    StructuredOutputError,
    StructuredOutputViolation,
)


def _required_value_request(context):
    request = _build_request(context)
    raw = json.loads(request.serialized_context)
    raw["actions"]["options"][0]["parameter_schema"] = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    return replace(
        request,
        serialized_context=json.dumps(raw, separators=(",", ":"), ensure_ascii=False),
    )


@dataclass
class _CompactPort:
    payload: object | None = None
    provider: str = "zhipu"
    model: str = "glm-4.1v-thinking-flashx"
    endpoint_class: str = "fixture"
    supports_multimodal: bool = True
    last_call: ModelCallRecord | None = None
    calls: int = 0
    messages: list = field(default_factory=list)

    async def generate_structured(self, messages, output_schema, config):
        self.calls += 1
        self.messages = list(messages)
        assert output_schema is CompactToolCallPayload
        content = messages[1].content
        assert isinstance(content, str)
        request = json.loads(content)
        tool = next(item for item in request["tools"] if item["name"].startswith("act_"))
        self.last_call = ModelCallRecord(
            provider=self.provider,
            model=self.model,
            endpoint_class=self.endpoint_class,
            prompt_version=config.prompt_version,
            schema_name=output_schema.__name__,
            schema_version="dynamic_tools.v1",
            latency_ms=3,
            response_id=f"response:{self.calls}",
        )
        return output_schema.model_validate(self.payload or {"tool": tool["name"], "args": {}})


def test_compact_tool_bridge_hides_runtime_ids_and_returns_typed_decision() -> None:
    async def scenario() -> None:
        context = await _context()
        port = _CompactPort()
        adapter = DynamicToolDecisionAdapter(port, _zero_retry_config())

        response = await adapter.generate(_build_request(context))

        assert not isinstance(response, ModelFailure)
        content = port.messages[1].content
        assert isinstance(content, str)
        assert context.context_id not in content
        assert '"action_id"' not in content
        decision = response.decision
        assert isinstance(decision, SelectAction)
        assert decision.context_id == context.context_id
        assert decision.action_id.startswith("action:")
        assert adapter.last_resolution_code is ToolResolutionCode.ACCEPTED
        assert adapter.last_catalog_count >= 1
        assert adapter.last_catalog_bytes > 0

    asyncio.run(scenario())


def test_unknown_tool_is_typed_and_zero_package() -> None:
    async def scenario() -> None:
        adapter = DynamicToolDecisionAdapter(
            _CompactPort(payload={"tool": "not_offered", "args": {}}),
            _zero_retry_config(),
        )

        outcome = await adapter.generate(_build_request(await _context()))

        assert isinstance(outcome, ModelFailure)
        assert outcome.kind is ModelFailureKind.SCHEMA_ERROR
        assert adapter.last_resolution_code is ToolResolutionCode.UNKNOWN_TOOL

    asyncio.run(scenario())


def test_compact_transport_repairs_format_once_without_changing_gui_turn() -> None:
    class RepairPort(_CompactPort):
        repair_messages: tuple = ()

        async def generate_structured(self, messages, output_schema, config):
            if self.calls == 0:
                self.calls += 1
                raise StructuredOutputError(
                    "malformed compact proposal",
                    violations=(StructuredOutputViolation("args.value", "missing"),),
                )
            self.repair_messages = tuple(messages)
            return await super().generate_structured(messages, output_schema, config)

    async def scenario() -> None:
        port = RepairPort()
        adapter = DynamicToolDecisionAdapter(port, _zero_retry_config())

        outcome = await adapter.generate(_build_request(await _context()))

        assert not isinstance(outcome, ModelFailure)
        assert port.calls == 2
        assert adapter.last_schema_repair_count == 1
        repair_system = port.repair_messages[0].content
        assert isinstance(repair_system, str)
        assert '"field_path":"args.value"' in repair_system
        assert '"code":"missing"' in repair_system
        assert "malformed compact proposal" not in repair_system

    asyncio.run(scenario())


def test_known_tool_invalid_arguments_are_repaired_once_with_fixed_public_contract() -> None:
    class ArgumentRepairPort(_CompactPort):
        history: list = []

        async def generate_structured(self, messages, output_schema, config):
            self.payload = {
                "tool": "act_01",
                "args": {} if self.calls == 0 else {"value": "hello"},
            }
            outcome = await super().generate_structured(messages, output_schema, config)
            self.history.append(tuple(messages))
            return outcome

    async def scenario() -> None:
        port = ArgumentRepairPort()
        port.history = []
        adapter = DynamicToolDecisionAdapter(port, _zero_retry_config())

        outcome = await adapter.generate(_required_value_request(await _context()))

        assert not isinstance(outcome, ModelFailure)
        assert port.calls == 2
        assert adapter.last_schema_repair_count == 1
        assert adapter.last_argument_repair_count == 1
        repair_system = port.history[1][0].content
        assert isinstance(repair_system, str)
        assert '"selected_tool":"act_01"' in repair_system
        assert '"required":["value"]' in repair_system
        assert '"field_paths":["parameters.value"]' in repair_system
        assert '"actual"' not in repair_system
        assert '"expected"' not in repair_system
        assert '"value":"hello"' not in repair_system

    asyncio.run(scenario())


def test_argument_repair_remains_zero_package_when_repair_is_invalid_or_changes_tool() -> None:
    class InvalidRepairPort(_CompactPort):
        repaired_tool = "act_01"

        async def generate_structured(self, messages, output_schema, config):
            self.payload = {
                "tool": "act_01" if self.calls == 0 else self.repaired_tool,
                "args": {},
            }
            return await super().generate_structured(messages, output_schema, config)

    async def scenario() -> None:
        request = _required_value_request(await _context())
        invalid = InvalidRepairPort()
        adapter = DynamicToolDecisionAdapter(invalid, _zero_retry_config())
        outcome = await adapter.generate(request)
        assert isinstance(outcome, ModelFailure)
        assert invalid.calls == 2
        assert adapter.last_resolution_code is ToolResolutionCode.INVALID_ARGUMENTS

        changed = InvalidRepairPort()
        changed.repaired_tool = "not_offered"
        adapter = DynamicToolDecisionAdapter(changed, _zero_retry_config())
        outcome = await adapter.generate(request)
        assert isinstance(outcome, ModelFailure)
        assert changed.calls == 2
        assert adapter.last_resolution_code is ToolResolutionCode.INVALID_ARGUMENTS

    asyncio.run(scenario())


def test_outer_format_and_argument_repair_share_one_request_budget() -> None:
    class FormatThenInvalidPort(_CompactPort):
        async def generate_structured(self, messages, output_schema, config):
            if self.calls == 0:
                self.calls += 1
                raise StructuredOutputError("malformed compact proposal")
            self.payload = {"tool": "act_01", "args": {}}
            return await super().generate_structured(messages, output_schema, config)

    async def scenario() -> None:
        port = FormatThenInvalidPort()
        adapter = DynamicToolDecisionAdapter(port, _zero_retry_config())

        outcome = await adapter.generate(_required_value_request(await _context()))

        assert isinstance(outcome, ModelFailure)
        assert port.calls == 2
        assert adapter.last_schema_repair_count == 1
        assert adapter.last_argument_repair_count == 0
        assert adapter.last_resolution_code is ToolResolutionCode.INVALID_ARGUMENTS

    asyncio.run(scenario())


def test_native_zero_and_multiple_calls_are_typed_without_resolving_a_decision() -> None:
    @dataclass
    class NativePort:
        calls: tuple[ToolCall, ...]
        provider: str = "mistral"
        model: str = "mistral-medium-3-5"
        endpoint_class: str = "fixture"
        supports_multimodal: bool = True
        last_call: ModelCallRecord | None = None

        async def generate_tool_calls(self, messages, tools, config, *, require_one):
            del messages, tools, config
            assert require_one is True
            return self.calls

    async def scenario() -> None:
        request = _build_request(await _context())
        zero = DynamicToolDecisionAdapter(NativePort(()), _zero_retry_config())
        zero_outcome = await zero.generate(request)
        assert isinstance(zero_outcome, ModelFailure)
        assert zero.last_resolution_code is ToolResolutionCode.ZERO_CALLS

        multiple = DynamicToolDecisionAdapter(
            NativePort((ToolCall("act_01", {}), ToolCall("act_01", {}))),
            _zero_retry_config(),
        )
        multiple_outcome = await multiple.generate(request)
        assert isinstance(multiple_outcome, ModelFailure)
        assert multiple.last_resolution_code is ToolResolutionCode.MULTIPLE_CALLS

    asyncio.run(scenario())

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from test_model_port_decision_bridge import _context, _zero_retry_config

from affordance_runtime.agent import AgentDecisionPackage, SelectAction
from affordance_runtime.model_boundary import ModelFailure, ModelFailureKind
from affordance_runtime.model_policy.parser import parse_agent_decision
from affordance_runtime.model_policy.policy import _build_request
from affordance_runtime.model_policy.tool_contracts import ToolCall, ToolResolutionCode
from affordance_runtime.model_policy.tool_port_bridge import (
    CompactToolCallPayload,
    DynamicToolDecisionAdapter,
)
from affordance_runtime.model_port import ModelCallRecord, StructuredOutputError


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


def test_compact_tool_bridge_hides_runtime_ids_and_restores_existing_package() -> None:
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
        parsed = parse_agent_decision(response.raw_payload, context.context_id)
        assert isinstance(parsed, SelectAction | AgentDecisionPackage)
        decision = parsed.decision if isinstance(parsed, AgentDecisionPackage) else parsed
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
        async def generate_structured(self, messages, output_schema, config):
            if self.calls == 0:
                self.calls += 1
                raise StructuredOutputError("malformed compact proposal")
            return await super().generate_structured(messages, output_schema, config)

    async def scenario() -> None:
        port = RepairPort()
        adapter = DynamicToolDecisionAdapter(port, _zero_retry_config())

        outcome = await adapter.generate(_build_request(await _context()))

        assert not isinstance(outcome, ModelFailure)
        assert port.calls == 2
        assert adapter.last_schema_repair_count == 1

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

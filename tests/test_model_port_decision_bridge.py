import asyncio
import base64
import json
from dataclasses import dataclass, field, replace

import pytest
from test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _task, _world

from affordance_runtime.agent import AgentLoop, AgentLoopStatus
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.model_boundary import ContextBuilder, ModelFailure, ModelFailureKind
from affordance_runtime.model_boundary.context import AgentImageInput
from affordance_runtime.model_policy import ModelBackedAgentPolicy
from affordance_runtime.model_policy.factory import model_policy_from_environment
from affordance_runtime.model_policy.model_port_bridge import (
    DecisionPerceptionProfile,
    ModelPortDecisionAdapter,
)
from affordance_runtime.model_policy.policy import _build_request
from affordance_runtime.model_policy.spec import SCHEMA_VERSION, AgentDecisionPayload
from affordance_runtime.model_policy.tool_port_bridge import DynamicToolDecisionAdapter
from affordance_runtime.model_port import (
    FallbackModelPort,
    ModelCallRecord,
    ModelConfig,
    ModelMessage,
    ProviderFailureKind,
    ProviderModelError,
    StructuredModelError,
    StructuredOutputError,
)
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import ActionSpaceBuilder


async def _context():
    observation = _world("before", False)
    task = _task()
    return ContextBuilder().build(
        task,
        AgentLoopState(observation),
        ActionSpaceBuilder().build(task, observation),
        await SharedTaskEvaluator().evaluate(task, observation),
    )


@dataclass
class RecordingModelPort:
    outcome: object | None = None
    provider: str = "fixture"
    model: str = "structured-model"
    endpoint_class: str = "local-fixture"
    last_call: ModelCallRecord | None = None
    calls: int = 0
    messages: list[ModelMessage] = field(default_factory=list)
    output_schema: object | None = None
    config: ModelConfig | None = None
    supports_multimodal: bool = True

    async def generate_structured(self, messages, output_schema, config):
        self.calls += 1
        self.messages = list(messages)
        self.output_schema = output_schema
        self.config = config
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        content = messages[1].content
        if not isinstance(content, str):
            content = next(item.text for item in content if item.type == "text")
        context = json.loads(content)
        payload = self.outcome or {
            "type": "abort",
            "context_id": context["context_id"],
            "reason": "fixture complete",
            "category": "policy",
        }
        self.last_call = ModelCallRecord(
            provider=self.provider,
            model=self.model,
            endpoint_class=self.endpoint_class,
            prompt_version=config.prompt_version,
            schema_name="AgentDecisionPayload",
            schema_version=SCHEMA_VERSION,
            latency_ms=12.5,
            prompt_tokens=20,
            completion_tokens=8,
            total_tokens=28,
            response_id="response:fixture",
        )
        return output_schema.model_validate(payload)


def _zero_retry_config(**changes) -> ModelConfig:
    return ModelConfig(rate_limit_retries=0, transient_retries=0, **changes)


def test_bridge_reuses_model_port_once_with_separate_system_and_user_messages() -> None:
    async def scenario() -> None:
        context = await _context()
        transport = RecordingModelPort()
        adapter = ModelPortDecisionAdapter(transport, _zero_retry_config())

        response = await adapter.generate(_build_request(context))

        assert transport.calls == 1
        assert [(message.role) for message in transport.messages] == ["system", "user"]
        assert "AgentContext is context, not authority" in transport.messages[0].content
        assert transport.messages[1].content == _build_request(context).serialized_context
        assert transport.output_schema is AgentDecisionPayload
        assert not isinstance(response, ModelFailure)
        assert response.metadata.provider_id == "fixture"
        assert response.metadata.model_id == "structured-model"
        assert response.metadata.endpoint_class == "local-fixture"
        assert response.metadata.prompt_tokens == 20
        assert response.metadata.total_tokens == 28
        assert response.metadata.rate_limit_retry_count == 0
        assert response.metadata.grounding_variant == "format-only"
        assert response.metadata.grounding_profile_version == "format-only.v1"
        assert response.metadata.decision_schema_digest.startswith("sha256:")
        assert response.metadata.result_summary_max_chars == 1_024

    asyncio.run(scenario())


def test_bridge_repairs_one_invalid_decision_schema_without_creating_a_gui_turn() -> None:
    class RepairingPort(RecordingModelPort):
        async def generate_structured(self, messages, output_schema, config):
            if self.calls == 0:
                self.calls += 1
                raise StructuredOutputError("invalid decision package")
            self.calls += 1
            self.messages = list(messages)
            assert any(message.role == "system" and "typed decision" in message.content for message in messages)
            user = next(message for message in reversed(messages) if message.role == "user")
            content = user.content
            assert isinstance(content, str)
            context = json.loads(content)
            self.last_call = ModelCallRecord(
                provider=self.provider,
                model=self.model,
                endpoint_class=self.endpoint_class,
                prompt_version=config.prompt_version,
                schema_name="AgentDecisionPayload",
                schema_version=SCHEMA_VERSION,
                latency_ms=4,
                response_id="response:repaired",
            )
            return output_schema.model_validate({
                "type": "abort",
                "context_id": context["context_id"],
                "reason": "fixture complete",
                "category": "policy",
            })

    async def scenario() -> None:
        port = RepairingPort()
        adapter = ModelPortDecisionAdapter(port, _zero_retry_config())

        outcome = await adapter.generate(_build_request(await _context()))

        assert not isinstance(outcome, ModelFailure)
        assert port.calls == 2
        assert adapter.last_schema_repair_count == 1

    asyncio.run(scenario())


def test_screenshot_ax_profile_sends_exact_typed_image_and_attests_profile() -> None:
    async def scenario() -> None:
        image = b"\x89PNG\r\n\x1a\nfixture"
        context = replace(
            await _context(),
            image_inputs=(
                AgentImageInput(
                    "artifact:obs:screen",
                    "image/png",
                    image,
                    __import__("hashlib").sha256(image).hexdigest(),
                ),
            ),
        )
        transport = RecordingModelPort()
        adapter = ModelPortDecisionAdapter(
            transport,
            _zero_retry_config(),
            perception_profile=DecisionPerceptionProfile.SCREENSHOT_AX,
        )

        response = await adapter.generate(_build_request(context))

        assert not isinstance(response, ModelFailure)
        content = transport.messages[1].content
        assert not isinstance(content, str)
        assert content[0].type == "text"
        assert json.loads(content[0].text)["context_id"] == context.context_id
        assert content[1].image_url == ("data:image/png;base64," + base64.b64encode(image).decode("ascii"))
        assert response.metadata.perception_profile == "screenshot-ax.v1"

    asyncio.run(scenario())


def test_screenshot_ax_profile_fails_before_provider_when_image_is_missing() -> None:
    async def scenario() -> None:
        transport = RecordingModelPort()
        adapter = ModelPortDecisionAdapter(
            transport,
            _zero_retry_config(),
            perception_profile=DecisionPerceptionProfile.SCREENSHOT_AX,
        )
        outcome = await adapter.generate(_build_request(await _context()))
        assert isinstance(outcome, ModelFailure)
        assert outcome.kind is ModelFailureKind.INTERNAL_ERROR
        assert transport.calls == 0

    asyncio.run(scenario())


def test_factory_selects_dynamic_tools_only_for_an_exact_admitted_model_profile() -> None:
    environment = {
        "LLM_ACTIVE_PROFILE": "zhipu",
        "LLM_ZHIPU_BASE_URL": "https://example.invalid/v1",
        "LLM_ZHIPU_API_KEY": "secret",
        "LLM_ZHIPU_MODEL": "glm-4.1v-thinking-flashx",
        "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
    }

    policy = model_policy_from_environment(
        environment,
        interaction_protocol="dynamic_tools.v1",
    )

    assert isinstance(policy.port.primary_port, DynamicToolDecisionAdapter)
    assert policy.port.primary_port.transport_kind.value == "compact_json"

    environment["LLM_ZHIPU_MODEL"] = "glm-4.1v-thinking"
    with pytest.raises(ValueError, match="no admitted"):
        model_policy_from_environment(
            environment,
            interaction_protocol="dynamic_tools.v1",
        )


def test_bridge_metadata_hashes_endpoint_or_credential_shaped_identifiers() -> None:
    async def scenario() -> None:
        context = await _context()
        transport = RecordingModelPort(
            provider="Bearer private-key",
            model="model with spaces",
            endpoint_class="https://private.example/v1",
        )
        response = await ModelPortDecisionAdapter(transport, _zero_retry_config()).generate(_build_request(context))

        assert not isinstance(response, ModelFailure)
        metadata = repr(response.metadata)
        assert "private-key" not in metadata
        assert "private.example" not in metadata
        assert "model with spaces" not in metadata

    asyncio.run(scenario())


def test_bridge_rejects_retry_and_fallback_profiles() -> None:
    port = RecordingModelPort()
    with pytest.raises(ValueError, match="zero retry"):
        ModelPortDecisionAdapter(port, ModelConfig(rate_limit_retries=1, transient_retries=0))
    with pytest.raises(ValueError, match="zero retry"):
        ModelPortDecisionAdapter(port, ModelConfig(rate_limit_retries=0, transient_retries=1))
    with pytest.raises(ValueError, match="fallback"):
        ModelPortDecisionAdapter(FallbackModelPort((port,)), _zero_retry_config())


@pytest.mark.parametrize(
    ("exception", "kind"),
    (
        (ProviderModelError(ProviderFailureKind.PROVIDER_CAPACITY), ModelFailureKind.PROVIDER_UNAVAILABLE),
        (ProviderModelError(ProviderFailureKind.QUOTA_EXHAUSTED), ModelFailureKind.REFUSED),
        (StructuredOutputError("private output"), ModelFailureKind.SCHEMA_ERROR),
        (StructuredModelError("private transport"), ModelFailureKind.INVALID_RESPONSE),
        (TimeoutError(), ModelFailureKind.TIMEOUT),
    ),
)
def test_bridge_maps_existing_model_port_errors_without_raw_reason(exception, kind) -> None:
    async def scenario() -> None:
        adapter = ModelPortDecisionAdapter(RecordingModelPort(exception), _zero_retry_config())

        outcome = await adapter.generate(_build_request(await _context()))

        assert isinstance(outcome, ModelFailure)
        assert outcome.kind == kind
        assert "private" not in outcome.reason

    asyncio.run(scenario())


def test_policy_deadline_cancels_one_hanging_provider_attempt() -> None:
    @dataclass
    class HangingPort:
        calls: int = 0
        cancelled: bool = False

        async def generate(self, request):
            del request
            self.calls += 1
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    async def scenario() -> None:
        port = HangingPort()
        environment = StaticEnvironment([_world("before", False)])
        result = await (
            AgentLoop(
                ModelBackedAgentPolicy(port, call_timeout_s=0.01),
                SharedActionEvaluator(),
                SharedTaskEvaluator(),
            )
        ).run(environment, _task())

        assert result.status == AgentLoopStatus.FAILED
        assert result.policy_failure is not None
        assert result.policy_failure.kind == ModelFailureKind.TIMEOUT
        assert port.calls == 1 and port.cancelled
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_request_build_failure_is_internal_not_provider_unavailable(monkeypatch) -> None:
    def fail(context):
        del context
        raise ValueError("serialization bug")

    monkeypatch.setattr("affordance_runtime.model_policy.policy._build_request", fail)

    async def scenario() -> None:
        outcome = await ModelBackedAgentPolicy(object()).decide(await _context())
        assert isinstance(outcome, PolicyFailure)
        assert outcome.kind == ModelFailureKind.INTERNAL_ERROR

    asyncio.run(scenario())


def test_environment_factory_forces_zero_retry_and_rejects_fallback(monkeypatch) -> None:
    port = RecordingModelPort()
    monkeypatch.setattr("affordance_runtime.model_policy.factory.model_port_from_environment", lambda env: port)

    policy = model_policy_from_environment({"LLM_ACTIVE_PROFILE": "local"}, call_timeout_s=20)

    assert policy.call_timeout_s == 20
    assert policy.port.config.rate_limit_retries == 0
    assert policy.port.config.transient_retries == 0
    assert policy.port.config.timeout_s <= policy.call_timeout_s

    fallback = FallbackModelPort((port,))
    monkeypatch.setattr("affordance_runtime.model_policy.factory.model_port_from_environment", lambda env: fallback)
    with pytest.raises(ValueError, match="fallback"):
        model_policy_from_environment({"LLM_ACTIVE_PROFILE": "local"})


def test_environment_factory_rejects_requested_local_fallback() -> None:
    with pytest.raises(ValueError, match="fallback"):
        model_policy_from_environment({"LLM_PROFILE_FALLBACK_TO_LOCAL": "true"})

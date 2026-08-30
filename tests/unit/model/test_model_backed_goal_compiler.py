from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from affordance_runtime.goals import Failed, GoalPlanBoundary, GoalPlanProposal, Ready
from affordance_runtime.goals.compiler import GoalCompilerRequest
from affordance_runtime.model.goal_compiler import (
    GOAL_COMPILER_INSTRUCTIONS,
    GOAL_COMPILER_PROMPT_VERSION,
    GoalCompilerModelResponse,
    ModelBackedGoalCompiler,
    model_goal_compiler_from_environment,
)
from affordance_runtime.model.policy import model_roles_from_environment
from affordance_runtime.model.providers.port import (
    ModelConfig,
    ProviderFailureKind,
    ProviderModelError,
    StructuredModelError,
    StructuredOutputError,
    StructuredOutputViolation,
)
from tests.support.agent.core_loop_support import _task, _world


def _item(**changes):
    value = {
        "id": "complete_requested_changes",
        "objective": "Complete every requested visible change without altering unrelated controls.",
        "done_when": "Every relevant item visibly has the requested state.",
        "depends_on": (),
        "final": False,
    }
    value.update(changes)
    return value


def _ready(**changes):
    return GoalCompilerModelResponse(disposition="ready", items=(_item(**changes),))


@dataclass
class ScriptedModelPort:
    outcomes: list[object]
    provider: str = "zhipu"
    model: str = "glm-4.7-flash"
    endpoint_class: str = "fixture"
    last_call: object | None = None
    last_transcript: object | None = None
    messages: list[tuple[object, ...]] = field(default_factory=list)
    schemas: list[type] = field(default_factory=list)
    configs: list[object] = field(default_factory=list)

    @property
    def supports_multimodal(self) -> bool:
        return False

    async def generate_structured(self, messages, output_schema, config):
        index = len(self.messages) + 1
        self.messages.append(tuple(messages))
        self.schemas.append(output_schema)
        self.configs.append(config)
        self.last_call = SimpleNamespace(
            response_id=f"response:{index}",
            latency_ms=float(index),
            prompt_tokens=10 * index,
            completion_tokens=2 * index,
            total_tokens=12 * index,
        )
        self.last_transcript = {
            "llm.input_messages": [{"role": "user", "content": f"input:{index}"}],
            "llm.output_messages": [{"role": "assistant", "content": f"raw:{index}"}],
        }
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def test_model_schema_is_five_field_fixed_depth_and_tolerant_of_surplus() -> None:
    schema = json.dumps(GoalCompilerModelResponse.model_json_schema(), sort_keys=True)
    assert all(name in schema for name in ("id", "objective", "done_when", "depends_on", "final"))
    assert all(
        name not in schema
        for name in (
            "edge_path",
            "predicate",
            "target_kind",
            "target_facts",
            "EntityFilter",
            "Relation",
            "FactEquals",
            "node_id",
        )
    )
    response = GoalCompilerModelResponse.model_validate(
        {
            "disposition": "ready",
            "items": ({**_item(), "label": "ignored description", "relation": "ignored"},),
            "unexpected_envelope_note": "ignored",
        }
    )
    assert response.items[0].model_dump() == _item()


def test_initial_attempt_uses_independent_prompt_and_preserves_transcript() -> None:
    port = ScriptedModelPort([_ready()])
    compiler = ModelBackedGoalCompiler(port)
    outcome = asyncio.run(compiler.compile(GoalCompilerRequest(_task(), _world("initial", False))))
    assert isinstance(outcome, GoalPlanProposal)
    assert port.schemas == [GoalCompilerModelResponse]
    assert port.configs[0].prompt_version == GOAL_COMPILER_PROMPT_VERSION
    assert "optional GoalCompiler" in port.messages[0][0].content
    assert "Describe outcomes, not internal" in port.messages[0][0].content
    assert "semantic_contract" not in port.messages[0][1].content
    assert compiler.last_generation_attempts[0].transcript["llm.output_messages"][0]["content"] == "raw:1"


def test_needs_input_contract_reserves_environment_facts_for_action_policy() -> None:
    assert GOAL_COMPILER_PROMPT_VERSION == "goal-plan-compiler.v8"
    assert "user exclusively owns" in GOAL_COMPILER_INSTRUCTIONS
    assert "GUI surface, screenshot, page, application, file" in GOAL_COMPILER_INSTRUCTIONS
    assert "never ask the user to supply the requested result" in GOAL_COMPILER_INSTRUCTIONS
    assert "Do not collapse a genuinely multi-stage information task" in GOAL_COMPILER_INSTRUCTIONS
    assert "separate dependent items" in GOAL_COMPILER_INSTRUCTIONS
    assert "TaskGoal is the sole semantic authority" in GOAL_COMPILER_INSTRUCTIONS
    assert "turn an implication into" in GOAL_COMPILER_INSTRUCTIONS
    assert "explicit-statement requirement" in GOAL_COMPILER_INSTRUCTIONS
    assert "return not_required rather than rewriting the criterion" in GOAL_COMPILER_INSTRUCTIONS


def test_generation_attempt_records_role_thinking_contract() -> None:
    port = ScriptedModelPort([_ready()])
    port.thinking_mode = None
    compiler = ModelBackedGoalCompiler(port, ModelConfig(thinking_mode="disabled"))

    asyncio.run(compiler.compile(GoalCompilerRequest(_task())))

    attempt = compiler.last_generation_attempts[0]
    assert attempt.thinking_requested == "disabled"
    assert attempt.thinking_effective == "disabled"


def test_schema_repair_preserves_both_raw_attempts() -> None:
    port = ScriptedModelPort(
        [
            StructuredOutputError("invalid", violations=(StructuredOutputViolation("$", "json_invalid"),)),
            _ready(),
        ]
    )
    compiler = ModelBackedGoalCompiler(port)
    outcome = asyncio.run(compiler.compile(GoalCompilerRequest(_task())))
    assert isinstance(outcome, GoalPlanProposal)
    assert compiler.last_schema_repair_count == 1
    assert [item.phase for item in compiler.last_generation_attempts] == [
        "goal_compile_initial",
        "goal_compile_schema_repair",
    ]
    assert [item.transcript["llm.output_messages"][0]["content"] for item in compiler.last_generation_attempts] == [
        "raw:1",
        "raw:2",
    ]


def test_initial_and_repair_failure_degrade_advisory_with_transcripts() -> None:
    compiler = ModelBackedGoalCompiler(
        ScriptedModelPort(
            [
                StructuredOutputError("invalid"),
                StructuredOutputError("still invalid"),
            ]
        )
    )
    result = asyncio.run(compiler.compile(GoalCompilerRequest(_task())))
    assert result == Failed(1, "goal_compiler_model_failed")
    assert len(compiler.last_generation_attempts) == 2
    assert all(item.transcript is not None for item in compiler.last_generation_attempts)


def test_provider_failure_is_typed_and_exception_visible() -> None:
    compiler = ModelBackedGoalCompiler(ScriptedModelPort([StructuredModelError("redacted")]))
    result = asyncio.run(compiler.compile(GoalCompilerRequest(_task())))
    assert result == Failed(1, "goal_compiler_model_failed")
    assert compiler.last_generation_attempts[0].exception_class == "StructuredModelError"


def test_transient_rate_limit_retries_once_and_preserves_both_attempts() -> None:
    port = ScriptedModelPort(
        [
            ProviderModelError(ProviderFailureKind.RATE_LIMIT_TRANSIENT),
            _ready(),
        ]
    )
    compiler = ModelBackedGoalCompiler(
        port,
        ModelConfig(
            rate_limit_retries=0,
            transient_retries=0,
            rate_limit_backoff_s=0,
        ),
    )

    result = asyncio.run(compiler.compile(GoalCompilerRequest(_task())))

    assert isinstance(result, GoalPlanProposal)
    assert [item.phase for item in compiler.last_generation_attempts] == [
        "goal_compile_initial",
        "goal_compile_initial_provider_retry",
    ]
    assert [item.status for item in compiler.last_generation_attempts] == ["failed", "accepted"]
    assert [item.transcript["llm.output_messages"][0]["content"] for item in compiler.last_generation_attempts] == [
        "raw:1",
        "raw:2",
    ]


def test_transient_rate_limit_retry_is_bounded_to_one() -> None:
    compiler = ModelBackedGoalCompiler(
        ScriptedModelPort(
            [
                ProviderModelError(ProviderFailureKind.RATE_LIMIT_TRANSIENT),
                ProviderModelError(ProviderFailureKind.RATE_LIMIT_TRANSIENT),
            ]
        ),
        ModelConfig(rate_limit_retries=0, transient_retries=0, rate_limit_backoff_s=0),
    )

    result = asyncio.run(compiler.compile(GoalCompilerRequest(_task())))

    assert result == Failed(1, "goal_compiler_model_failed")
    assert len(compiler.last_generation_attempts) == 2


def test_non_transient_provider_failure_is_not_retried() -> None:
    compiler = ModelBackedGoalCompiler(
        ScriptedModelPort([ProviderModelError(ProviderFailureKind.QUOTA_EXHAUSTED)]),
        ModelConfig(rate_limit_retries=0, transient_retries=0, rate_limit_backoff_s=0),
    )

    result = asyncio.run(compiler.compile(GoalCompilerRequest(_task())))

    assert result == Failed(1, "goal_compiler_model_failed")
    assert len(compiler.last_generation_attempts) == 1


def test_contract_repair_appends_to_initial_lineage() -> None:
    bad = GoalPlanProposal(1, ({"id": "broken"},))
    port = ScriptedModelPort([_ready(), _ready()])
    compiler = ModelBackedGoalCompiler(port)
    original = compiler.compile
    calls = 0

    async def compile_with_bad_first(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            await original(request)
            return bad
        return await original(request)

    object.__setattr__(compiler, "compile", compile_with_bad_first)
    result = asyncio.run(GoalPlanBoundary().resolve(compiler, _task(), next_plan_version=1))
    assert isinstance(result, Ready)
    assert [item.phase for item in compiler.last_generation_attempts] == [
        "goal_compile_initial",
        "goal_compile_contract_repair",
    ]


@pytest.mark.parametrize(
    "payload",
    (
        {"disposition": "ready"},
        {"disposition": "needs_input", "question": "Which?", "missing_fields": ()},
        {"disposition": "unsupported"},
        {"disposition": "ready", "items": (_item(depends_on=("missing",)),)},
        {"disposition": "ready", "items": (_item(depends_on=("complete_requested_changes",)),)},
    ),
)
def test_invalid_envelope_shapes_fail_typed(payload) -> None:
    with pytest.raises(ValidationError):
        GoalCompilerModelResponse.model_validate(payload)


def test_role_factory_uses_distinct_better_compiler_model(monkeypatch) -> None:
    from affordance_runtime.model import goal_compiler as module
    from affordance_runtime.model.policy import factory

    def build(environment):
        port = ScriptedModelPort([])
        port.model = environment["LLM_ZHIPU_MODEL"]
        return port

    action_policy = object()
    monkeypatch.setattr(factory, "model_policy_from_environment", lambda *args, **kwargs: action_policy)
    monkeypatch.setattr(module, "model_port_from_environment", build)
    roles = model_roles_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "zhipu",
            "LLM_ZHIPU_API_KEY": "secret",
            "LLM_ZHIPU_MODEL": "glm-4.1v-thinking-flashx",
            "LLM_GOAL_COMPILER_MODEL": "glm-4.7-flash",
        }
    )
    assert roles.action_policy is action_policy
    assert roles.goal_compiler.port.model == "glm-4.7-flash"


def test_role_factory_uses_aliyun_compiler_model_override(monkeypatch) -> None:
    from affordance_runtime.model import goal_compiler as module
    from affordance_runtime.model.policy import factory

    def build(environment):
        port = ScriptedModelPort([])
        port.model = environment["LLM_ALIYUN_MODEL"]
        return port

    action_policy = object()
    monkeypatch.setattr(factory, "model_policy_from_environment", lambda *args, **kwargs: action_policy)
    monkeypatch.setattr(module, "model_port_from_environment", build)

    roles = model_roles_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "aliyun",
            "LLM_ALIYUN_BASE_URL": "https://aliyun.invalid/compatible-mode/v1",
            "LLM_ALIYUN_API_KEY": "secret",
            "LLM_ALIYUN_MODEL": "glm-5.2",
            "LLM_GOAL_COMPILER_MODEL": "glm-5.2-compiler",
        }
    )

    assert roles.action_policy is action_policy
    assert roles.goal_compiler.port.model == "glm-5.2-compiler"


def test_role_factory_uses_deepseek_compiler_model_override(monkeypatch) -> None:
    from affordance_runtime.model import goal_compiler as module
    from affordance_runtime.model.policy import factory

    def build(environment):
        port = ScriptedModelPort([])
        port.model = environment["LLM_DEEPSEEK_MODEL"]
        return port

    action_policy = object()
    monkeypatch.setattr(factory, "model_policy_from_environment", lambda *args, **kwargs: action_policy)
    monkeypatch.setattr(module, "model_port_from_environment", build)

    roles = model_roles_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "deepseek",
            "LLM_DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            "LLM_DEEPSEEK_API_KEY": "secret",
            "LLM_DEEPSEEK_MODEL": "deepseek-v4-flash",
            "LLM_GOAL_COMPILER_MODEL": "deepseek-v4-pro",
        }
    )

    assert roles.action_policy is action_policy
    assert roles.goal_compiler.port.model == "deepseek-v4-pro"


def test_deepseek_goal_compiler_disables_provider_thinking_for_structured_role() -> None:
    compiler = model_goal_compiler_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "deepseek",
            "LLM_DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            "LLM_DEEPSEEK_API_KEY": "secret",
            "LLM_DEEPSEEK_MODEL": "deepseek-v4-flash",
        }
    )

    assert compiler.port.supports_thinking_control is True
    assert compiler.config.thinking_mode == "disabled"


def test_goal_compiler_does_not_send_thinking_to_provider_without_control() -> None:
    compiler = model_goal_compiler_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "aliyun",
            "LLM_ALIYUN_BASE_URL": "https://aliyun.invalid/compatible-mode/v1",
            "LLM_ALIYUN_API_KEY": "secret",
            "LLM_ALIYUN_MODEL": "glm-5.2",
        }
    )

    assert compiler.port.supports_thinking_control is False
    assert compiler.config.thinking_mode is None


def test_pydantic_policy_keeps_distinct_compiler_model_override(monkeypatch) -> None:
    from affordance_runtime.model import goal_compiler as module
    from affordance_runtime.model.policy import factory

    def build(environment):
        port = ScriptedModelPort([])
        port.model = environment["LLM_ZHIPU_MODEL"]
        return port

    action_policy = object()
    monkeypatch.setattr(factory, "model_policy_from_environment", lambda *args, **kwargs: action_policy)
    monkeypatch.setattr(module, "model_port_from_environment", build)

    roles = model_roles_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "zhipu",
            "LLM_ZHIPU_API_KEY": "secret",
            "LLM_ZHIPU_MODEL": "glm-4.6",
            "LLM_GOAL_COMPILER_MODEL": "glm-4.7-flash",
        }
    )

    assert roles.action_policy is action_policy
    assert roles.goal_compiler.port.model == "glm-4.7-flash"


def test_role_factory_can_explicitly_disable_goal_compiler(monkeypatch) -> None:
    from affordance_runtime.goals import UnavailableGoalCompiler
    from affordance_runtime.model.policy import factory

    action_policy = object()
    monkeypatch.setattr(factory, "model_policy_from_environment", lambda *args, **kwargs: action_policy)

    roles = model_roles_from_environment(
        {
            "LLM_ACTIVE_PROFILE": "zhipu",
            "LLM_ZHIPU_MODEL": "glm-4.6",
            "LLM_GOAL_COMPILER_MODEL": "glm-4.7-flash",
            "LLM_GOAL_COMPILER_MODE": "disabled",
        }
    )

    assert roles.action_policy is action_policy
    assert isinstance(roles.goal_compiler, UnavailableGoalCompiler)

    with pytest.raises(ValueError, match="must be model or disabled"):
        model_roles_from_environment(
            {
                "LLM_GOAL_COMPILER_MODE": "unknown",
            }
        )

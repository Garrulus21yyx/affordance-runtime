from __future__ import annotations

from dataclasses import dataclass
from itertools import chain, combinations

import pytest

from affordance_runtime.agent import (
    ALL_DECISION_CAPABILITIES,
    TOOL_ACTION_DECISION_CAPABILITIES,
    DecisionCapability,
    TargetRuntime,
    UnsupportedCompositionError,
)
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.benchmarks.model_protocol import (
    PRIMARY_BENCHMARK_ACTION_PROTOCOL,
    PRIMARY_BENCHMARK_REQUIRED_DECISIONS,
)
from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkComposition
from affordance_runtime.model_policy import (
    DYNAMIC_TOOLS_PROTOCOL,
    GROUNDED_TOOLS_PROTOCOL,
    STRUCTURED_PACKAGE_PROTOCOL,
    DynamicToolDecisionAdapter,
    GroundedToolDecisionAdapter,
    ModelBackedAgentPolicy,
    ModelPortDecisionAdapter,
)
from affordance_runtime.model_policy.grounded_tool_contracts import GroundedToolPhase
from affordance_runtime.model_port import ModelConfig


@dataclass
class _Transport:
    provider: str = "zhipu"
    model: str = "glm-4.1v-thinking-flashx"
    endpoint_class: str = "fixture"
    supports_multimodal: bool = True


class _Evaluator:
    async def evaluate(self, *args, **kwargs):
        del args, kwargs
        raise AssertionError("composition capability checks must not call evaluators")


@dataclass
class _DeclaredPolicy:
    supported_decisions: frozenset[DecisionCapability]

    async def decide(self, context):
        del context
        raise AssertionError("composition capability checks must not call the policy")


def _config() -> ModelConfig:
    return ModelConfig(timeout_s=1, rate_limit_retries=0, transient_retries=0)


def test_each_action_protocol_declares_its_exact_supported_decisions() -> None:
    structured = ModelPortDecisionAdapter(_Transport(), _config())
    dynamic = DynamicToolDecisionAdapter(_Transport(), _config())
    grounded = GroundedToolDecisionAdapter(_Transport(), _config())

    assert structured.interaction_protocol == STRUCTURED_PACKAGE_PROTOCOL
    assert structured.supported_decisions == ALL_DECISION_CAPABILITIES
    assert dynamic.interaction_protocol == DYNAMIC_TOOLS_PROTOCOL
    assert dynamic.supported_decisions == TOOL_ACTION_DECISION_CAPABILITIES
    assert grounded.interaction_protocol == GROUNDED_TOOLS_PROTOCOL
    assert grounded.supported_decisions == TOOL_ACTION_DECISION_CAPABILITIES


def test_objective_phase_does_not_claim_action_decision_capabilities() -> None:
    adapter = GroundedToolDecisionAdapter(
        _Transport(),
        _config(),
        phase=GroundedToolPhase.OBJECTIVE_PROPOSAL,
    )

    assert adapter.supported_decisions == frozenset()


def test_model_policy_preserves_adapter_capabilities() -> None:
    adapter = DynamicToolDecisionAdapter(_Transport(), _config())

    assert ModelBackedAgentPolicy(adapter, call_timeout_s=2).supported_decisions == (
        TOOL_ACTION_DECISION_CAPABILITIES
    )


def test_runtime_accepts_exactly_subsets_of_declared_capabilities() -> None:
    supported = TOOL_ACTION_DECISION_CAPABILITIES
    evaluator = _Evaluator()
    all_subsets = chain.from_iterable(
        combinations(tuple(ALL_DECISION_CAPABILITIES), size)
        for size in range(len(ALL_DECISION_CAPABILITIES) + 1)
    )

    for subset in all_subsets:
        required = frozenset(subset)
        if required <= supported:
            runtime = TargetRuntime(
                AgentDecisionPorts(_DeclaredPolicy(supported)),
                evaluator,
                evaluator,
                required_decisions=required,
            )
            assert runtime.required_decisions == required
            continue
        with pytest.raises(UnsupportedCompositionError) as caught:
            TargetRuntime(
                AgentDecisionPorts(_DeclaredPolicy(supported)),
                evaluator,
                evaluator,
                required_decisions=required,
            )
        assert caught.value.outcome.required_decisions == required
        assert caught.value.outcome.supported_decisions == supported
        assert caught.value.outcome.missing_decisions == required - supported


def test_required_decisions_reject_stringly_declared_capabilities() -> None:
    evaluator = _Evaluator()

    with pytest.raises(TypeError, match="typed DecisionCapability"):
        TargetRuntime(
            AgentDecisionPorts(_DeclaredPolicy(TOOL_ACTION_DECISION_CAPABILITIES)),
            evaluator,
            evaluator,
            required_decisions=frozenset({"select_action"}),  # type: ignore[arg-type]
        )


def test_current_benchmark_primary_protocol_is_grounded_tools() -> None:
    assert PRIMARY_BENCHMARK_ACTION_PROTOCOL == GROUNDED_TOOLS_PROTOCOL
    assert PRIMARY_BENCHMARK_REQUIRED_DECISIONS == TOOL_ACTION_DECISION_CAPABILITIES
    composition = BenchmarkComposition(
        _DeclaredPolicy(TOOL_ACTION_DECISION_CAPABILITIES),
        _Evaluator(),
        _Evaluator(),
        required_decisions=PRIMARY_BENCHMARK_REQUIRED_DECISIONS,
    )
    assert composition.required_decisions == TOOL_ACTION_DECISION_CAPABILITIES

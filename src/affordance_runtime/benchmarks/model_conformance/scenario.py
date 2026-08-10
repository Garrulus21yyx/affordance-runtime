"""Build the current real-DOM public AgentContext without executing an action."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent.evaluation_control import validated_task_evaluation
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.benchmarks.target_loop.real_adapter_support import (
    real_adapter_task,
    real_dom_environment,
)
from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.model_boundary.context import AgentContext
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.model_policy.prompt import MODEL_POLICY_INSTRUCTIONS
from affordance_runtime.model_policy.serialization import serialize_agent_context
from affordance_runtime.model_policy.spec import decision_response_schema
from affordance_runtime.world.action_space import ActionSpaceBuilder

from .complexity import measure_model_input_complexity
from .contracts import ModelInputComplexity


@dataclass(frozen=True)
class LiveDomScenario:
    context: AgentContext
    serialized_context: str
    complexity: ModelInputComplexity


async def build_live_dom_scenario() -> LiveDomScenario:
    instrumentation = BenchmarkInstrumentation()
    environment = real_dom_environment(instrumentation)
    task = real_adapter_task()
    try:
        acquisition = await environment.reset(task)
        if acquisition.observation is None:
            raise RuntimeError("model conformance initial acquisition failed")
        observation = acquisition.observation
        state = AgentLoopState(observation, remaining_turns=task.loop_budget.max_turns)
        evaluation = await validated_task_evaluation(ProductionTaskEvaluator(), task, observation)
        action_space = ActionSpaceBuilder().build(task, observation)
        builder = ContextBuilder()
        context = builder.build(
            task,
            state,
            action_space,
            evaluation,
            observation_capabilities=environment.observation_capabilities,
        )
        serialized = serialize_agent_context(context)
        complexity = measure_model_input_complexity(
            serialized, MODEL_POLICY_INSTRUCTIONS, decision_response_schema(),
        )
        return LiveDomScenario(context, serialized, complexity)
    finally:
        close = getattr(environment, "close", None)
        if close is not None:
            await close()

"""Public-context-only scripted conformance policy and mechanical evaluators."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from affordance_runtime.agent import SelectAction
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.benchmarks.external_smoke.case_environment import ExternalEnvironmentTaskEvaluator
from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkComposition
from affordance_runtime.evaluation import ProductionActionOutcomeProjector
from affordance_runtime.model.policy import (
    ModelBackedAgentPolicy,
    ModelInvocationResult,
    ModelMetadata,
    ResolvedModelDecision,
)


@dataclass
class BrowserGymStructuredDecisionPort:
    """Conformance-only typed port; consumes the canonical AgentContext."""

    calls: int = 0
    public_contexts: list[AgentContext] = field(default_factory=list)

    async def generate(self, request):
        self.calls += 1
        context = request.agent_context
        self.public_contexts.append(context)
        decision = _public_decision(context)
        metadata = ModelMetadata(
            provider_id="conformance", model_id="scripted-structured",
            response_id=f"response:{self.calls}", endpoint_class="in-process",
            prompt_version="browsergym-adapter-conformance.v1",
            schema_version="typed-agent-context.v1",
        )
        return ModelInvocationResult(
            output=ResolvedModelDecision(decision, metadata),
            metadata=metadata,
            lineage={"role": "ActionPolicy", "adapter": "conformance"},
        )


def adapter_conformance_composition(environment, port) -> BenchmarkComposition:
    return BenchmarkComposition(
        ModelBackedAgentPolicy(port, call_timeout_s=10),
        ProductionActionOutcomeProjector(),
        ExternalEnvironmentTaskEvaluator(environment.benchmark_task_id, environment),
    )


def _public_decision(context: AgentContext) -> SelectAction:
    instruction = context.task.instruction
    actions = context.actions.options
    quoted = _quoted(instruction)
    if instruction.casefold().startswith("enter "):
        desired = quoted[0] if quoted else ""
        fill = _first(actions, "type_text")
        if fill is not None and fill.target_state.get("value") != desired:
            return _selection(context, fill, {"text": desired})
        return _selection(context, _labelled(actions, "activate", "submit"), {})
    if instruction.casefold().startswith("select "):
        match = re.search(r"select\s+(.+?)\s+from", instruction, flags=re.IGNORECASE)
        desired = match.group(1).strip() if match else ""
        select = _first(actions, "select_option")
        if select is not None and select.target_state.get("value") != desired:
            return _selection(context, select, {"value": desired})
        return _selection(context, _labelled(actions, "activate", "submit"), {})
    label = quoted[0] if quoted else ""
    return _selection(context, _labelled(actions, "activate", label), {})


def _selection(context, option, parameters) -> SelectAction:
    if option is None:
        raise ValueError("public task instruction does not match the current ActionSpace")
    return SelectAction(context.context_id, option.action_id, parameters)


def _first(actions, semantic):
    return next((item for item in actions if item.semantic_action == semantic), None)


def _labelled(actions, semantic, label):
    return next(
        (
            item for item in actions
            if item.semantic_action == semantic
            and item.target_label.casefold() == label.casefold()
        ),
        None,
    )


def _quoted(instruction: str) -> tuple[str, ...]:
    return tuple(re.findall(r'"([^"\\]*)"', instruction))

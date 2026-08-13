"""Public-context-only scripted conformance policy and mechanical evaluators."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from affordance_runtime.benchmarks.external_smoke.browsergym_action_evaluator import (
    BrowserGymMechanicalActionEvaluator,
)
from affordance_runtime.benchmarks.external_smoke.environment import ExternalEnvironmentTaskEvaluator
from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkComposition
from affordance_runtime.model_policy import ModelBackedAgentPolicy, ModelMetadata, ResolvedModelDecision
from affordance_runtime.model_policy.spec import AgentDecisionPayload, payload_to_decision


@dataclass
class BrowserGymStructuredDecisionPort:
    """Conformance-only structured port; consumes the same serialized public context as a model."""

    calls: int = 0
    serialized_contexts: list[str] = field(default_factory=list)

    async def generate(self, request):
        self.calls += 1
        self.serialized_contexts.append(request.serialized_context)
        context = json.loads(request.serialized_context)
        payload = _public_decision(context)
        decision = payload_to_decision(AgentDecisionPayload.model_validate(payload), request.context_id)
        return ResolvedModelDecision(
            decision,
            ModelMetadata(
                provider_id="conformance", model_id="scripted-structured",
                response_id=f"response:{self.calls}", endpoint_class="in-process",
                prompt_version="browsergym-adapter-conformance.v1",
                schema_version=request.schema_version,
            ),
        )


def adapter_conformance_composition(environment, port) -> BenchmarkComposition:
    return BenchmarkComposition(
        ModelBackedAgentPolicy(port, call_timeout_s=10),
        BrowserGymMechanicalActionEvaluator(),
        ExternalEnvironmentTaskEvaluator(environment.benchmark_task_id, environment),
    )


def _public_decision(context: dict[str, object]) -> dict[str, object]:
    instruction = _instruction(context)
    actions = _actions(context)
    targets = _targets(context)
    quoted = _quoted(instruction)
    if instruction.casefold().startswith("enter "):
        desired = quoted[0] if quoted else ""
        fill = _first(actions, "fill")
        if fill is not None and _target_value(targets, fill) != desired:
            return _selection(context, fill, {"value": desired})
        return _selection(context, _labelled(actions, targets, "activate", "submit"), {})
    if instruction.casefold().startswith("select "):
        match = re.search(r"select\s+(.+?)\s+from", instruction, flags=re.IGNORECASE)
        desired = match.group(1).strip() if match else ""
        select = _first(actions, "select")
        if select is not None and _target_value(targets, select) != desired:
            return _selection(context, select, {"value": desired})
        return _selection(context, _labelled(actions, targets, "activate", "submit"), {})
    label = quoted[0] if quoted else ""
    return _selection(context, _labelled(actions, targets, "activate", label), {})


def _selection(context, option, parameters) -> dict[str, object]:
    if option is None:
        raise ValueError("public task instruction does not match the current ActionSpace")
    return {
        "type": "select_action", "context_id": context["context_id"],
        "action_id": option["action_id"], "parameters": parameters, "destination_id": "",
    }


def _instruction(context) -> str:
    task = context.get("task", {})
    return str(task.get("instruction", "")) if isinstance(task, dict) else ""


def _actions(context) -> list[dict[str, object]]:
    actions = context.get("actions", {})
    values = actions.get("options", ()) if isinstance(actions, dict) else ()
    return [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []


def _targets(context) -> dict[str, dict[str, object]]:
    world = context.get("world", {})
    section = world.get("targets", {}) if isinstance(world, dict) else {}
    values = section.get("items", ()) if isinstance(section, dict) else ()
    return {str(item.get("target_id")): item for item in values if isinstance(item, dict)}


def _target_value(targets: dict[str, dict[str, object]], action: dict[str, object]) -> object:
    target = targets.get(str(action.get("target_id")), {})
    state = target.get("state")
    return state.get("value") if isinstance(state, dict) else None


def _first(actions, semantic):
    return next((item for item in actions if item.get("semantic_action") == semantic), None)


def _labelled(actions, targets, semantic, label):
    return next(
        (
            item for item in actions
            if item.get("semantic_action") == semantic
            and str(targets.get(str(item.get("target_id")), {}).get("label", "")).casefold() == label.casefold()
        ),
        None,
    )


def _quoted(instruction: str) -> tuple[str, ...]:
    return tuple(re.findall(r'"([^"\\]*)"', instruction))

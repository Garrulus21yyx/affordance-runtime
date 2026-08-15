"""Level-4 real DOM attempt through the production target AgentLoop."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from affordance_runtime.agent import Abort, AgentLoopStatus, SelectAction
from affordance_runtime.agent.context.failures import ModelFailure
from affordance_runtime.agent.decision_capability import DecisionCapability
from affordance_runtime.app.composition import compose_target_runtime
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.benchmarks.target_loop.real_adapter_support import real_adapter_task, real_dom_environment
from affordance_runtime.benchmarks.target_loop.support import CurrentFactActionEvaluator
from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.contracts import ResolvedModelDecision
from affordance_runtime.model.policy.grounding import DecisionGroundingVariant
from affordance_runtime.model.policy.model_port_bridge import ModelPortDecisionAdapter
from affordance_runtime.model.providers.port import ModelConfig, ModelPort

from .contracts import ConformanceAttempt, ModelConformanceStage
from .stages import AttributedDecision, attribute_decision_payload


@dataclass
class CapturingDecisionPort:
    wrapped: ModelPortDecisionAdapter
    request: object | None = None
    outcome: ResolvedModelDecision | ModelFailure | None = None

    @property
    def supported_decisions(self) -> frozenset[DecisionCapability]:
        return self.wrapped.supported_decisions

    @property
    def transport_timeout_s(self) -> float:
        return self.wrapped.transport_timeout_s

    async def generate(self, request):
        self.request = request
        self.outcome = await self.wrapped.generate(request)
        return self.outcome


async def run_level_four_attempt(
    port: ModelPort,
    *,
    grounding_variant: str,
    attempt_number: int,
) -> ConformanceAttempt:
    config = ModelConfig(
        timeout_s=89, rate_limit_retries=0, transient_retries=0, prompt_version="p5-m1.1",
    )
    capturing = CapturingDecisionPort(ModelPortDecisionAdapter(
        port, config, grounding_variant=DecisionGroundingVariant(grounding_variant),
    ))
    policy = ModelBackedAgentPolicy(capturing, call_timeout_s=90)
    instrumentation = BenchmarkInstrumentation()
    environment = real_dom_environment(instrumentation)
    try:
        result = await compose_target_runtime(
            policy,
            CurrentFactActionEvaluator(),
            ProductionTaskEvaluator(),
        ).run_task(environment, real_adapter_task())
    finally:
        close = getattr(environment, "close", None)
        if close is not None:
            await close()
    request = capturing.request
    user = getattr(request, "serialized_context", "")
    schema = getattr(request, "decision_schema", {})
    schema_bytes = len(json.dumps(
        to_json_compatible(schema), sort_keys=True, separators=(",", ":"),
    ).encode())
    output = ""
    attributed = _attributed(capturing.outcome, user)
    stage = attributed.stage
    if stage == ModelConformanceStage.SUCCESS and result.status != AgentLoopStatus.DONE:
        stage = ModelConformanceStage.RUNTIME_ADMISSION if result.execution_count == 0 else ModelConformanceStage.TASK_EVALUATION
    metadata = policy.last_metadata
    return ConformanceAttempt(
        f"attempt:{grounding_variant}:4:{attempt_number}", "4", grounding_variant,
        stage, stage == ModelConformanceStage.SUCCESS, attributed.failure_kind,
        attributed.decision_variant, len(user.encode()),
        len(getattr(request, "instructions", "").encode()), len(user.encode()), schema_bytes,
        len(user.encode()) + len(getattr(request, "instructions", "").encode()) + schema_bytes,
        _count(user, "action_id"), _count(user, "target_id"), _count(user, "fact_ref"),
        _history(user), metadata.prompt_tokens if metadata else 0,
        metadata.completion_tokens if metadata else 0, metadata.total_tokens if metadata else 0,
        len(output.encode()), f"sha256:{hashlib.sha256(output.encode()).hexdigest()}" if output else "",
        metadata.latency_ms if metadata else 0.0,
    )


def _attributed(outcome, user):
    if isinstance(outcome, ModelFailure):
        return attribute_decision_payload(outcome, "", (), {})
    if not isinstance(outcome, ResolvedModelDecision):
        return attribute_decision_payload("{", "", (), {})
    value = json.loads(user)
    if isinstance(value, dict) and isinstance(value.get("agent_context"), dict):
        value = value["agent_context"]
    options = value.get("actions", {}).get("options", ())
    action_ids = tuple(str(item.get("action_id") or "") for item in options)
    destinations = {
        str(item.get("action_id") or ""): tuple(
            ["", *(str(dest.get("destination_id") or "") for dest in item.get("destinations", {}).get("items", ()))]
        )
        for item in options
    }
    decision = outcome.decision
    if isinstance(decision, Abort):
        return AttributedDecision(ModelConformanceStage.MODEL_ABORT, "model_abort", "abort")
    if isinstance(decision, SelectAction):
        if decision.action_id not in action_ids:
            return AttributedDecision(ModelConformanceStage.ACTION_ID, "hidden_action", "select_action")
        if decision.destination_id not in destinations.get(decision.action_id, ("",)):
            return AttributedDecision(
                ModelConformanceStage.DESTINATION_ID, "hidden_destination", "select_action"
            )
    return AttributedDecision(
        ModelConformanceStage.SUCCESS,
        decision_variant=_decision_variant(decision),
    )


def _decision_variant(decision) -> str:
    return {
        "SelectAction": "select_action",
        "RequestObservation": "request_observation",
        "RequestActionPage": "request_action_page",
        "AskUser": "ask_user",
        "ProposeDone": "propose_done",
        "Wait": "wait",
        "Abort": "abort",
    }.get(type(decision).__name__, "")


def _count(user: str, key: str) -> int:
    return user.count(f'"{key}"')


def _history(user: str) -> int:
    try:
        value = json.loads(user)
        if isinstance(value, dict) and isinstance(value.get("agent_context"), dict):
            value = value["agent_context"]
        return len(value.get("history", {}).get("items", ()))
    except (AttributeError, json.JSONDecodeError):
        return 0

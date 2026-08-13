"""Executable product composition for the configured target model policy."""

from __future__ import annotations

from collections.abc import Mapping

from affordance_runtime.agent.composition import compose_target_runtime
from affordance_runtime.agent.decision_capability import TOOL_ACTION_DECISION_CAPABILITIES
from affordance_runtime.evaluation import ProductionActionEvaluator, ProductionTaskEvaluator
from affordance_runtime.model_policy import model_policy_from_environment
from affordance_runtime.model_policy.grounded_tool_contracts import GROUNDED_TOOLS_PROTOCOL
from affordance_runtime.target_runtime_client import TargetRuntimeClient


def compose_target_client_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
    interaction_protocol: str | None = None,
) -> TargetRuntimeClient:
    """Compose the configured model against the supported product GUI control set."""

    selected_protocol = interaction_protocol or GROUNDED_TOOLS_PROTOCOL
    policy = model_policy_from_environment(
        environment,
        call_timeout_s=call_timeout_s,
        interaction_protocol=selected_protocol,
    )
    return TargetRuntimeClient(compose_target_runtime(
        policy,
        ProductionActionEvaluator(),
        ProductionTaskEvaluator(),
        required_decisions=TOOL_ACTION_DECISION_CAPABILITIES,
    ))

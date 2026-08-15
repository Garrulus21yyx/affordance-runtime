"""Authoritative model-control profile for the current GUI benchmark."""

from affordance_runtime.agent.decision_capability import (
    GROUNDED_ACTION_DECISION_CAPABILITIES,
    DecisionCapability,
)
from affordance_runtime.model.policy.grounded_tool_contracts import GROUNDED_TOOLS_PROTOCOL
from affordance_runtime.model.policy.model_port_bridge import DecisionPerceptionProfile

PRIMARY_BENCHMARK_ACTION_PROTOCOL = GROUNDED_TOOLS_PROTOCOL
PRIMARY_BENCHMARK_PERCEPTION_PROFILE = DecisionPerceptionProfile.STRUCTURE_FIRST
PRIMARY_BENCHMARK_REQUIRED_DECISIONS: frozenset[DecisionCapability] = (
    GROUNDED_ACTION_DECISION_CAPABILITIES
)

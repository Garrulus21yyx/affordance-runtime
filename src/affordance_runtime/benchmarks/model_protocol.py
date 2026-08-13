"""Authoritative model-control profile for the current GUI benchmark."""

from affordance_runtime.agent.decision_capability import (
    TOOL_ACTION_DECISION_CAPABILITIES,
    DecisionCapability,
)
from affordance_runtime.model_policy.grounded_tool_contracts import GROUNDED_TOOLS_PROTOCOL
from affordance_runtime.model_policy.model_port_bridge import DecisionPerceptionProfile

PRIMARY_BENCHMARK_ACTION_PROTOCOL = GROUNDED_TOOLS_PROTOCOL
PRIMARY_BENCHMARK_PERCEPTION_PROFILE = DecisionPerceptionProfile.STRUCTURE_FIRST
PRIMARY_BENCHMARK_REQUIRED_DECISIONS: frozenset[DecisionCapability] = (
    TOOL_ACTION_DECISION_CAPABILITIES
)

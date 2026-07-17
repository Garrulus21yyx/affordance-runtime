"""Runtime state kernel.

The state kernel preserves task constraints and obligations across long GUI
trajectories. It is deliberately separate from planner state so Codex, Claude,
LangGraph, OpenHands, or a local planner can all use the same execution memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from affordance_runtime.contracts import ExecutionReceipt, Observation


@dataclass
class StateKernel:
    task_id: str
    goal: str
    constraints: dict[str, Any] = field(default_factory=dict)
    subgoals: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    hidden_state_hypotheses: list[str] = field(default_factory=list)
    pending_obligations: list[str] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    receipts: list[ExecutionReceipt] = field(default_factory=list)

    def remember_observation(self, observation: Observation) -> None:
        self.observations.append(observation)

    def record_receipt(self, receipt: ExecutionReceipt) -> None:
        self.receipts.append(receipt)
        for value in receipt.evidence.values():
            if isinstance(value, str) and value not in self.evidence:
                self.evidence.append(value)

    def add_obligation(self, obligation: str) -> None:
        if obligation not in self.pending_obligations:
            self.pending_obligations.append(obligation)

    def satisfy_obligation(self, obligation: str) -> None:
        self.pending_obligations = [item for item in self.pending_obligations if item != obligation]

    def current_revision(self) -> str:
        return self.observations[-1].environment_revision if self.observations else ""

    def constraint_summary(self) -> str:
        return "; ".join(f"{key}={value}" for key, value in sorted(self.constraints.items()))


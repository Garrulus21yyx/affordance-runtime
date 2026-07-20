"""Runtime state kernel.

The state kernel preserves task constraints and obligations across long GUI
trajectories. It is deliberately separate from planner state so Codex, Claude,
LangGraph, OpenHands, or a local planner can all use the same execution memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation
from affordance_runtime.recovery import RecoveryIncident
from affordance_runtime.verification import VerificationReport

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "created": {"observing", "aborted"},
    "observing": {"planning", "failed", "aborted"},
    "planning": {"preflight", "waiting_clarification", "done", "failed", "aborted"},
    "waiting_clarification": {"observing", "aborted"},
    "preflight": {"acting", "observing", "recovering", "waiting_approval", "aborted"},
    "waiting_approval": {"preflight", "aborted"},
    "acting": {"verifying", "recovering", "failed"},
    "verifying": {"planning", "observing", "recovering", "done", "failed"},
    "recovering": {"observing", "waiting_approval", "aborted", "failed"},
    "done": set(),
    "failed": set(),
    "aborted": set(),
}


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
    phase: str = "created"
    current_snapshot_id: str = ""
    current_contract: ActionContract | None = None
    latest_verification: VerificationReport | None = None
    step_count: int = 0
    observation_count: int = 0
    replan_count: int = 0
    recovery_count: int = 0
    recovery_incident: RecoveryIncident | None = None
    recovery_diagnostics: dict[str, Any] = field(default_factory=dict)
    effectful_action_count: int = 0
    transitions: list[tuple[str, str]] = field(default_factory=list)
    final_result: dict[str, Any] = field(default_factory=dict)
    planner_history: list[dict[str, Any]] = field(default_factory=list)
    version: int = 0

    def remember_observation(self, observation: Observation) -> None:
        self.observations.append(observation)
        self.observation_count += 1
        self.current_snapshot_id = observation.snapshot_id
        self.version += 1

    def record_receipt(self, receipt: ExecutionReceipt) -> None:
        self.receipts.append(receipt)
        for value in receipt.evidence.values():
            if isinstance(value, str) and value not in self.evidence:
                self.evidence.append(value)
        self.version += 1

    def add_obligation(self, obligation: str) -> None:
        if obligation not in self.pending_obligations:
            self.pending_obligations.append(obligation)
            self.version += 1

    def satisfy_obligation(self, obligation: str) -> None:
        remaining = [item for item in self.pending_obligations if item != obligation]
        if remaining != self.pending_obligations:
            self.pending_obligations = remaining
            self.version += 1

    def record_planner_proposal(self, proposal: dict[str, Any]) -> None:
        self.planner_history.append(proposal)
        self.version += 1

    def current_revision(self) -> str:
        return self.observations[-1].environment_revision if self.observations else ""

    def constraint_summary(self) -> str:
        return "; ".join(f"{key}={value}" for key, value in sorted(self.constraints.items()))

    def transition(self, next_phase: str) -> None:
        if next_phase not in _ALLOWED_TRANSITIONS.get(self.phase, set()):
            raise ValueError(f"invalid runtime transition: {self.phase} -> {next_phase}")
        self.transitions.append((self.phase, next_phase))
        self.phase = next_phase
        self.version += 1

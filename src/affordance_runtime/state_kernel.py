"""Runtime state kernel.

The state kernel preserves task constraints and obligations across long GUI
trajectories. It is deliberately separate from planner state so Codex, Claude,
LangGraph, OpenHands, or a local planner can all use the same execution memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from affordance_runtime.active_perception import (
    EvidenceGap,
    PerceptionResolution,
    ProbePlan,
    ProbeReceipt,
)
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation
from affordance_runtime.failure_envelope import FailureEnvelope
from affordance_runtime.recovery import RecoveryIncident
from affordance_runtime.recovery_commands import RecoveryDelta, RecoveryPlan, RecoveryReceipt
from affordance_runtime.recovery_coordinator import RecoveryHistoryItem
from affordance_runtime.task_planning import PlanProgress, TaskPlan
from affordance_runtime.verification import VerificationReport

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "created": {"observing", "aborted"},
    "observing": {"planning", "recovering", "failed", "aborted"},
    "planning": {"observing", "preflight", "recovering", "waiting_clarification", "deferred", "done", "failed", "aborted"},
    "waiting_clarification": {"observing", "aborted"},
    "preflight": {"acting", "observing", "recovering", "waiting_approval", "aborted"},
    "waiting_approval": {"preflight", "aborted"},
    "acting": {"verifying", "recovering", "failed"},
    "verifying": {"planning", "observing", "recovering", "done", "failed"},
    "recovering": {
        "observing",
        "planning",
        "waiting_approval",
        "waiting_clarification",
        "deferred",
        "aborted",
        "failed",
    },
    "done": set(),
    "failed": set(),
    "aborted": set(),
    "deferred": set(),
}


class ProgressGuardReason(StrEnum):
    EFFECT_ALREADY_SATISFIED = "effect_already_satisfied"
    NO_PROGRESS_REPEAT = "no_progress_repeat"


@dataclass(frozen=True)
class ActionProgressRecord:
    """Minimal verified outcome used to block duplicate semantic actions."""

    signature: str
    post_environment_revision: str
    verification_passed: bool
    effect_satisfied: bool
    post_page_revision: str = ""


@dataclass
class TaskSkillRunState:
    """Authoritative verified progress for one accepted TaskSkill activation."""

    skill_id: str
    version: str
    bindings: dict[str, Any] = field(default_factory=dict)
    next_step_index: int = 0
    completed_step_ids: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    active_step_id: str = ""
    fallthrough_reason: str = ""

    @property
    def active(self) -> bool:
        return not self.fallthrough_reason


@dataclass
class StateKernel:
    task_id: str
    goal: str
    constraints: dict[str, Any] = field(default_factory=dict)
    subgoals: list[str] = field(default_factory=list)
    task_plan: TaskPlan | None = None
    plan_progress: PlanProgress | None = None
    evidence: list[str] = field(default_factory=list)
    hidden_state_hypotheses: list[str] = field(default_factory=list)
    disproved_assumptions: list[str] = field(default_factory=list)
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
    active_perception_count: int = 0
    evidence_gaps: tuple[EvidenceGap, ...] = ()
    active_probe_plan: ProbePlan | None = None
    probe_receipts: list[ProbeReceipt] = field(default_factory=list)
    perception_resolution: PerceptionResolution | None = None
    attempted_probe_fingerprints: set[str] = field(default_factory=set)
    recovery_incident: RecoveryIncident | None = None
    current_failure: FailureEnvelope | None = None
    current_recovery_plan: RecoveryPlan | None = None
    recovery_receipts: list[RecoveryReceipt] = field(default_factory=list)
    recovery_deltas: list[RecoveryDelta] = field(default_factory=list)
    recovery_history: list[RecoveryHistoryItem] = field(default_factory=list)
    attempted_recovery_strategy_ids: set[str] = field(default_factory=set)
    recovery_diagnostics: dict[str, Any] = field(default_factory=dict)
    effectful_action_count: int = 0
    transitions: list[tuple[str, str]] = field(default_factory=list)
    final_result: dict[str, Any] = field(default_factory=dict)
    planner_history: list[dict[str, Any]] = field(default_factory=list)
    action_progress: list[ActionProgressRecord] = field(default_factory=list)
    progress_guard_events: list[dict[str, str]] = field(default_factory=list)
    excluded_grounding_candidates: dict[str, list[str]] = field(default_factory=dict)
    grounding_fallback_lineage: dict[str, dict[str, str]] = field(default_factory=dict)
    task_skill: TaskSkillRunState | None = None
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

    def record_disproved_assumption(self, assumption: str) -> None:
        value = assumption.strip()
        if value and value not in self.disproved_assumptions:
            self.disproved_assumptions.append(value)
            self.version += 1

    def satisfy_obligation(self, obligation: str) -> None:
        remaining = [item for item in self.pending_obligations if item != obligation]
        if remaining != self.pending_obligations:
            self.pending_obligations = remaining
            self.version += 1

    def record_planner_proposal(self, proposal: dict[str, Any]) -> None:
        self.planner_history.append(proposal)
        self.version += 1

    def activate_task_skill(
        self,
        skill_id: str,
        version: str,
        bindings: dict[str, Any],
    ) -> TaskSkillRunState:
        if self.task_skill is not None and self.task_skill.active:
            raise ValueError("another TaskSkill is already active")
        self.task_skill = TaskSkillRunState(skill_id, version, dict(bindings))
        self.version += 1
        return self.task_skill

    def update_task_skill_bindings(self, bindings: dict[str, Any]) -> None:
        if self.task_skill is None:
            raise ValueError("no TaskSkill is active")
        changed = False
        for name, value in bindings.items():
            if self.task_skill.bindings.get(name) != value:
                self.task_skill.bindings[name] = value
                changed = True
        if changed:
            self.version += 1

    def expose_task_skill_step(self, step_id: str) -> None:
        if self.task_skill is None or not self.task_skill.active:
            raise ValueError("no active TaskSkill can expose a step")
        if self.task_skill.active_step_id != step_id:
            self.task_skill.active_step_id = step_id
            self.version += 1

    def checkpoint_task_skill_step(self, step_id: str, evidence: list[str]) -> None:
        if self.task_skill is None or self.task_skill.active_step_id != step_id:
            raise ValueError("TaskSkill checkpoint does not match the active step")
        if step_id not in self.task_skill.completed_step_ids:
            self.task_skill.completed_step_ids.append(step_id)
        self.task_skill.evidence.extend(item for item in evidence if item not in self.task_skill.evidence)
        self.task_skill.next_step_index += 1
        self.task_skill.active_step_id = ""
        self.version += 1

    def fall_through_task_skill(self, reason: str) -> None:
        if self.task_skill is None:
            return
        self.task_skill.fallthrough_reason = reason
        self.task_skill.active_step_id = ""
        self.version += 1

    def record_action_progress(
        self,
        signature: str,
        post_environment_revision: str,
        *,
        verification_passed: bool,
        effect_satisfied: bool | None = None,
        post_page_revision: str = "",
    ) -> None:
        self.action_progress.append(
            ActionProgressRecord(
                signature=signature,
                post_environment_revision=post_environment_revision,
                verification_passed=verification_passed,
                effect_satisfied=(verification_passed if effect_satisfied is None else effect_satisfied),
                post_page_revision=post_page_revision,
            )
        )
        self.version += 1

    def check_progress_guard(self, signature: str) -> ProgressGuardReason | None:
        if not self.action_progress:
            return None
        previous = next(
            (item for item in reversed(self.action_progress) if item.signature == signature),
            None,
        )
        if previous is None:
            return None
        same_page = (
            previous.post_page_revision == self.current_page_revision()
            if previous.post_page_revision and self.current_page_revision()
            else previous.post_environment_revision == self.current_revision()
        )
        if previous.effect_satisfied and same_page:
            return ProgressGuardReason.EFFECT_ALREADY_SATISFIED
        if not previous.verification_passed and previous.post_environment_revision == self.current_revision():
            return ProgressGuardReason.NO_PROGRESS_REPEAT
        return None

    def record_progress_guard(self, reason: ProgressGuardReason, signature: str) -> None:
        self.progress_guard_events.append(
            {
                "reason": reason.value,
                "signature": signature,
                "environment_revision": self.current_revision(),
            }
        )
        self.version += 1

    def record_grounding_reroute(
        self,
        contract: ActionContract,
        reason: str,
        *,
        exclude_candidate: bool = True,
    ) -> None:
        """Retain immutable recovery lineage and optionally exclude a failed route."""

        candidate = contract.grounding_candidate
        if candidate is None:
            return
        if exclude_candidate:
            excluded = self.excluded_grounding_candidates.setdefault(candidate.semantic_target_id, [])
            if candidate.candidate_id not in excluded:
                excluded.append(candidate.candidate_id)
        self.grounding_fallback_lineage[candidate.semantic_target_id] = {
            "supersedes_contract_id": contract.id,
            "source_contract_id": contract.source_contract_id or contract.id,
            "fallback_reason": reason,
            "failed_source": candidate.source.value,
        }
        self.version += 1

    def complete_grounding_recovery(self, semantic_target_id: str) -> None:
        """Release incident-local exclusions after a replacement contract verifies."""

        changed = False
        if self.excluded_grounding_candidates.pop(semantic_target_id, None) is not None:
            changed = True
        if self.grounding_fallback_lineage.pop(semantic_target_id, None) is not None:
            changed = True
        if changed:
            self.version += 1

    def excluded_candidates_for(self, semantic_target_id: str) -> frozenset[str]:
        return frozenset(self.excluded_grounding_candidates.get(semantic_target_id, ()))

    def fallback_lineage_for(self, semantic_target_id: str) -> dict[str, str]:
        return dict(self.grounding_fallback_lineage.get(semantic_target_id, {}))

    def install_task_plan(self, plan: TaskPlan) -> None:
        """Attach a validated immutable plan without advancing any subgoal."""

        if plan.task_id != self.task_id:
            raise ValueError("TaskPlan task_id does not match run state")
        self.task_plan = plan
        self.plan_progress = PlanProgress()
        self.subgoals = [item.objective for item in plan.subgoals]
        self.version += 1

    def active_subgoal(self) -> str:
        if self.task_plan is None or self.plan_progress is None:
            return self.subgoals[-1] if self.subgoals else ""
        identifier = self.plan_progress.active_subgoal_id
        return next((item.objective for item in self.task_plan.subgoals if item.subgoal_id == identifier), "")

    def activate_next_subgoal(self) -> str:
        if self.task_plan is None or self.plan_progress is None:
            return self.subgoals[-1] if self.subgoals else ""
        previous = self.plan_progress.active_subgoal_id
        identifier = self.plan_progress.activate_next(self.task_plan)
        if identifier != previous:
            self.version += 1
        return next((item.objective for item in self.task_plan.subgoals if item.subgoal_id == identifier), "")

    def complete_subgoal(self, subgoal_id: str, evidence: tuple[str, ...]) -> None:
        if self.task_plan is None or self.plan_progress is None:
            raise ValueError("cannot complete a subgoal without a TaskPlan")
        if subgoal_id not in {item.subgoal_id for item in self.task_plan.subgoals}:
            raise ValueError("unknown TaskPlan subgoal")
        self.plan_progress.complete(subgoal_id, evidence)
        for item in evidence:
            if item not in self.evidence:
                self.evidence.append(item)
        self.version += 1

    def record_subgoal_action(self) -> None:
        if self.task_plan is None or self.plan_progress is None:
            return
        subgoal_id = self.plan_progress.active_subgoal_id
        if subgoal_id:
            self.plan_progress.record_action(subgoal_id)
            self.version += 1

    def replace_task_plan(self, plan: TaskPlan) -> None:
        """Replace only unfinished structure while preserving verified outcomes."""

        if self.task_plan is None or self.plan_progress is None:
            raise ValueError("cannot replace a missing TaskPlan")
        if plan.task_id != self.task_id:
            raise ValueError("TaskPlan task_id does not match run state")
        if plan.plan_version != self.task_plan.plan_version + 1:
            raise ValueError("replanned TaskPlan version must increase by one")
        if plan.supersedes_plan_id != self.task_plan.plan_id:
            raise ValueError("replanned TaskPlan must supersede the active plan")
        if plan.plan_id == self.task_plan.plan_id:
            raise ValueError("replanned TaskPlan requires a new plan_id")
        new_ids = {item.subgoal_id for item in plan.subgoals}
        completed = set(self.plan_progress.completed_subgoal_ids)
        if not completed.issubset(new_ids):
            raise ValueError("replanned TaskPlan must preserve verified subgoals")
        previous_by_id = {item.subgoal_id: item for item in self.task_plan.subgoals}
        replacement_by_id = {item.subgoal_id: item for item in plan.subgoals}
        if any(replacement_by_id[subgoal_id] != previous_by_id[subgoal_id] for subgoal_id in completed):
            raise ValueError("replanned TaskPlan cannot redefine a verified subgoal")
        self.task_plan = plan
        self.plan_progress = PlanProgress(
            completed_subgoal_ids=list(self.plan_progress.completed_subgoal_ids),
            evidence_by_subgoal={key: list(value) for key, value in self.plan_progress.evidence_by_subgoal.items()},
            task_replan_count=self.plan_progress.task_replan_count + 1,
        )
        self.subgoals = [item.objective for item in plan.subgoals]
        self.version += 1

    def current_revision(self) -> str:
        return self.observations[-1].environment_revision if self.observations else ""

    def current_page_revision(self) -> str:
        return self.observations[-1].page_revision if self.observations else ""

    def constraint_summary(self) -> str:
        return "; ".join(f"{key}={value}" for key, value in sorted(self.constraints.items()))

    def transition(self, next_phase: str) -> None:
        if next_phase not in _ALLOWED_TRANSITIONS.get(self.phase, set()):
            raise ValueError(f"invalid runtime transition: {self.phase} -> {next_phase}")
        self.transitions.append((self.phase, next_phase))
        self.phase = next_phase
        self.version += 1

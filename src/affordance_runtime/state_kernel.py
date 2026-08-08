"""Current-state kernel; complete history belongs to Trace and ArtifactStore."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, NamedTuple

from affordance_runtime.active_perception import EvidenceGap, PerceptionResolution, ProbePlan, ProbeReceipt
from affordance_runtime.contracts import ActionContract, ExecutionReceipt
from affordance_runtime.failure_envelope import FailureEnvelope
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.observation_store import ObservationCommit, ObservationRef
from affordance_runtime.recovery_protocol import RecoveryDecision, RecoveryOutcome
from affordance_runtime.simplified_runtime_contracts import (
    EffectSettlement,
    ExecutionAttempt,
    UncertainExternalEffect,
)
from affordance_runtime.task_plan_contracts import TaskPlan
from affordance_runtime.task_plan_progress import TaskProgress
from affordance_runtime.verification.mechanical import VerificationReport

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "created": {"observing", "aborted"},
    "observing": {"planning", "recovering", "done", "failed", "aborted"},
    "planning": {
        "observing",
        "preflight",
        "recovering",
        "waiting_approval",
        "waiting_clarification",
        "deferred",
        "done",
        "failed",
        "aborted",
    },
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
class ActionKey:
    action_kind: str
    target_id: str
    parameter_digest: str

    def __post_init__(self) -> None:
        if not all((self.action_kind, self.target_id, self.parameter_digest)):
            raise ValueError("action key fields are required")

    @classmethod
    def from_signature(cls, signature: str) -> ActionKey:
        try:
            payload = json.loads(signature)
        except json.JSONDecodeError as exc:
            raise ValueError("action progress signature must be canonical JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("action progress signature must be a JSON object")
        action_kind, target_id = str(payload.get("action_kind") or ""), str(payload.get("target") or "")
        parameters = payload.get("parameters", {})
        if not action_kind or not target_id or not isinstance(parameters, dict):
            raise ValueError("action progress signature must include action_kind, target, and parameters")
        digest_payload: dict[str, object] = {"parameters": parameters}
        if payload.get("destination"):
            digest_payload["destination"] = str(payload["destination"])
        if payload.get("subgoal"):
            digest_payload["subgoal"] = str(payload["subgoal"])
        canonical = json.dumps(
            to_json_compatible(freeze_json(digest_payload)), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        parameter_digest = hashlib.sha256(canonical.encode()).hexdigest()
        return cls(action_kind, target_id, f"sha256:{parameter_digest}")


class RecentActionOutcomeRecord(NamedTuple):
    key: ActionKey
    post_environment_revision: str
    verification_passed: bool
    effect_satisfied: bool
    post_page_revision: str
    attempt_id: str


@dataclass
class RecentActionOutcomeIndex:
    capacity: int = 40
    records: list[RecentActionOutcomeRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ValueError("recent action outcome capacity must be positive")
        if len(self.records) > self.capacity:
            self.records = self.records[-self.capacity :]

    def record(
        self,
        key: ActionKey,
        post_environment_revision: str,
        *,
        verification_passed: bool,
        effect_satisfied: bool,
        post_page_revision: str = "",
        attempt_id: str = "",
    ) -> None:
        self.records.append(
            RecentActionOutcomeRecord(
                key,
                post_environment_revision,
                verification_passed,
                effect_satisfied,
                post_page_revision,
                attempt_id,
            )
        )
        if len(self.records) > self.capacity:
            del self.records[: len(self.records) - self.capacity]

    def latest(self, key: ActionKey) -> RecentActionOutcomeRecord | None:
        return next((item for item in reversed(self.records) if item.key == key), None)


@dataclass
class StateKernel:
    task_id: str
    goal: str
    constraints: dict[str, Any] = field(default_factory=dict)
    task_plan: TaskPlan | None = None
    task_progress: TaskProgress | None = None
    current_observation_ref: ObservationRef | None = None
    current_observation_environment_revision: str = ""
    current_observation_page_revision: str = ""
    last_receipt: ExecutionReceipt | None = None
    last_receipt_attempt_id: str = ""
    current_disproved_assumption: str = ""
    phase: str = "created"
    current_snapshot_id: str = ""
    current_contract: ActionContract | None = None
    current_execution_attempt: ExecutionAttempt | None = None
    uncertain_external_effects: tuple[UncertainExternalEffect, ...] = ()
    latest_verification: VerificationReport | None = None
    latest_effect_settlement: EffectSettlement | None = None
    step_count: int = 0
    observation_count: int = 0
    replan_count: int = 0
    recovery_count: int = 0
    active_perception_count: int = 0
    evidence_gaps: tuple[EvidenceGap, ...] = ()
    active_probe_plan: ProbePlan | None = None
    latest_probe_receipt: ProbeReceipt | None = None
    perception_resolution: PerceptionResolution | None = None
    attempted_probe_fingerprints: set[str] = field(default_factory=set)
    current_failure: FailureEnvelope | None = None
    current_recovery_decision: RecoveryDecision | None = None
    current_recovery_outcome: RecoveryOutcome | None = None
    attempted_recovery_strategy_ids: set[str] = field(default_factory=set)
    effectful_action_count: int = 0
    final_result: dict[str, Any] = field(default_factory=dict)
    latest_planner_proposal: dict[str, Any] = field(default_factory=dict)
    recent_action_outcomes: RecentActionOutcomeIndex = field(default_factory=RecentActionOutcomeIndex)
    latest_progress_guard: dict[str, str] | None = None
    current_excluded_candidates: dict[str, set[str]] = field(default_factory=dict)
    current_grounding_fallback: dict[str, dict[str, str]] = field(default_factory=dict)
    version: int = 0

    def remember_observation_commit(self, observation: ObservationCommit) -> None:
        self.current_observation_ref = observation.ref
        self.current_observation_environment_revision = observation.environment_revision
        self.current_observation_page_revision = observation.page_revision
        self.observation_count += 1
        self.current_snapshot_id = observation.ref.epoch_id
        self.version += 1

    def record_receipt(self, receipt: ExecutionReceipt, *, attempt_id: str = "") -> None:
        self.last_receipt = receipt
        self.last_receipt_attempt_id = attempt_id or (
            self.current_execution_attempt.attempt_id
            if self.current_execution_attempt is not None
            else ""
        )
        self.version += 1

    def record_disproved_assumption(self, assumption: str) -> None:
        value = assumption.strip()
        if value and value != self.current_disproved_assumption:
            self.current_disproved_assumption = value
            self.version += 1

    def record_planner_proposal(self, proposal: dict[str, Any]) -> None:
        self.latest_planner_proposal = proposal
        self.version += 1

    def record_action_progress(
        self,
        signature: str,
        post_environment_revision: str,
        *,
        verification_passed: bool,
        effect_satisfied: bool | None = None,
        post_page_revision: str = "",
        attempt_id: str = "",
    ) -> None:
        self.recent_action_outcomes.record(
            ActionKey.from_signature(signature),
            post_environment_revision,
            verification_passed=verification_passed,
            effect_satisfied=(verification_passed if effect_satisfied is None else effect_satisfied),
            post_page_revision=post_page_revision,
            attempt_id=attempt_id,
        )
        self.version += 1

    def check_progress_guard(self, signature: str) -> ProgressGuardReason | None:
        previous = self.recent_action_outcomes.latest(ActionKey.from_signature(signature))
        if previous is None:
            return None
        same_page = (
            previous.post_page_revision == self.current_page_revision()
            if previous.post_page_revision and self.current_page_revision()
            else previous.post_environment_revision == self.current_revision()
        )
        if previous.effect_satisfied and same_page:
            return ProgressGuardReason.EFFECT_ALREADY_SATISFIED
        verified_absence = bool(
            self.latest_effect_settlement
            and self.latest_effect_settlement.status.value == "not_occurred"
            and previous.attempt_id
            and self.latest_effect_settlement.attempt_id == previous.attempt_id
        )
        if (
            not previous.verification_passed
            and previous.post_environment_revision == self.current_revision()
            and not verified_absence
        ):
            return ProgressGuardReason.NO_PROGRESS_REPEAT
        return None

    def record_progress_guard(self, reason: ProgressGuardReason, signature: str) -> None:
        self.latest_progress_guard = {
            "reason": reason.value,
            "signature": signature,
            "environment_revision": self.current_revision(),
        }
        self.version += 1

    def record_grounding_reroute(
        self, contract: ActionContract, reason: str, *, exclude_candidate: bool = True
    ) -> None:
        candidate = contract.grounding_candidate
        if candidate is None:
            return
        if exclude_candidate:
            excluded = self.current_excluded_candidates.setdefault(candidate.semantic_target_id, set())
            if candidate.candidate_id not in excluded:
                excluded.add(candidate.candidate_id)
        self.current_grounding_fallback[candidate.semantic_target_id] = {
            "supersedes_contract_id": contract.id,
            "source_contract_id": contract.source_contract_id or contract.id,
            "fallback_reason": reason,
            "failed_source": candidate.source.value,
        }
        self.version += 1

    def complete_grounding_recovery(self, semantic_target_id: str) -> None:
        changed = False
        changed |= self.current_excluded_candidates.pop(semantic_target_id, None) is not None
        changed |= self.current_grounding_fallback.pop(semantic_target_id, None) is not None
        if changed:
            self.version += 1

    def excluded_candidates_for(self, semantic_target_id: str) -> frozenset[str]:
        return frozenset(self.current_excluded_candidates.get(semantic_target_id, ()))

    def fallback_lineage_for(self, semantic_target_id: str) -> dict[str, str]:
        return dict(self.current_grounding_fallback.get(semantic_target_id, {}))

    def install_task_plan(self, plan: TaskPlan) -> None:
        if plan.task_id != self.task_id:
            raise ValueError("TaskPlan task_id does not match run state")
        self.task_plan = plan
        self.task_progress = TaskProgress()
        self.version += 1

    def active_subgoal(self) -> str:
        if self.task_plan is None or self.task_progress is None:
            return ""
        identifier = self.task_progress.active_step_id
        return next((item.objective for item in self.task_plan.steps if item.step_id == identifier), "")

    def activate_next_step(self) -> str:
        if self.task_plan is None or self.task_progress is None:
            return ""
        previous = self.task_progress.active_step_id
        identifier = self.task_progress.activate_next(self.task_plan)
        if identifier != previous:
            self.version += 1
        return next((item.objective for item in self.task_plan.steps if item.step_id == identifier), "")

    def complete_step(
        self,
        step_id: str,
        evidence: tuple[str, ...],
        criterion_ids: tuple[str, ...] = (),
    ) -> None:
        if self.task_plan is None or self.task_progress is None:
            raise ValueError("cannot complete a step without a TaskPlan")
        self.task_progress.complete(
            plan=self.task_plan,
            step_id=step_id,
            criterion_ids=criterion_ids,
            evidence_refs=evidence,
            state_version=self.version,
        )
        self.version += 1

    def record_step_action(self) -> None:
        if self.task_plan is None or self.task_progress is None:
            return
        step_id = self.task_progress.active_step_id
        if step_id:
            self.task_progress.record_action(step_id)
            self.version += 1

    def replace_task_plan(self, plan: TaskPlan) -> None:
        if self.task_plan is None or self.task_progress is None:
            raise ValueError("cannot replace a missing TaskPlan")
        if plan.task_id != self.task_id:
            raise ValueError("TaskPlan task_id does not match run state")
        if plan.plan_version != self.task_plan.plan_version + 1:
            raise ValueError("replanned TaskPlan version must increase by one")
        if plan.supersedes_plan_id != self.task_plan.plan_id:
            raise ValueError("replanned TaskPlan must supersede the active plan")
        if plan.plan_id == self.task_plan.plan_id:
            raise ValueError("replanned TaskPlan requires a new plan_id")
        self.task_plan = plan
        self.task_progress.active_step_id = ""
        self.task_progress.failed_step_ids = []
        self.task_progress.action_count_by_step = {}
        self.task_progress.replan_count += 1
        self.version += 1

    def current_revision(self) -> str:
        return self.current_observation_environment_revision

    def current_page_revision(self) -> str:
        return self.current_observation_page_revision

    def constraint_summary(self) -> str:
        return "; ".join(f"{key}={value}" for key, value in sorted(self.constraints.items()))

    def transition(self, next_phase: str) -> None:
        if next_phase not in _ALLOWED_TRANSITIONS.get(self.phase, set()):
            raise ValueError(f"invalid runtime transition: {self.phase} -> {next_phase}")
        self.phase = next_phase
        self.version += 1

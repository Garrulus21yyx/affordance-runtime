"""Thin long-horizon mission contracts around the single GUI loop."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.working_facts import WorkingFact
from affordance_runtime.evaluation.evidence_records import EvidenceRecord
from affordance_runtime.immutable import freeze_json
from affordance_runtime.model.policy.contracts import ModelInvocationResult
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation

_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ID = re.compile(r"^[a-z][a-z0-9_:-]{0,95}$")
_MAX_TEXT = 500
_MAX_COLLECTION = 32
_MAX_AUDIT_EVIDENCE_RECORDS = 128


class ManagerRoute(StrEnum):
    EXECUTE_SUBTASK = "execute_subtask"
    ASK_USER = "ask_user"
    BLOCKED = "blocked"
    REQUEST_FINAL_AUDIT = "request_final_audit"


class AuditDeltaStatus(StrEnum):
    AUDITED_SATISFIED = "audited_satisfied"
    AUDITED_UNSATISFIED = "audited_unsatisfied"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"


class SupervisorPhase(StrEnum):
    MANAGER = "manager"
    EXECUTING = "executing"
    AUDITING = "auditing"
    FINALIZING = "finalizing"
    WAITING_USER = "waiting_user"
    TERMINAL = "terminal"


class MissionOutcome(StrEnum):
    RUNNING = "running"
    NEEDS_USER_INPUT = "needs_user_input"
    BLOCKED = "blocked"
    MANAGER_FAILURE = "manager_failure"
    AUDITOR_FAILURE = "auditor_failure"
    BOUNDARY_REJECTED = "boundary_rejected"
    EVIDENCE_GAP = "evidence_gap"
    FINAL_AUDIT_NOT_READY = "final_audit_not_ready"
    FINALIZED = "finalized"
    CANCELLED = "cancelled"
    TASK_COMPLETE = "task_complete"
    TASK_BLOCKED = "task_blocked"
    ROUND_BUDGET_EXHAUSTED = "round_budget_exhausted"


class EpisodeMonitorEvent(StrEnum):
    STATE_CHANGED = "state_changed"
    NO_OBSERVED_CHANGE = "no_observed_change"
    REPEATED_ACTION = "repeated_action"
    OSCILLATION = "oscillation"
    FORMAL_CRITERION_CHANGED = "formal_criterion_changed"
    PROVIDER_FAILURE = "provider_failure"
    ENVIRONMENT_FAILURE = "environment_failure"
    CAPABILITY_GAP = "capability_gap"


class EpisodeMonitorRecommendation(StrEnum):
    CONTINUE = "continue"
    YIELD = "yield"


@dataclass(frozen=True)
class SubtaskContract:
    objective: str
    done_when: str
    constraints: tuple[str, ...] = ()
    relevant_fact_keys: tuple[str, ...] = ()
    candidate_output_keys: tuple[str, ...] = ()
    episode_turn_budget: int = 10
    related_audit_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _bounded_text(self.objective, "subtask objective")
        _bounded_text(self.done_when, "subtask done_when")
        object.__setattr__(self, "constraints", _bounded_unique(self.constraints, "constraints"))
        object.__setattr__(self, "relevant_fact_keys", _keys(self.relevant_fact_keys, "relevant_fact_keys"))
        object.__setattr__(
            self,
            "candidate_output_keys",
            _keys(self.candidate_output_keys, "candidate_output_keys"),
        )
        object.__setattr__(self, "related_audit_ids", _ids(self.related_audit_ids, "related_audit_ids"))
        if type(self.episode_turn_budget) is not int or not 1 <= self.episode_turn_budget <= 100:
            raise ValueError("subtask episode budget must be within [1, 100]")


@dataclass(frozen=True)
class ManagerDecision:
    route: ManagerRoute
    subtask: SubtaskContract | None = None
    question: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.route, ManagerRoute):
            raise TypeError("manager route must be typed")
        has_subtask = self.subtask is not None
        if self.route is ManagerRoute.EXECUTE_SUBTASK:
            if not has_subtask or self.question:
                raise ValueError("execute_subtask requires exactly one SubtaskContract")
        elif has_subtask:
            raise ValueError("only execute_subtask can carry a SubtaskContract")
        if self.route is ManagerRoute.ASK_USER:
            _bounded_text(self.question, "manager question", limit=1_000)
        elif self.question:
            raise ValueError("only ask_user can carry a question")
        if self.reason:
            _bounded_text(self.reason, "manager reason")


@dataclass(frozen=True)
class AuditedOutcome:
    audit_id: str
    status: AuditDeltaStatus
    evidence_refs: tuple[str, ...]
    summary: str

    def __post_init__(self) -> None:
        _require_id(self.audit_id, "audit_id")
        if self.status not in {AuditDeltaStatus.AUDITED_SATISFIED, AuditDeltaStatus.AUDITED_UNSATISFIED}:
            raise ValueError("MissionState stores only audited resolved outcomes")
        object.__setattr__(self, "evidence_refs", _bounded_unique(self.evidence_refs, "evidence_refs"))
        _bounded_text(self.summary, "outcome summary")


@dataclass(frozen=True)
class AcceptedFact:
    key: str
    record: EvidenceRecord
    purpose: str
    accepted_at_version: int

    def __post_init__(self) -> None:
        _require_key(self.key, "fact key")
        if not isinstance(self.record, EvidenceRecord):
            raise TypeError("accepted fact requires an EvidenceRecord")
        _bounded_text(self.purpose, "fact purpose")
        if self.accepted_at_version < 0:
            raise ValueError("accepted fact version cannot be negative")

    def as_working_fact(self, step_index: int = 0) -> WorkingFact:
        return WorkingFact(self.key, self.record, step_index, self.purpose)


@dataclass(frozen=True)
class MissionState:
    version: int = 0
    audited_outcomes: tuple[AuditedOutcome, ...] = ()
    accepted_facts: tuple[AcceptedFact, ...] = ()
    audit_lineage: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.version < 0:
            raise ValueError("mission version cannot be negative")
        object.__setattr__(self, "audited_outcomes", tuple(self.audited_outcomes))
        object.__setattr__(self, "accepted_facts", tuple(self.accepted_facts))
        object.__setattr__(self, "audit_lineage", _ids(self.audit_lineage, "audit_lineage"))
        if any(not isinstance(item, AuditedOutcome) for item in self.audited_outcomes):
            raise TypeError("mission audited outcomes must be typed")
        if any(not isinstance(item, AcceptedFact) for item in self.accepted_facts):
            raise TypeError("mission accepted facts must be typed")
        if len({item.audit_id for item in self.audited_outcomes}) != len(self.audited_outcomes):
            raise ValueError("audited outcome IDs cannot repeat")
        if len({item.key for item in self.accepted_facts}) != len(self.accepted_facts):
            raise ValueError("accepted fact keys cannot repeat")

    @classmethod
    def empty(cls) -> MissionState:
        return cls()

    def carry_working_facts(self, relevant_keys: tuple[str, ...] = ()) -> tuple[WorkingFact, ...]:
        selected = set(_keys(relevant_keys, "relevant_fact_keys"))
        return tuple(
            item.as_working_fact()
            for item in self.accepted_facts
            if item.key in selected
        )


@dataclass(frozen=True)
class SupervisorState:
    phase: SupervisorPhase = SupervisorPhase.MANAGER
    active_subtask: SubtaskContract | None = None
    last_typed_episode_exit: str = ""
    last_ref: str = ""
    mission_round_budget: int = 8
    final_response_delivered: bool = False
    opened_environment_ref: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.phase, SupervisorPhase):
            raise TypeError("supervisor phase must be typed")
        if self.active_subtask is not None and not isinstance(self.active_subtask, SubtaskContract):
            raise TypeError("active subtask must be typed")
        if not 0 <= self.mission_round_budget <= 100:
            raise ValueError("mission round budget is outside bounds")
        for value in (self.last_typed_episode_exit, self.last_ref, self.opened_environment_ref):
            if value and len(value) > 200:
                raise ValueError("supervisor transient identity exceeds bounds")
        if type(self.final_response_delivered) is not bool:
            raise TypeError("final response latch must be boolean")


@dataclass(frozen=True)
class ManagerRoleRequest:
    original_task: TaskGoal
    mission_state: MissionState
    last_typed_exit: str = ""
    last_audit_or_failure_ref: str = ""
    remaining_rounds: int = 0


@dataclass(frozen=True)
class AuditBundle:
    observation_id: str
    source_observation_ids: tuple[str, ...]
    evidence_records: tuple[EvidenceRecord, ...]
    source_coverages: Mapping[str, str] | None = None
    total_evidence_count: int = 0

    @classmethod
    def from_world(cls, world: WorldObservation) -> AuditBundle:
        from affordance_runtime.evaluation.evidence import WorldEvidenceIndex

        index = WorldEvidenceIndex.from_observation(world)
        records = index.records[:_MAX_AUDIT_EVIDENCE_RECORDS]
        return cls(
            world.observation_id,
            tuple(source.observation_id for source in world.sources),
            records,
            {source.observation_id: source.coverage.value for source in world.sources},
            len(index.records),
        )

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("audit bundle requires observation identity")
        object.__setattr__(self, "source_observation_ids", _bounded_unique(self.source_observation_ids, "sources"))
        object.__setattr__(self, "evidence_records", tuple(self.evidence_records))
        object.__setattr__(self, "source_coverages", dict(self.source_coverages or {}))
        if len(self.evidence_records) > _MAX_AUDIT_EVIDENCE_RECORDS:
            raise ValueError("audit bundle evidence records exceed bound")
        if self.total_evidence_count and self.total_evidence_count < len(self.evidence_records):
            raise ValueError("audit bundle total cannot be smaller than retained evidence")
        if any(not isinstance(item, EvidenceRecord) for item in self.evidence_records):
            raise TypeError("audit bundle evidence must be typed")

    def resolve(self, evidence_ref: str) -> EvidenceRecord | None:
        return next((item for item in self.evidence_records if item.evidence_ref == evidence_ref), None)

    @property
    def truncated(self) -> bool:
        return bool(self.total_evidence_count and self.total_evidence_count > len(self.evidence_records))


@dataclass(frozen=True)
class AuditorRoleRequest:
    original_task: TaskGoal
    subtask: SubtaskContract
    pre_mission_state: MissionState
    after_world: WorldObservation
    working_facts: tuple[WorkingFact, ...]
    yield_reason: str
    episode_history: tuple[AgentTurnView, ...]
    audit_bundle: AuditBundle
    related_audit_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutcomeProposal:
    audit_id: str
    status: AuditDeltaStatus
    evidence_refs: tuple[str, ...]
    summary: str

    def __post_init__(self) -> None:
        _require_id(self.audit_id, "audit_id")
        if self.status not in {AuditDeltaStatus.AUDITED_SATISFIED, AuditDeltaStatus.AUDITED_UNSATISFIED}:
            raise ValueError("outcome proposals must be resolved audited statuses")
        object.__setattr__(self, "evidence_refs", _bounded_unique(self.evidence_refs, "evidence_refs"))
        _bounded_text(self.summary, "outcome proposal summary")


@dataclass(frozen=True)
class PromoteFactProposal:
    key: str
    evidence_ref: str
    value: object
    purpose: str

    def __post_init__(self) -> None:
        _require_key(self.key, "fact key")
        _bounded_text(self.evidence_ref, "evidence_ref")
        object.__setattr__(self, "value", freeze_json(self.value))
        _bounded_text(self.purpose, "fact purpose")


@dataclass(frozen=True)
class AuditDelta:
    status: AuditDeltaStatus
    base_mission_version: int
    completed_outcomes: tuple[OutcomeProposal, ...] = ()
    promote_facts: tuple[PromoteFactProposal, ...] = ()
    invalidate_fact_keys: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    recovery_hint: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, AuditDeltaStatus):
            raise TypeError("audit delta status must be typed")
        if self.base_mission_version < 0:
            raise ValueError("audit delta base version cannot be negative")
        object.__setattr__(self, "completed_outcomes", tuple(self.completed_outcomes))
        object.__setattr__(self, "promote_facts", tuple(self.promote_facts))
        object.__setattr__(self, "invalidate_fact_keys", _keys(self.invalidate_fact_keys, "invalidate_fact_keys"))
        object.__setattr__(self, "missing_evidence", _bounded_unique(self.missing_evidence, "missing_evidence"))
        if any(not isinstance(item, OutcomeProposal) for item in self.completed_outcomes):
            raise TypeError("audit outcomes must be typed")
        if any(not isinstance(item, PromoteFactProposal) for item in self.promote_facts):
            raise TypeError("audit fact promotions must be typed")
        if self.recovery_hint:
            _bounded_text(self.recovery_hint, "recovery hint")


@dataclass(frozen=True)
class AuditBoundaryResult:
    accepted: bool
    mission_state: MissionState
    reason_code: str = ""


@dataclass(frozen=True)
class EpisodeMonitorTransition:
    events: tuple[EpisodeMonitorEvent, ...]
    recommendation: EpisodeMonitorRecommendation
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))
        if any(not isinstance(item, EpisodeMonitorEvent) for item in self.events):
            raise TypeError("episode monitor events must be typed")
        if not isinstance(self.recommendation, EpisodeMonitorRecommendation):
            raise TypeError("episode monitor recommendation must be typed")


class ManagerPort(Protocol):
    async def decide(
        self, request: ManagerRoleRequest
    ) -> ModelInvocationResult[ManagerDecision]: ...


class AuditorPort(Protocol):
    async def audit(
        self, request: AuditorRoleRequest
    ) -> ModelInvocationResult[AuditDelta]: ...


def _bounded_text(value: str, field_name: str, *, limit: int = _MAX_TEXT) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{field_name} must be nonblank and bounded")


def _require_key(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _KEY.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be bounded snake_case")


def _require_id(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be bounded")


def _bounded_unique(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    result = tuple(str(item) for item in values)
    if len(result) > _MAX_COLLECTION or len(set(result)) != len(result):
        raise ValueError(f"{field_name} must be bounded and unique")
    for item in result:
        _bounded_text(item, field_name)
    return result


def _keys(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    result = _bounded_unique(values, field_name)
    for item in result:
        _require_key(item, field_name)
    return result


def _ids(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    result = _bounded_unique(values, field_name)
    for item in result:
        _require_id(item, field_name)
    return result

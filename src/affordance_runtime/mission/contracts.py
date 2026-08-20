"""Thin long-horizon mission contracts around the single GUI loop."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from affordance_runtime.agent.context.contracts import AgentTurnView, sanitize_history_value
from affordance_runtime.agent.working_facts import WorkingFact
from affordance_runtime.evaluation.evidence_records import EvidenceRecord
from affordance_runtime.immutable import freeze_json
from affordance_runtime.model.policy.contracts import ModelInvocationResult
from affordance_runtime.task.contracts import TaskGoal, criterion_id
from affordance_runtime.world.contracts import WorldObservation

_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ID = re.compile(r"^[a-z][a-z0-9_:-]{0,95}$")
_MAX_TEXT = 500
_MAX_COLLECTION = 32
_MAX_AUDIT_EVIDENCE_RECORDS = 4096


class ExecutionMode(StrEnum):
    STANDALONE = "standalone"
    MISSION = "mission"


class ManagerRoute(StrEnum):
    EXECUTE_SUBTASK = "execute_subtask"
    ASK_USER = "ask_user"
    BLOCKED = "blocked"
    REQUEST_FINALIZATION = "request_finalization"


class ManagerRequestMode(StrEnum):
    INITIAL_PLAN = "initial_plan"
    REVIEW_AND_ROUTE = "review_and_route"


class ManagerAssessment(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
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
    AUDITOR_CONTEXT_CAPACITY = "auditor_context_capacity"
    AUDITOR_PROVIDER_FAILURE = "auditor_provider_failure"
    AUDITOR_SCHEMA_FAILURE = "auditor_schema_failure"
    BOUNDARY_REJECTED = "boundary_rejected"
    EVIDENCE_GAP = "evidence_gap"
    FINALIZATION_NOT_READY = "finalization_not_ready"
    FINALIZED = "finalized"
    CANCELLED = "cancelled"
    TASK_COMPLETE = "task_complete"
    TASK_BLOCKED = "task_blocked"
    STRATEGY_NOT_CHANGED = "strategy_not_changed"
    OPERATIONAL_FAILURE = "operational_failure"
    UNHANDLED_EPISODE_STATE = "unhandled_episode_state"
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
    RECOVER = "recover"
    YIELD = "yield"


class RecoveryKind(StrEnum):
    GROUNDING_STALL = "grounding_stall"
    EFFECT_STALL = "effect_stall"
    UNCERTAIN_EFFECT = "uncertain_effect"
    STATE_OSCILLATION = "state_oscillation"
    CONTROL_STALL = "control_stall"
    STRATEGY_STALL = "strategy_stall"
    CAPABILITY_GAP = "capability_gap"
    PROTOCOL_STALL = "protocol_stall"


@dataclass(frozen=True)
class RecoverySignal:
    kind: RecoveryKind
    stable_signature: str
    observed_evidence: Mapping[str, object]
    attempted_modes: tuple[str, ...] = ()
    prohibited_immediate_repeat: str = ""
    recovery_attempt: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RecoveryKind):
            object.__setattr__(self, "kind", RecoveryKind(self.kind))
        _bounded_text(self.stable_signature, "recovery signature", limit=1_000)
        object.__setattr__(self, "observed_evidence", freeze_json(dict(self.observed_evidence)))
        object.__setattr__(self, "attempted_modes", _bounded_unique(self.attempted_modes, "attempted_modes"))
        if self.prohibited_immediate_repeat:
            _bounded_text(self.prohibited_immediate_repeat, "prohibited repeat", limit=1_000)
        if not 1 <= self.recovery_attempt <= 3:
            raise ValueError("recovery attempt is outside bounds")


@dataclass(frozen=True)
class SubtaskContract:
    objective: str
    done_when: str
    constraints: tuple[str, ...] = ()
    relevant_fact_keys: tuple[str, ...] = ()
    candidate_output_keys: tuple[str, ...] = ()
    episode_turn_budget: int = 15
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
        if type(self.episode_turn_budget) is not int or not 1 <= self.episode_turn_budget <= 15:
            raise ValueError("subtask episode budget must be within [1, 15]")


@dataclass(frozen=True)
class ManagerDecision:
    assessment: ManagerAssessment
    route: ManagerRoute
    evidence_refs: tuple[str, ...] = ()
    working_outcomes: tuple[WorkingOutcomeProposal, ...] = ()
    working_facts: tuple[WorkingFactProposal, ...] = ()
    invalidate_fact_keys: tuple[str, ...] = ()
    subtask: SubtaskContract | None = None
    question: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.assessment, ManagerAssessment):
            raise TypeError("manager assessment must be typed")
        if not isinstance(self.route, ManagerRoute):
            raise TypeError("manager route must be typed")
        object.__setattr__(self, "evidence_refs", _bounded_unique(self.evidence_refs, "evidence_refs"))
        object.__setattr__(self, "working_outcomes", tuple(self.working_outcomes))
        object.__setattr__(self, "working_facts", tuple(self.working_facts))
        object.__setattr__(
            self,
            "invalidate_fact_keys",
            _keys(self.invalidate_fact_keys, "invalidate_fact_keys"),
        )
        if any(not isinstance(item, WorkingOutcomeProposal) for item in self.working_outcomes):
            raise TypeError("manager working outcomes must be typed")
        if any(not isinstance(item, WorkingFactProposal) for item in self.working_facts):
            raise TypeError("manager working facts must be typed")
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

    def state_proposal(self, base_mission_version: int) -> WorkingStateProposal | None:
        if not (self.working_outcomes or self.working_facts or self.invalidate_fact_keys):
            return None
        return WorkingStateProposal(
            self.assessment,
            base_mission_version,
            self.working_outcomes,
            self.working_facts,
            self.invalidate_fact_keys,
        )


@dataclass(frozen=True)
class AcceptedWorkingOutcome:
    outcome_id: str
    assessment: ManagerAssessment
    evidence_refs: tuple[str, ...]
    summary: str
    evidence_records: tuple[EvidenceRecord, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        _require_id(self.outcome_id, "outcome_id")
        if self.assessment not in {ManagerAssessment.SATISFIED, ManagerAssessment.UNSATISFIED}:
            raise ValueError("MissionState stores only resolved working outcomes")
        object.__setattr__(self, "evidence_refs", _bounded_unique(self.evidence_refs, "evidence_refs"))
        _bounded_text(self.summary, "outcome summary")
        object.__setattr__(self, "evidence_records", tuple(self.evidence_records))
        if any(not isinstance(item, EvidenceRecord) for item in self.evidence_records):
            raise TypeError("working outcome evidence records must be typed")
        if self.evidence_records and tuple(item.evidence_ref for item in self.evidence_records) != self.evidence_refs:
            raise ValueError("working outcome records must match cited evidence refs")


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
    working_outcomes: tuple[AcceptedWorkingOutcome, ...] = ()
    accepted_facts: tuple[AcceptedFact, ...] = ()
    evidence_lineage: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.version < 0:
            raise ValueError("mission version cannot be negative")
        object.__setattr__(self, "working_outcomes", tuple(self.working_outcomes))
        object.__setattr__(self, "accepted_facts", tuple(self.accepted_facts))
        object.__setattr__(self, "evidence_lineage", _ids(self.evidence_lineage, "evidence_lineage"))
        if any(not isinstance(item, AcceptedWorkingOutcome) for item in self.working_outcomes):
            raise TypeError("mission working outcomes must be typed")
        if any(not isinstance(item, AcceptedFact) for item in self.accepted_facts):
            raise TypeError("mission accepted facts must be typed")
        if len({item.outcome_id for item in self.working_outcomes}) != len(self.working_outcomes):
            raise ValueError("working outcome IDs cannot repeat")
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

    def finalization_working_facts(self) -> tuple[WorkingFact, ...]:
        facts = [item.as_working_fact() for item in self.accepted_facts]
        for outcome_index, outcome in enumerate(self.working_outcomes, start=1):
            for record_index, record in enumerate(outcome.evidence_records, start=1):
                facts.append(
                    WorkingFact(
                        f"candidate_{outcome_index}_{record_index}",
                        record,
                        0,
                        outcome.summary,
                    )
                )
        return tuple(facts[:32])


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
class AuditGuidance:
    """Bounded Auditor advice for one immediately following Manager decision."""

    missing_evidence: tuple[str, ...] = ()
    recovery_hint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "missing_evidence",
            _bounded_unique(self.missing_evidence, "missing_evidence"),
        )
        if self.recovery_hint:
            _bounded_text(self.recovery_hint, "recovery hint")
        if not self.missing_evidence and not self.recovery_hint:
            raise ValueError("audit guidance cannot be empty")


@dataclass(frozen=True)
class ManagerRecoveryView:
    """Non-authoritative, one-shot recovery context owned by Supervisor routing."""

    exit_kind: str
    world_changed: bool
    prior_subtask: SubtaskContract
    recovery_signal: RecoverySignal | None = None
    attempted_modes: tuple[str, ...] = ()
    audit_guidance: AuditGuidance | None = None

    def __post_init__(self) -> None:
        _bounded_text(self.exit_kind, "recovery exit kind", limit=200)
        if type(self.world_changed) is not bool:
            raise TypeError("recovery world_changed must be boolean")
        if not isinstance(self.prior_subtask, SubtaskContract):
            raise TypeError("recovery prior_subtask must be typed")
        if self.recovery_signal is not None and not isinstance(self.recovery_signal, RecoverySignal):
            raise TypeError("manager recovery signal must be typed")
        object.__setattr__(
            self,
            "attempted_modes",
            _bounded_unique(self.attempted_modes, "attempted_modes"),
        )
        if self.audit_guidance is not None and not isinstance(self.audit_guidance, AuditGuidance):
            raise TypeError("manager audit guidance must be typed")


@dataclass(frozen=True)
class MissionEnvironmentView:
    """Bounded, ref-free projection of the fresh execution environment for Manager."""

    surface: str = "unknown"
    application: str = ""
    page_title: str = ""
    route_family: str = ""
    available_capabilities: tuple[str, ...] = ()
    unavailable_capabilities: tuple[str, ...] = ()
    last_successful_transitions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        surface = _ref_free_text(self.surface) or "unknown"
        object.__setattr__(self, "surface", surface)
        _bounded_text(surface, "environment surface", limit=80)
        for name, value in (
            ("environment application", self.application),
            ("environment page title", self.page_title),
            ("environment route family", self.route_family),
        ):
            clean = _ref_free_text(value)
            object.__setattr__(self, name.removeprefix("environment ").replace(" ", "_"), clean)
            if clean:
                _bounded_text(clean, name, limit=240)
        object.__setattr__(
            self,
            "available_capabilities",
            _ref_free_unique(self.available_capabilities, "available_capabilities"),
        )
        object.__setattr__(
            self,
            "unavailable_capabilities",
            _ref_free_unique(self.unavailable_capabilities, "unavailable_capabilities"),
        )
        object.__setattr__(
            self,
            "last_successful_transitions",
            _ref_free_unique(self.last_successful_transitions, "last_successful_transitions")[-4:],
        )


@dataclass(frozen=True)
class ManagerRoleRequest:
    mode: ManagerRequestMode
    original_task: TaskGoal
    mission_state: MissionState
    last_typed_exit: str = ""
    last_audit_or_failure_ref: str = ""
    remaining_rounds: int = 0
    recovery: ManagerRecoveryView | None = None
    environment: MissionEnvironmentView = field(default_factory=MissionEnvironmentView)
    active_subtask: SubtaskContract | None = None
    review_world: WorldObservation | None = None
    evidence_bundle: EvidenceBundle | None = None
    candidate_output_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ManagerRequestMode):
            raise TypeError("manager request mode must be typed")
        if self.recovery is not None and not isinstance(self.recovery, ManagerRecoveryView):
            raise TypeError("manager recovery view must be typed")
        if not isinstance(self.environment, MissionEnvironmentView):
            raise TypeError("manager environment view must be typed")
        object.__setattr__(
            self,
            "candidate_output_keys",
            _keys(self.candidate_output_keys, "candidate_output_keys"),
        )
        review_fields = (self.active_subtask, self.review_world, self.evidence_bundle)
        if self.mode is ManagerRequestMode.INITIAL_PLAN:
            if any(item is not None for item in review_fields) or self.recovery is not None:
                raise ValueError("initial_plan cannot carry an episode review")
        elif not all(item is not None for item in review_fields) or self.recovery is None:
            raise ValueError("review_and_route requires one complete fresh review bundle")
        if self.review_world is not None and self.evidence_bundle is not None:
            if self.review_world.observation_id != self.evidence_bundle.observation_id:
                raise ValueError("manager review evidence must describe its fresh World")


@dataclass(frozen=True)
class EvidenceBundle:
    observation_id: str
    source_observation_ids: tuple[str, ...]
    evidence_records: tuple[EvidenceRecord, ...]
    source_coverages: Mapping[str, str] | None = None
    total_evidence_count: int = 0

    @classmethod
    def from_world(cls, world: WorldObservation) -> EvidenceBundle:
        from affordance_runtime.evaluation.evidence import WorldEvidenceIndex, public_text_evidence_records

        index = WorldEvidenceIndex.from_observation(world)
        all_records = tuple(sorted(
            (*index.records, *public_text_evidence_records(world)),
            key=lambda item: item.evidence_ref,
        ))
        records = all_records[:_MAX_AUDIT_EVIDENCE_RECORDS]
        return cls(
            world.observation_id,
            tuple(source.observation_id for source in world.sources),
            records,
            {source.observation_id: source.coverage.value for source in world.sources},
            len(all_records),
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
class AuditorTaskProjection:
    """Role-specific public task slice; complete TaskGoal inputs never cross this boundary."""

    task_id: str
    revision: int
    instruction: str
    constraints: tuple[str, ...] = ()
    related_success_criteria: tuple[Mapping[str, object], ...] = ()
    related_requested_outputs: tuple[str, ...] = ()

    @classmethod
    def from_authorities(
        cls,
        task: TaskGoal,
        subtask: SubtaskContract,
    ) -> AuditorTaskProjection:
        related = set(subtask.related_audit_ids)
        outputs = set(subtask.candidate_output_keys)
        return cls(
            task.task_id,
            task.revision,
            task.instruction,
            subtask.constraints,
            tuple(item for item in task.success_criteria if criterion_id(item) in related),
            tuple(item for item in task.requested_outputs if item in outputs),
        )

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.instruction.strip():
            raise ValueError("Auditor task projection requires identity and instruction")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("Auditor task projection revision must be positive")
        object.__setattr__(self, "constraints", _bounded_unique(self.constraints, "audit task constraints"))
        object.__setattr__(
            self,
            "related_success_criteria",
            tuple(freeze_json(item) for item in self.related_success_criteria),
        )
        object.__setattr__(
            self,
            "related_requested_outputs",
            _bounded_unique(self.related_requested_outputs, "audit requested outputs"),
        )


@dataclass(frozen=True)
class AuditorRoleRequest:
    task: AuditorTaskProjection
    subtask: SubtaskContract
    pre_mission_state: MissionState
    after_world: WorldObservation
    working_facts: tuple[WorkingFact, ...]
    yield_reason: str
    episode_history: tuple[AgentTurnView, ...]
    audit_bundle: EvidenceBundle
    related_audit_ids: tuple[str, ...] = ()

    @classmethod
    def from_authorities(
        cls,
        original_task: TaskGoal,
        subtask: SubtaskContract,
        pre_mission_state: MissionState,
        after_world: WorldObservation,
        working_facts: tuple[WorkingFact, ...],
        yield_reason: str,
        episode_history: tuple[AgentTurnView, ...],
        audit_bundle: EvidenceBundle,
        related_audit_ids: tuple[str, ...] = (),
    ) -> AuditorRoleRequest:
        return cls(
            AuditorTaskProjection.from_authorities(original_task, subtask),
            subtask,
            pre_mission_state,
            after_world,
            working_facts,
            yield_reason,
            episode_history,
            audit_bundle,
            related_audit_ids,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.task, AuditorTaskProjection):
            raise TypeError("auditor request requires a role-specific task projection")
        if not isinstance(self.subtask, SubtaskContract):
            raise TypeError("auditor request requires a typed subtask")
        if not isinstance(self.pre_mission_state, MissionState):
            raise TypeError("auditor request requires typed pre-MissionState")
        if not isinstance(self.after_world, WorldObservation):
            raise TypeError("auditor request requires a fresh typed WorldObservation")
        if self.yield_reason not in {"outcome_proposed", "request_finalization"}:
            raise ValueError("Auditor is available only for a semantic commit or final uncertainty")
        object.__setattr__(self, "working_facts", tuple(self.working_facts))
        if any(not isinstance(item, WorkingFact) for item in self.working_facts):
            raise TypeError("auditor working facts must be typed")
        object.__setattr__(self, "episode_history", tuple(self.episode_history))
        if any(not isinstance(item, AgentTurnView) for item in self.episode_history):
            raise TypeError("auditor history must be public and typed")
        if not isinstance(self.audit_bundle, EvidenceBundle):
            raise TypeError("auditor request requires a typed audit bundle")
        if self.audit_bundle.observation_id != self.after_world.observation_id:
            raise ValueError("auditor bundle must describe the fresh audit world")
        object.__setattr__(
            self,
            "related_audit_ids",
            _ids(self.related_audit_ids, "related_audit_ids"),
        )


@dataclass(frozen=True)
class AuditorDecision:
    assessment: ManagerAssessment
    evidence_refs: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        if self.assessment is ManagerAssessment.NOT_APPLICABLE:
            raise ValueError("Auditor must return an opinion or unknown")
        object.__setattr__(
            self,
            "evidence_refs",
            _bounded_unique(self.evidence_refs, "auditor evidence_refs"),
        )
        if self.reason:
            _bounded_text(self.reason, "auditor reason")


@dataclass(frozen=True)
class WorkingOutcomeProposal:
    outcome_id: str
    assessment: ManagerAssessment
    evidence_refs: tuple[str, ...]
    summary: str

    def __post_init__(self) -> None:
        _require_id(self.outcome_id, "outcome_id")
        if self.assessment not in {ManagerAssessment.SATISFIED, ManagerAssessment.UNSATISFIED}:
            raise ValueError("working outcomes must use resolved assessments")
        object.__setattr__(self, "evidence_refs", _bounded_unique(self.evidence_refs, "evidence_refs"))
        _bounded_text(self.summary, "outcome proposal summary")


@dataclass(frozen=True)
class WorkingFactProposal:
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
class WorkingStateProposal:
    assessment: ManagerAssessment
    base_mission_version: int
    completed_outcomes: tuple[WorkingOutcomeProposal, ...] = ()
    promote_facts: tuple[WorkingFactProposal, ...] = ()
    invalidate_fact_keys: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    recovery_hint: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.assessment, ManagerAssessment):
            raise TypeError("working-state assessment must be typed")
        if self.base_mission_version < 0:
            raise ValueError("working-state base version cannot be negative")
        object.__setattr__(self, "completed_outcomes", tuple(self.completed_outcomes))
        object.__setattr__(self, "promote_facts", tuple(self.promote_facts))
        object.__setattr__(self, "invalidate_fact_keys", _keys(self.invalidate_fact_keys, "invalidate_fact_keys"))
        object.__setattr__(self, "missing_evidence", _bounded_unique(self.missing_evidence, "missing_evidence"))
        if any(not isinstance(item, WorkingOutcomeProposal) for item in self.completed_outcomes):
            raise TypeError("working outcomes must be typed")
        if any(not isinstance(item, WorkingFactProposal) for item in self.promote_facts):
            raise TypeError("working fact proposals must be typed")
        if self.recovery_hint:
            _bounded_text(self.recovery_hint, "recovery hint")


@dataclass(frozen=True)
class EvidenceBoundaryResult:
    accepted: bool
    mission_state: MissionState
    reason_code: str = ""


@dataclass(frozen=True)
class EpisodeMonitorTransition:
    events: tuple[EpisodeMonitorEvent, ...]
    recommendation: EpisodeMonitorRecommendation
    reason: str = ""
    recovery_signal: RecoverySignal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))
        if any(not isinstance(item, EpisodeMonitorEvent) for item in self.events):
            raise TypeError("episode monitor events must be typed")
        if not isinstance(self.recommendation, EpisodeMonitorRecommendation):
            raise TypeError("episode monitor recommendation must be typed")
        if self.recovery_signal is not None and not isinstance(self.recovery_signal, RecoverySignal):
            raise TypeError("episode monitor recovery signal must be typed")


class ManagerPort(Protocol):
    async def decide(
        self, request: ManagerRoleRequest
    ) -> ModelInvocationResult[ManagerDecision]: ...


class AuditorPort(Protocol):
    async def audit(
        self, request: AuditorRoleRequest
    ) -> ModelInvocationResult[AuditorDecision]: ...


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


def _ref_free_text(value: str) -> str:
    sanitized = sanitize_history_value(value)
    if not isinstance(sanitized, str):
        raise TypeError("ref-free mission projection requires text")
    return sanitized


def _ref_free_unique(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    bounded = _bounded_unique(values, field_name)
    sanitized = tuple(
        dict.fromkeys(clean for item in bounded if (clean := _ref_free_text(item)))
    )
    return _bounded_unique(sanitized, field_name)


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

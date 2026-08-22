"""Thin long-horizon mission contracts around the single GUI loop."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from affordance_runtime.agent.attempt_signature import PublicAttemptSignature
from affordance_runtime.agent.budgets import ORDINARY_EPISODE_TURNS
from affordance_runtime.agent.context.contracts import sanitize_history_value
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
_MAX_AUDIT_EVIDENCE_RECORDS = 4096


class ExecutionMode(StrEnum):
    STANDALONE = "standalone"
    MISSION = "mission"


class PlannerRoute(StrEnum):
    ROADMAP = "roadmap"
    ASK_USER = "ask_user"
    BLOCKED = "blocked"


class PlannerRequestMode(StrEnum):
    START = "start"
    NEEDS_REPLAN = "needs_replan"
    ROADMAP_EXHAUSTED_NOT_FINALIZABLE = "roadmap_exhausted_not_finalizable"


class EvidenceAssessment(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"


class MilestoneAdmissionRoute(StrEnum):
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    CONTINUE_EVIDENCE = "continue_evidence"
    SEMANTIC_AUDIT = "semantic_audit"


class EvidenceBoundaryRejectionClass(StrEnum):
    """Whether a rejected write is unsafe or can be replanned without a write."""

    FATAL = "fatal"
    RECOVERABLE_SHAPE = "recoverable_shape"


class SupervisorPhase(StrEnum):
    PLANNING = "planning"
    EXECUTING = "executing"
    AUDITING = "auditing"
    FINALIZING = "finalizing"
    WAITING_USER = "waiting_user"
    TERMINAL = "terminal"


class MissionOutcome(StrEnum):
    RUNNING = "running"
    NEEDS_USER_INPUT = "needs_user_input"
    BLOCKED = "blocked"
    PLANNER_FAILURE = "planner_failure"
    AUDIT_UNAVAILABLE = "audit_unavailable"
    BOUNDARY_REJECTED = "boundary_rejected"
    EVIDENCE_GAP = "evidence_gap"
    FINALIZATION_NOT_READY = "finalization_not_ready"
    FINALIZED = "finalized"
    CANCELLED = "cancelled"
    TASK_COMPLETE = "task_complete"
    TASK_BLOCKED = "task_blocked"
    OPERATIONAL_FAILURE = "operational_failure"
    UNHANDLED_EPISODE_STATE = "unhandled_episode_state"
    ROUND_BUDGET_EXHAUSTED = "round_budget_exhausted"


class EpisodeMonitorEvent(StrEnum):
    STATE_CHANGED = "state_changed"
    NO_OBSERVED_CHANGE = "no_observed_change"
    REPEATED_ACTION = "repeated_action"
    OSCILLATION = "oscillation"
    ROUTE_REGRESSION = "route_regression"
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
    ROUTE_REGRESSION = "route_regression"
    CONTROL_STALL = "control_stall"
    STRATEGY_STALL = "strategy_stall"
    CAPABILITY_GAP = "capability_gap"
    PROTOCOL_STALL = "protocol_stall"
    MILESTONE_MISALIGNED = "milestone_misaligned"


ORDINARY_EPISODE_TURN_BUDGET = ORDINARY_EPISODE_TURNS


@dataclass(frozen=True)
class EvidenceRequirement:
    key: str
    description: str

    def __post_init__(self) -> None:
        _require_key(self.key, "evidence requirement key")
        _bounded_text(self.description, "evidence requirement description")


@dataclass(frozen=True)
class RecoverySignal:
    kind: RecoveryKind
    stable_signature: str
    observed_evidence: Mapping[str, object]
    attempted_modes: tuple[str, ...] = ()
    prohibited_attempt_signature: PublicAttemptSignature | None = None
    human_instruction: str = ""
    recovery_attempt: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RecoveryKind):
            object.__setattr__(self, "kind", RecoveryKind(self.kind))
        _bounded_text(self.stable_signature, "recovery signature", limit=1_000)
        object.__setattr__(self, "observed_evidence", freeze_json(dict(self.observed_evidence)))
        object.__setattr__(self, "attempted_modes", _bounded_unique(self.attempted_modes, "attempted_modes"))
        if self.prohibited_attempt_signature is not None and not isinstance(
            self.prohibited_attempt_signature, PublicAttemptSignature
        ):
            raise TypeError("prohibited attempt signature must be typed")
        if self.human_instruction:
            _bounded_text(self.human_instruction, "recovery instruction", limit=1_000)
        if not 1 <= self.recovery_attempt <= 3:
            raise ValueError("recovery attempt is outside bounds")


@dataclass(frozen=True)
class Milestone:
    id: str
    outcome: str
    done_when: str
    required_evidence: tuple[EvidenceRequirement, ...] = ()
    depends_on: tuple[str, ...] = ()
    final: bool = False

    def __post_init__(self) -> None:
        _require_id(self.id, "milestone id")
        _bounded_text(self.outcome, "milestone outcome")
        _bounded_text(self.done_when, "milestone done_when")
        requirements = tuple(self.required_evidence)
        if any(not isinstance(item, EvidenceRequirement) for item in requirements):
            raise TypeError("milestone required evidence must be typed")
        if len(requirements) > 16:
            raise ValueError("required_evidence exceeds bounded collection size")
        if len({item.key for item in requirements}) != len(requirements):
            raise ValueError("required evidence keys must be unique")
        object.__setattr__(self, "required_evidence", requirements)
        object.__setattr__(self, "depends_on", _ids(self.depends_on, "milestone dependencies"))
        if self.id in self.depends_on:
            raise ValueError("milestone cannot depend on itself")
        if type(self.final) is not bool:
            raise TypeError("milestone final flag must be boolean")


@dataclass(frozen=True)
class MilestoneRoadmap:
    version: int
    milestones: tuple[Milestone, ...]

    def __post_init__(self) -> None:
        if type(self.version) is not int or self.version < 1:
            raise ValueError("roadmap version must be positive")
        milestones = tuple(self.milestones)
        if not 1 <= len(milestones) <= 5 or any(not isinstance(item, Milestone) for item in milestones):
            raise ValueError("roadmap requires one to five typed milestones")
        ids = {item.id for item in milestones}
        if len(ids) != len(milestones):
            raise ValueError("roadmap milestone ids must be unique")
        if any(dep not in ids for item in milestones for dep in item.depends_on):
            raise ValueError("roadmap dependency is missing")
        if sum(item.final for item in milestones) > 1:
            raise ValueError("roadmap permits at most one final milestone")
        visiting: set[str] = set()
        visited: set[str] = set()
        by_id = {item.id: item for item in milestones}

        def visit(milestone_id: str) -> None:
            if milestone_id in visiting:
                raise ValueError("roadmap dependencies must be acyclic")
            if milestone_id in visited:
                return
            visiting.add(milestone_id)
            for dependency in by_id[milestone_id].depends_on:
                visit(dependency)
            visiting.remove(milestone_id)
            visited.add(milestone_id)

        for milestone_id in by_id:
            visit(milestone_id)
        object.__setattr__(self, "milestones", milestones)

    def select_ready(self, mission: MissionState) -> Milestone | None:
        accepted = {
            item.outcome_id
            for item in mission.working_outcomes
            if item.assessment is EvidenceAssessment.SATISFIED
        }
        return next(
            (
                item
                for item in self.milestones
                if item.id not in accepted and set(item.depends_on).issubset(accepted)
            ),
            None,
        )


@dataclass(frozen=True)
class PlannerDecision:
    route: PlannerRoute
    roadmap: MilestoneRoadmap | None = None
    question: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.route, PlannerRoute):
            raise TypeError("planner route must be typed")
        if self.route is PlannerRoute.ROADMAP:
            if self.roadmap is None or self.question:
                raise ValueError("roadmap route requires exactly one MilestoneRoadmap")
        elif self.roadmap is not None:
            raise ValueError("only roadmap route can carry a roadmap")
        if self.route is PlannerRoute.ASK_USER:
            _bounded_text(self.question, "planner question", limit=1_000)
        elif self.question:
            raise ValueError("only ask_user can carry a question")
        if self.reason:
            _bounded_text(self.reason, "planner reason")


@dataclass(frozen=True)
class AcceptedWorkingOutcome:
    outcome_id: str
    assessment: EvidenceAssessment
    evidence_refs: tuple[str, ...]
    summary: str
    evidence_records: tuple[EvidenceRecord, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        _require_id(self.outcome_id, "outcome_id")
        if self.assessment not in {EvidenceAssessment.SATISFIED, EvidenceAssessment.UNSATISFIED}:
            raise ValueError("MissionState stores only resolved working outcomes")
        object.__setattr__(self, "evidence_refs", _bounded_unique(self.evidence_refs, "evidence_refs"))
        if self.assessment is EvidenceAssessment.SATISFIED and not self.evidence_refs:
            raise ValueError("satisfied MissionState outcome requires evidence refs")
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
        return tuple(item.as_working_fact() for item in self.accepted_facts if item.key in selected)

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
    phase: SupervisorPhase = SupervisorPhase.PLANNING
    active_milestone: Milestone | None = None
    roadmap: MilestoneRoadmap | None = None
    last_typed_episode_exit: str = ""
    last_ref: str = ""
    mission_round_budget: int = 8
    final_response_delivered: bool = False
    opened_environment_ref: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.phase, SupervisorPhase):
            raise TypeError("supervisor phase must be typed")
        if self.active_milestone is not None and not isinstance(self.active_milestone, Milestone):
            raise TypeError("active milestone must be typed")
        if self.roadmap is not None and not isinstance(self.roadmap, MilestoneRoadmap):
            raise TypeError("supervisor roadmap must be typed")
        if not 0 <= self.mission_round_budget <= 100:
            raise ValueError("mission round budget is outside bounds")
        for value in (self.last_typed_episode_exit, self.last_ref, self.opened_environment_ref):
            if value and len(value) > 200:
                raise ValueError("supervisor transient identity exceeds bounds")
        if type(self.final_response_delivered) is not bool:
            raise TypeError("final response latch must be boolean")


@dataclass(frozen=True)
class AuditGuidance:
    """Bounded evidence/audit feedback for the same ActionPolicy milestone."""

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
class PublicOutcomeSummary:
    """Bounded public change summary; never a second World or completion authority."""

    before_observation_id: str
    after_observation_id: str
    world_changed: bool
    new_evidence_refs: tuple[str, ...] = ()
    outcome: str = ""

    def __post_init__(self) -> None:
        if not self.before_observation_id.strip() or not self.after_observation_id.strip():
            raise ValueError("public outcome summary requires before/after identity")
        if type(self.world_changed) is not bool:
            raise TypeError("public outcome world_changed must be boolean")
        object.__setattr__(
            self,
            "new_evidence_refs",
            _bounded_evidence_refs(self.new_evidence_refs),
        )
        if self.outcome:
            _bounded_text(self.outcome, "public outcome summary")


@dataclass(frozen=True)
class PlannerRecoveryView:
    """Non-authoritative, one-shot recovery context owned by Supervisor routing."""

    exit_kind: str
    world_changed: bool
    prior_milestone: Milestone
    recovery_signal: RecoverySignal | None = None
    attempted_modes: tuple[str, ...] = ()
    outcome_proposal: str = ""
    working_proposal_feedback: str = ""

    def __post_init__(self) -> None:
        _bounded_text(self.exit_kind, "recovery exit kind", limit=200)
        if type(self.world_changed) is not bool:
            raise TypeError("recovery world_changed must be boolean")
        if not isinstance(self.prior_milestone, Milestone):
            raise TypeError("recovery prior_milestone must be typed")
        if self.recovery_signal is not None and not isinstance(self.recovery_signal, RecoverySignal):
            raise TypeError("planner recovery signal must be typed")
        object.__setattr__(
            self,
            "attempted_modes",
            _bounded_unique(self.attempted_modes, "attempted_modes"),
        )
        if self.outcome_proposal:
            _bounded_text(self.outcome_proposal, "outcome proposal")
        if self.working_proposal_feedback:
            _bounded_text(
                self.working_proposal_feedback,
                "working proposal feedback",
                limit=200,
            )


@dataclass(frozen=True)
class FunctionalRegionSummary:
    label: str
    purpose: str
    control_families: tuple[str, ...] = ()
    coverage: str = "complete"

    def __post_init__(self) -> None:
        label = _ref_free_text(self.label)
        if not label:
            raise ValueError("functional region requires a label")
        object.__setattr__(self, "label", label)
        purpose = _ref_free_text(self.purpose)
        if not purpose:
            raise ValueError("functional region requires a purpose")
        object.__setattr__(self, "purpose", purpose)
        object.__setattr__(
            self,
            "control_families",
            _ref_free_unique(self.control_families, "control_families"),
        )
        if self.coverage not in {"complete", "partial"}:
            raise ValueError("functional region coverage is invalid")


@dataclass(frozen=True)
class MissionEnvironmentView:
    """Bounded, ref-free projection of the fresh execution environment for Planner."""

    surface: str = "unknown"
    application: str = ""
    page_title: str = ""
    route_family: str = ""
    document_title: str = ""
    current_route: str = ""
    visible_primary_heading: str = ""
    identity_conflict: bool = False
    available_capabilities: tuple[str, ...] = ()
    unavailable_capabilities: tuple[str, ...] = ()
    last_successful_transitions: tuple[str, ...] = ()
    functional_regions: tuple[FunctionalRegionSummary, ...] = ()
    world_observation_id: str = field(default="", repr=False, compare=False, metadata={"serialize": False})

    def __post_init__(self) -> None:
        surface = _ref_free_text(self.surface) or "unknown"
        object.__setattr__(self, "surface", surface)
        _bounded_text(surface, "environment surface", limit=80)
        for name, value in (
            ("environment application", self.application),
            ("environment page title", self.page_title),
            ("environment route family", self.route_family),
            ("environment document title", self.document_title),
            ("environment current route", self.current_route),
            ("environment visible primary heading", self.visible_primary_heading),
        ):
            clean = _ref_free_text(value)
            object.__setattr__(self, name.removeprefix("environment ").replace(" ", "_"), clean)
            if clean:
                _bounded_text(clean, name, limit=240)
        if type(self.identity_conflict) is not bool:
            raise TypeError("environment identity conflict must be boolean")
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
        regions = tuple(self.functional_regions)
        if len(regions) > _MAX_COLLECTION or any(not isinstance(item, FunctionalRegionSummary) for item in regions):
            raise ValueError("mission environment functional regions are invalid")
        object.__setattr__(self, "functional_regions", regions)
        if self.world_observation_id and len(self.world_observation_id) > 240:
            raise ValueError("mission environment lineage is invalid")


@dataclass(frozen=True)
class PlannerRoleRequest:
    mode: PlannerRequestMode
    original_task: TaskGoal
    mission_state: MissionState
    current_roadmap: MilestoneRoadmap | None = None
    last_typed_exit: str = ""
    remaining_mission_budget: int = 0
    recovery: PlannerRecoveryView | None = None
    environment: MissionEnvironmentView = field(default_factory=MissionEnvironmentView)
    last_milestone_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.mode, PlannerRequestMode):
            raise TypeError("planner request mode must be typed")
        if self.current_roadmap is not None and not isinstance(self.current_roadmap, MilestoneRoadmap):
            raise TypeError("planner current roadmap must be typed")
        if self.recovery is not None and not isinstance(self.recovery, PlannerRecoveryView):
            raise TypeError("planner recovery view must be typed")
        if not isinstance(self.environment, MissionEnvironmentView):
            raise TypeError("planner environment view must be typed")
        if not 0 <= self.remaining_mission_budget <= 100:
            raise ValueError("remaining mission budget is outside bounds")
        if self.mode is PlannerRequestMode.START:
            if self.current_roadmap is not None or self.recovery is not None or self.last_milestone_id:
                raise ValueError("start request cannot carry prior roadmap state")
        elif self.current_roadmap is None:
            raise ValueError("boundary planner requests require the current roadmap")
        if self.mode is PlannerRequestMode.NEEDS_REPLAN and self.recovery is None:
            raise ValueError("needs_replan requires typed recovery context")
        if self.mode is not PlannerRequestMode.NEEDS_REPLAN and self.recovery is not None:
            raise ValueError("only needs_replan can carry recovery context")
        if self.last_milestone_id:
            _require_id(self.last_milestone_id, "last milestone id")


@dataclass(frozen=True)
class EvidenceBundle:
    observation_id: str
    source_observation_ids: tuple[str, ...]
    evidence_records: tuple[EvidenceRecord, ...]
    source_coverages: Mapping[str, str] | None = None
    total_evidence_count: int = 0
    pinned_evidence_refs: tuple[str, ...] = ()

    @classmethod
    def from_world(
        cls,
        world: WorldObservation,
        working_facts: tuple[WorkingFact, ...] = (),
    ) -> EvidenceBundle:
        from affordance_runtime.evaluation.evidence import WorldEvidenceIndex, public_text_evidence_records

        index = WorldEvidenceIndex.from_observation(world)
        pinned_by_ref: dict[str, EvidenceRecord] = {}
        for item in working_facts:
            previous = pinned_by_ref.get(item.record.evidence_ref)
            if previous is not None and previous != item.record:
                raise ValueError("one pinned evidence ref cannot identify conflicting records")
            pinned_by_ref[item.record.evidence_ref] = item.record
        pinned = tuple(pinned_by_ref.values())
        by_ref = {item.evidence_ref: item for item in (*index.records, *public_text_evidence_records(world), *pinned)}
        pinned_refs = {item.evidence_ref for item in pinned}
        all_records = tuple(sorted(by_ref.values(), key=lambda item: item.evidence_ref))
        records = (
            *sorted(pinned, key=lambda item: item.evidence_ref),
            *(item for item in all_records if item.evidence_ref not in pinned_refs),
        )[:_MAX_AUDIT_EVIDENCE_RECORDS]
        return cls(
            world.observation_id,
            tuple(source.observation_id for source in world.sources),
            records,
            {source.observation_id: source.coverage.value for source in world.sources},
            len(all_records),
            tuple(item.evidence_ref for item in pinned),
        )

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("audit bundle requires observation identity")
        object.__setattr__(self, "source_observation_ids", _bounded_unique(self.source_observation_ids, "sources"))
        object.__setattr__(self, "evidence_records", tuple(self.evidence_records))
        object.__setattr__(self, "source_coverages", dict(self.source_coverages or {}))
        object.__setattr__(
            self,
            "pinned_evidence_refs",
            _bounded_evidence_refs(self.pinned_evidence_refs),
        )
        if len(self.evidence_records) > _MAX_AUDIT_EVIDENCE_RECORDS:
            raise ValueError("audit bundle evidence records exceed bound")
        if self.total_evidence_count and self.total_evidence_count < len(self.evidence_records):
            raise ValueError("audit bundle total cannot be smaller than retained evidence")
        if any(not isinstance(item, EvidenceRecord) for item in self.evidence_records):
            raise TypeError("audit bundle evidence must be typed")
        if any(self.resolve(ref) is None for ref in self.pinned_evidence_refs):
            raise ValueError("pinned audit evidence must belong to the bundle")

    def resolve(self, evidence_ref: str) -> EvidenceRecord | None:
        return next((item for item in self.evidence_records if item.evidence_ref == evidence_ref), None)

    def bounded_packet(self, limit: int = 128) -> EvidenceBundle:
        """Return the exact evidence packet offered to one semantic Auditor call."""

        if not 1 <= limit <= 128:
            raise ValueError("Auditor evidence packet limit is outside bounds")
        records = self.evidence_records[:limit]
        retained = {item.evidence_ref for item in records}
        if any(ref not in retained for ref in self.pinned_evidence_refs):
            raise ValueError("Auditor evidence packet cannot drop pinned WorkingFacts")
        return EvidenceBundle(
            self.observation_id,
            self.source_observation_ids,
            records,
            self.source_coverages,
            self.total_evidence_count or len(self.evidence_records),
            self.pinned_evidence_refs,
        )

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
    related_requested_outputs: tuple[str, ...] = ()

    @classmethod
    def from_authorities(
        cls,
        task: TaskGoal,
        milestone: Milestone,
    ) -> AuditorTaskProjection:
        outputs = {item.key for item in milestone.required_evidence}
        return cls(
            task.task_id,
            task.revision,
            task.instruction,
            task.constraints,
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
            "related_requested_outputs",
            _bounded_unique(self.related_requested_outputs, "audit requested outputs"),
        )


@dataclass(frozen=True)
class AuditorRoleRequest:
    task: AuditorTaskProjection
    milestone: Milestone
    pre_mission_state: MissionState
    working_facts: tuple[WorkingFact, ...]
    outcome_summary: PublicOutcomeSummary
    yield_reason: str
    audit_bundle: EvidenceBundle

    @classmethod
    def from_authorities(
        cls,
        original_task: TaskGoal,
        milestone: Milestone,
        pre_mission_state: MissionState,
        working_facts: tuple[WorkingFact, ...],
        outcome_summary: PublicOutcomeSummary,
        yield_reason: str,
        audit_bundle: EvidenceBundle,
    ) -> AuditorRoleRequest:
        return cls(
            AuditorTaskProjection.from_authorities(original_task, milestone),
            milestone,
            pre_mission_state,
            working_facts,
            outcome_summary,
            yield_reason,
            audit_bundle,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.task, AuditorTaskProjection):
            raise TypeError("auditor request requires a role-specific task projection")
        if not isinstance(self.milestone, Milestone):
            raise TypeError("auditor request requires a typed milestone")
        if not isinstance(self.pre_mission_state, MissionState):
            raise TypeError("auditor request requires typed pre-MissionState")
        if not isinstance(self.outcome_summary, PublicOutcomeSummary):
            raise TypeError("auditor request requires a typed public outcome summary")
        if self.yield_reason != "outcome_proposed":
            raise ValueError("Auditor is available only for a semantic milestone uncertainty")
        object.__setattr__(self, "working_facts", tuple(self.working_facts))
        if any(not isinstance(item, WorkingFact) for item in self.working_facts):
            raise TypeError("auditor working facts must be typed")
        if not isinstance(self.audit_bundle, EvidenceBundle):
            raise TypeError("auditor request requires a typed audit bundle")
        if len(self.audit_bundle.evidence_records) > 128:
            raise ValueError("auditor request evidence packet exceeds 128 records")
        if self.audit_bundle.observation_id != self.outcome_summary.after_observation_id:
            raise ValueError("auditor bundle must describe the fresh audit world")
        if any(
            self.audit_bundle.resolve(item.record.evidence_ref) != item.record
            or item.record.evidence_ref not in self.audit_bundle.pinned_evidence_refs
            for item in self.working_facts
        ):
            raise ValueError("Auditor working facts must retain pinned bundle lineage")


@dataclass(frozen=True)
class AuditorDecision:
    assessment: EvidenceAssessment
    evidence_refs: tuple[str, ...] = ()
    missing_evidence_keys: tuple[str, ...] = ()
    guidance: str = ""

    def __post_init__(self) -> None:
        if self.assessment not in {
            EvidenceAssessment.SATISFIED,
            EvidenceAssessment.UNSATISFIED,
            EvidenceAssessment.UNKNOWN,
        }:
            raise ValueError("Auditor must return satisfied, unsatisfied, or unknown")
        object.__setattr__(
            self,
            "evidence_refs",
            _bounded_unique(self.evidence_refs, "auditor evidence_refs"),
        )
        if self.assessment is EvidenceAssessment.SATISFIED and not self.evidence_refs:
            raise ValueError("satisfied Auditor decision requires evidence refs")
        object.__setattr__(
            self,
            "missing_evidence_keys",
            _bounded_unique(self.missing_evidence_keys, "auditor missing evidence keys"),
        )
        if self.guidance:
            _bounded_text(self.guidance, "auditor guidance")


@dataclass(frozen=True)
class WorkingOutcomeProposal:
    outcome_id: str
    assessment: EvidenceAssessment
    evidence_refs: tuple[str, ...]
    summary: str

    def __post_init__(self) -> None:
        _require_id(self.outcome_id, "outcome_id")
        if self.assessment is EvidenceAssessment.SATISFIED and not self.evidence_refs:
            raise ValueError("satisfied working outcome requires evidence refs")
        if self.assessment not in {EvidenceAssessment.SATISFIED, EvidenceAssessment.UNSATISFIED}:
            raise ValueError("working outcomes must use resolved assessments")
        object.__setattr__(self, "evidence_refs", _bounded_unique(self.evidence_refs, "evidence_refs"))
        _bounded_text(self.summary, "outcome proposal summary")


@dataclass(frozen=True)
class WorkingFactProposal:
    key: str
    evidence_ref: str
    purpose: str

    def __post_init__(self) -> None:
        _require_key(self.key, "fact key")
        _bounded_text(self.evidence_ref, "evidence_ref")
        _bounded_text(self.purpose, "fact purpose")


@dataclass(frozen=True)
class WorkingStateProposal:
    assessment: EvidenceAssessment
    base_mission_version: int
    working_outcomes: tuple[WorkingOutcomeProposal, ...] = ()
    promote_facts: tuple[WorkingFactProposal, ...] = ()
    invalidate_fact_keys: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    recovery_hint: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.assessment, EvidenceAssessment):
            raise TypeError("working-state assessment must be typed")
        if self.base_mission_version < 0:
            raise ValueError("working-state base version cannot be negative")
        object.__setattr__(self, "working_outcomes", tuple(self.working_outcomes))
        object.__setattr__(self, "promote_facts", tuple(self.promote_facts))
        object.__setattr__(self, "invalidate_fact_keys", _keys(self.invalidate_fact_keys, "invalidate_fact_keys"))
        object.__setattr__(self, "missing_evidence", _bounded_unique(self.missing_evidence, "missing_evidence"))
        if any(not isinstance(item, WorkingOutcomeProposal) for item in self.working_outcomes):
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
    rejection_class: EvidenceBoundaryRejectionClass | None = None

    def __post_init__(self) -> None:
        if self.accepted:
            if self.reason_code or self.rejection_class is not None:
                raise ValueError("accepted boundary result cannot carry rejection data")
            return
        if not self.reason_code or self.rejection_class is None:
            raise ValueError("rejected boundary result requires typed rejection data")
        if not isinstance(self.rejection_class, EvidenceBoundaryRejectionClass):
            raise TypeError("boundary rejection class must be typed")


@dataclass(frozen=True)
class MilestoneAdmission:
    route: MilestoneAdmissionRoute
    assessment: EvidenceAssessment
    proposal: WorkingStateProposal | None = None
    reason_code: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.route, MilestoneAdmissionRoute):
            raise TypeError("milestone admission route must be typed")
        if not isinstance(self.assessment, EvidenceAssessment):
            raise TypeError("milestone admission assessment must be typed")
        if self.proposal is not None and not isinstance(self.proposal, WorkingStateProposal):
            raise TypeError("milestone admission proposal must be typed")
        if self.assessment is EvidenceAssessment.SATISFIED and self.proposal is None:
            raise ValueError("satisfied milestone admission requires a proposal")
        expected = {
            MilestoneAdmissionRoute.SATISFIED: EvidenceAssessment.SATISFIED,
            MilestoneAdmissionRoute.UNSATISFIED: EvidenceAssessment.UNSATISFIED,
            MilestoneAdmissionRoute.CONTINUE_EVIDENCE: EvidenceAssessment.UNKNOWN,
            MilestoneAdmissionRoute.SEMANTIC_AUDIT: EvidenceAssessment.UNKNOWN,
        }[self.route]
        if self.assessment is not expected:
            raise ValueError("milestone admission route and assessment disagree")
        if self.reason_code:
            _bounded_text(self.reason_code, "milestone admission reason", limit=200)


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


class PlannerPort(Protocol):
    async def plan(self, request: PlannerRoleRequest) -> ModelInvocationResult[PlannerDecision]: ...


class AuditorPort(Protocol):
    async def audit(self, request: AuditorRoleRequest) -> ModelInvocationResult[AuditorDecision]: ...


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


def _bounded_evidence_refs(values: tuple[str, ...]) -> tuple[str, ...]:
    result = tuple(str(item) for item in values)
    if len(result) > _MAX_AUDIT_EVIDENCE_RECORDS or len(set(result)) != len(result):
        raise ValueError("allowed_evidence_refs must be bounded and unique")
    for item in result:
        _bounded_text(item, "allowed_evidence_refs")
    return result


def _ref_free_text(value: str) -> str:
    sanitized = sanitize_history_value(value)
    if not isinstance(sanitized, str):
        raise TypeError("ref-free mission projection requires text")
    return sanitized


def _ref_free_unique(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    bounded = _bounded_unique(values, field_name)
    sanitized = tuple(dict.fromkeys(clean for item in bounded if (clean := _ref_free_text(item))))
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

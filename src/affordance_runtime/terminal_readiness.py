"""Typed, provider-neutral admission for task-terminal candidates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.contracts import Observation
from affordance_runtime.grounding import UnifiedAffordance
from affordance_runtime.task_planning import (
    PlanProgress,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    planning_semantic_tokens,
)


class ObligationState(StrEnum):
    OPEN = "open"
    SATISFIED = "satisfied"
    UNKNOWN = "unknown"


class TerminalReadinessStatus(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TaskObligationEvidence:
    """One typed obligation state backed by Runtime verification evidence."""

    obligation_id: str
    state: ObligationState
    task_revision: int
    verification_refs: tuple[str, ...] = ()
    observation_epoch_id: str = ""
    require_current_epoch: bool = False

    def __post_init__(self) -> None:
        if not self.obligation_id or self.task_revision < 1:
            raise ValueError("obligation evidence requires identity and task revision")
        if self.state == ObligationState.SATISFIED and not self.verification_refs:
            raise ValueError("satisfied obligation requires verification evidence")
        if self.require_current_epoch and not self.observation_epoch_id:
            raise ValueError("current-epoch obligation requires an observation epoch")


@dataclass(frozen=True)
class TerminalCandidate:
    """A caller-classified terminal candidate with explicit dependency closure."""

    semantic_target_id: str
    prerequisite_obligation_ids: tuple[str, ...] = ()
    dependencies_complete: bool = False

    def __post_init__(self) -> None:
        if not self.semantic_target_id:
            raise ValueError("terminal candidate requires a semantic target id")
        if len(self.prerequisite_obligation_ids) != len(
            set(self.prerequisite_obligation_ids)
        ):
            raise ValueError("terminal prerequisites must be unique")


@dataclass(frozen=True)
class TerminalEffectBinding:
    """Current grounding of one terminal candidate to one typed plan subgoal."""

    semantic_target_id: str
    candidate_id: str
    subgoal_id: str
    task_revision: int
    observation_epoch_id: str
    target_fingerprint: str

    def __post_init__(self) -> None:
        if not all(
            (
                self.semantic_target_id,
                self.candidate_id,
                self.subgoal_id,
                self.observation_epoch_id,
                self.target_fingerprint,
            )
        ) or self.task_revision < 1:
            raise ValueError("terminal effect binding requires current typed lineage")


@dataclass(frozen=True)
class TerminalEffectBindingResolution:
    bindings: tuple[TerminalEffectBinding, ...] = ()
    unresolved_target_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TerminalEffectBindingResolver:
    """Resolve only a unique active typed completion outcome to current grounding."""

    def resolve(
        self,
        *,
        plan: TaskPlan,
        progress: PlanProgress,
        unified_affordances: tuple[UnifiedAffordance, ...],
        observation: Observation,
    ) -> TerminalEffectBindingResolution:
        subgoal = _active_subgoal(plan, progress)
        if (
            subgoal is None
            or subgoal.outcome is None
            or subgoal.outcome.relation != SubgoalOutcomeRelation.IS_COMPLETED
            or subgoal.action_family
            not in {
                TaskPlanActionFamily.ACTIVATE,
                TaskPlanActionFamily.POINT_ACTIVATE,
            }
        ):
            return TerminalEffectBindingResolution()
        subject_tokens = planning_semantic_tokens(subgoal.outcome.subject)
        if not subject_tokens:
            return TerminalEffectBindingResolution()
        matches = tuple(
            item
            for item in unified_affordances
            if planning_semantic_tokens(item.label) == subject_tokens
            and _supports_terminal_family(item, subgoal.action_family)
        )
        if not matches:
            return TerminalEffectBindingResolution()
        if len(matches) != 1:
            return TerminalEffectBindingResolution(
                unresolved_target_ids=tuple(item.semantic_target_id for item in matches)
            )
        target = matches[0]
        current_candidates = tuple(
            item
            for item in target.grounding_candidates
            if item.is_current(observation)
            and _candidate_supports_terminal_family(item.supported_actions, subgoal.action_family)
        )
        if len(current_candidates) != 1:
            return TerminalEffectBindingResolution(
                unresolved_target_ids=(target.semantic_target_id,)
            )
        candidate = current_candidates[0]
        return TerminalEffectBindingResolution(
            bindings=(
                TerminalEffectBinding(
                    semantic_target_id=target.semantic_target_id,
                    candidate_id=candidate.candidate_id,
                    subgoal_id=subgoal.subgoal_id,
                    task_revision=plan.task_revision,
                    observation_epoch_id=observation.snapshot_id,
                    target_fingerprint=candidate.target_fingerprint,
                ),
            )
        )


@dataclass(frozen=True)
class TaskObligationView:
    """Compiler output consumed by the readiness evaluator without inference."""

    candidates: tuple[TerminalCandidate, ...]
    obligations: tuple[TaskObligationEvidence, ...]


@dataclass(frozen=True)
class TaskObligationViewCompiler:
    """Bind validated TaskPlan dependencies and completed evidence to terminals."""

    def compile(
        self,
        *,
        plan: TaskPlan,
        progress: PlanProgress,
        bindings: tuple[TerminalEffectBinding, ...],
        task_revision: int,
        observation_epoch_id: str,
        target_fingerprints: dict[str, str],
    ) -> TaskObligationView:
        if task_revision < 1 or not observation_epoch_id:
            raise ValueError("task obligation compilation requires current identity")
        target_ids = [item.semantic_target_id for item in bindings]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("terminal effect bindings must have unique targets")
        subgoal_by_id = {item.subgoal_id: item for item in plan.subgoals}
        evidence_by_id: dict[str, TaskObligationEvidence] = {}
        candidates: list[TerminalCandidate] = []
        for binding in bindings:
            current = (
                plan.task_revision == task_revision
                and binding.task_revision == task_revision
                and binding.observation_epoch_id == observation_epoch_id
                and target_fingerprints.get(binding.candidate_id)
                == binding.target_fingerprint
            )
            terminal_subgoal = subgoal_by_id.get(binding.subgoal_id)
            if not current or terminal_subgoal is None or terminal_subgoal.outcome is None:
                candidates.append(TerminalCandidate(binding.semantic_target_id))
                continue
            prerequisite_ids, complete = _transitive_prerequisites(
                binding.subgoal_id,
                subgoal_by_id,
            )
            for obligation_id in prerequisite_ids:
                if obligation_id in evidence_by_id:
                    continue
                subgoal = subgoal_by_id.get(obligation_id)
                if subgoal is None or subgoal.outcome is None:
                    complete = False
                    continue
                evidence_refs = tuple(progress.evidence_by_subgoal.get(obligation_id, ()))
                completed = obligation_id in progress.completed_subgoal_ids
                state = (
                    ObligationState.SATISFIED
                    if completed and evidence_refs
                    else ObligationState.UNKNOWN
                    if completed
                    else ObligationState.OPEN
                )
                evidence_by_id[obligation_id] = TaskObligationEvidence(
                    obligation_id,
                    state,
                    task_revision,
                    verification_refs=evidence_refs,
                )
            candidates.append(
                TerminalCandidate(
                    binding.semantic_target_id,
                    prerequisite_ids,
                    dependencies_complete=complete,
                )
            )
        return TaskObligationView(tuple(candidates), tuple(evidence_by_id.values()))


@dataclass(frozen=True)
class TerminalCandidateDecision:
    semantic_target_id: str
    status: TerminalReadinessStatus
    blocking_obligation_ids: tuple[str, ...] = ()
    unknown_obligation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TerminalReadinessDecision:
    """Narrowing result; only READY candidates may remain planner-visible."""

    candidates: tuple[TerminalCandidateDecision, ...]

    @property
    def ready_target_ids(self) -> tuple[str, ...]:
        return tuple(
            item.semantic_target_id
            for item in self.candidates
            if item.status == TerminalReadinessStatus.READY
        )

    @property
    def blocked_target_ids(self) -> tuple[str, ...]:
        return tuple(
            item.semantic_target_id
            for item in self.candidates
            if item.status != TerminalReadinessStatus.READY
        )


@dataclass(frozen=True)
class TerminalReadinessEvaluator:
    """Admit terminals only from complete, current typed dependency evidence."""

    def evaluate(
        self,
        *,
        task_revision: int,
        observation_epoch_id: str,
        candidates: tuple[TerminalCandidate, ...],
        obligations: tuple[TaskObligationEvidence, ...],
    ) -> TerminalReadinessDecision:
        if task_revision < 1 or not observation_epoch_id:
            raise ValueError("terminal readiness requires current task and observation identity")
        obligation_by_id = {item.obligation_id: item for item in obligations}
        if len(obligation_by_id) != len(obligations):
            raise ValueError("terminal obligation evidence ids must be unique")
        decisions = tuple(
            self._evaluate_candidate(
                candidate,
                obligation_by_id,
                task_revision=task_revision,
                observation_epoch_id=observation_epoch_id,
            )
            for candidate in candidates
        )
        return TerminalReadinessDecision(decisions)

    @staticmethod
    def _evaluate_candidate(
        candidate: TerminalCandidate,
        obligation_by_id: dict[str, TaskObligationEvidence],
        *,
        task_revision: int,
        observation_epoch_id: str,
    ) -> TerminalCandidateDecision:
        if not candidate.dependencies_complete:
            return TerminalCandidateDecision(
                candidate.semantic_target_id,
                TerminalReadinessStatus.UNKNOWN,
                unknown_obligation_ids=candidate.prerequisite_obligation_ids,
            )
        blocking: list[str] = []
        unknown: list[str] = []
        for obligation_id in candidate.prerequisite_obligation_ids:
            evidence = obligation_by_id.get(obligation_id)
            if evidence is None or evidence.state == ObligationState.UNKNOWN:
                unknown.append(obligation_id)
                continue
            if evidence.task_revision != task_revision:
                unknown.append(obligation_id)
                continue
            if (
                evidence.require_current_epoch
                and evidence.observation_epoch_id != observation_epoch_id
            ):
                unknown.append(obligation_id)
                continue
            if evidence.state == ObligationState.OPEN:
                blocking.append(obligation_id)
        status = (
            TerminalReadinessStatus.UNKNOWN
            if unknown
            else TerminalReadinessStatus.BLOCKED
            if blocking
            else TerminalReadinessStatus.READY
        )
        return TerminalCandidateDecision(
            candidate.semantic_target_id,
            status,
            tuple(blocking),
            tuple(unknown),
        )


def _transitive_prerequisites(
    subgoal_id: str,
    subgoal_by_id: dict[str, SubgoalSpec],
) -> tuple[tuple[str, ...], bool]:
    ordered: list[str] = []
    visiting: set[str] = set()
    complete = True

    def visit(identifier: str) -> None:
        nonlocal complete
        if identifier in visiting:
            complete = False
            return
        subgoal = subgoal_by_id.get(identifier)
        if subgoal is None:
            complete = False
            return
        dependencies = subgoal.depends_on
        visiting.add(identifier)
        for dependency in dependencies:
            if dependency not in subgoal_by_id:
                complete = False
                continue
            visit(dependency)
            if dependency not in ordered:
                ordered.append(dependency)
        visiting.remove(identifier)

    visit(subgoal_id)
    return tuple(ordered), complete


def _active_subgoal(plan: TaskPlan, progress: PlanProgress) -> SubgoalSpec | None:
    unavailable = set(progress.completed_subgoal_ids) | set(progress.failed_subgoal_ids)
    if progress.active_subgoal_id:
        active = next(
            (
                item
                for item in plan.subgoals
                if item.subgoal_id == progress.active_subgoal_id
                and item.subgoal_id not in unavailable
            ),
            None,
        )
        if active is not None:
            return active
    return next(
        (
            item
            for item in plan.subgoals
            if item.subgoal_id not in unavailable
            and all(dependency in progress.completed_subgoal_ids for dependency in item.depends_on)
        ),
        None,
    )


def _supports_terminal_family(
    target: UnifiedAffordance,
    family: TaskPlanActionFamily,
) -> bool:
    return _candidate_supports_terminal_family(target.supported_actions, family)


def _candidate_supports_terminal_family(
    supported_actions: frozenset[str],
    family: TaskPlanActionFamily,
) -> bool:
    compatible = {
        TaskPlanActionFamily.ACTIVATE: {
            "activate",
            "click",
            "download",
            "invoke",
            "write_property",
        },
        TaskPlanActionFamily.POINT_ACTIVATE: {"point_activate"},
    }
    return bool(supported_actions.intersection(compatible.get(family, set())))

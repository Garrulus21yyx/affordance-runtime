"""Typed, provider-neutral admission for task-terminal candidates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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

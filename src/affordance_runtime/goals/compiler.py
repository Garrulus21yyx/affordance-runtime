"""Sparse GoalCompiler port and tolerant GoalPlan validation boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from affordance_runtime.goals.plan import (
    Failed,
    GoalCompilerOutcome,
    GoalPlan,
    GoalPlanItem,
    GoalPlanProposal,
    GoalPlanResolution,
    NeedsInput,
    NotRequired,
    Ready,
    Unsupported,
)
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation


class GoalCompileTrigger(StrEnum):
    TASK_START = "task_start"
    TASK_REVISION = "task_revision"


@dataclass(frozen=True)
class GoalCompilerRequest:
    task: TaskGoal
    initial_evidence: WorldObservation | None = None
    repair_errors: tuple[str, ...] = ()
    attempt: int = 0
    trigger: GoalCompileTrigger = GoalCompileTrigger.TASK_START

    def __post_init__(self) -> None:
        if self.initial_evidence is not None and not isinstance(self.initial_evidence, WorldObservation):
            raise TypeError("goal compiler initial evidence must be a WorldObservation")
        if self.attempt not in {0, 1}:
            raise ValueError("goal compiler permits at most one contract repair")
        if not isinstance(self.trigger, GoalCompileTrigger):
            raise TypeError("goal compiler trigger must be typed")
        object.__setattr__(self, "repair_errors", tuple(self.repair_errors))


class GoalCompiler(Protocol):
    async def compile(self, request: GoalCompilerRequest) -> GoalCompilerOutcome: ...


@dataclass(frozen=True)
class NotRequiredGoalCompiler:
    reason: str = "atomic_task"

    async def compile(self, request: GoalCompilerRequest) -> GoalCompilerOutcome:
        return NotRequired(request.task.revision, self.reason)


@dataclass(frozen=True)
class UnavailableGoalCompiler:
    async def compile(self, request: GoalCompilerRequest) -> GoalCompilerOutcome:
        return Failed(request.task.revision, "goal_compiler_not_configured")


class InvalidGoalProposal(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


@dataclass(frozen=True)
class GoalPlanBoundary:
    """Validate only bounded plan shape; never interpret GUI/world semantics."""

    async def resolve(
        self,
        compiler: GoalCompiler,
        task: TaskGoal,
        initial_evidence: WorldObservation | None = None,
        *,
        next_plan_version: int,
        trigger: GoalCompileTrigger = GoalCompileTrigger.TASK_START,
    ) -> GoalPlanResolution:
        request = GoalCompilerRequest(task, initial_evidence, trigger=trigger)
        for attempt in range(2):
            try:
                outcome = await compiler.compile(request)
            except Exception:
                return Failed(task.revision, "goal_compiler_call_failed")
            if isinstance(outcome, GoalPlanProposal):
                try:
                    plan = self.accept(outcome, task, plan_version=next_plan_version)
                except (InvalidGoalProposal, KeyError, TypeError, ValueError) as exc:
                    issues = exc.issues if isinstance(exc, InvalidGoalProposal) else ("goal_plan_contract_invalid",)
                    if attempt == 0:
                        request = GoalCompilerRequest(task, initial_evidence, issues, attempt=1, trigger=trigger)
                        continue
                    return Failed(task.revision, "invalid_goal_plan")
                return Ready(task.revision, plan)
            if isinstance(outcome, (NotRequired, NeedsInput, Unsupported, Failed)):
                if outcome.task_revision != task.revision:
                    return Failed(task.revision, "goal_compiler_revision_mismatch")
                if attempt == 1 and not isinstance(outcome, Failed):
                    return Failed(task.revision, "invalid_goal_plan")
                return outcome
            return Failed(task.revision, "invalid_goal_compiler_outcome")
        return Failed(task.revision, "invalid_goal_plan")

    def accept(self, proposal: GoalPlanProposal, task: TaskGoal, *, plan_version: int) -> GoalPlan:
        if proposal.task_revision != task.revision:
            raise InvalidGoalProposal(("goal_plan_task_revision_mismatch",))
        items: list[GoalPlanItem] = []
        for raw in proposal.items:
            if not isinstance(raw, Mapping):
                raise InvalidGoalProposal(("goal_plan_item_invalid",))
            try:
                depends_on = raw.get("depends_on", ())
                if not isinstance(depends_on, (tuple, list)):
                    raise TypeError
                item = GoalPlanItem(
                    id=raw["id"],
                    objective=raw["objective"],
                    done_when=raw["done_when"],
                    depends_on=tuple(depends_on),
                    final=raw.get("final", False),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise InvalidGoalProposal(("goal_plan_item_invalid",)) from exc
            items.append(item)
        try:
            return GoalPlan(task.revision, plan_version, tuple(items))
        except (TypeError, ValueError) as exc:
            raise InvalidGoalProposal(("goal_plan_contract_invalid",)) from exc


TaskSemanticsBoundary = GoalPlanBoundary

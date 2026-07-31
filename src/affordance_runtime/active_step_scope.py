"""Pure active-step proposal scope evaluation.

SAR-5 foundation only. This module evaluates whether a semantic planner
proposal is scoped to the Runtime-owned active step view. It does not bind
contracts, mutate state, write trace, or decide progress/finish.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from affordance_runtime.simplified_runtime_contracts import (
    CollectionIntent,
    ElementIntent,
    RelationIntent,
    StepActivityStatus,
    StepSpec,
)

_TARGET_ACTIONS = {
    "activate",
    "point_activate",
    "type_text",
    "select_option",
    "press_key",
    "drag",
}


@dataclass(frozen=True)
class ActiveStepScopeDecision:
    allowed: bool
    reason_code: str
    blocking_step_id: str = ""

    def __post_init__(self) -> None:
        _require_nonblank("reason_code", self.reason_code)
        if self.blocking_step_id:
            _require_nonblank("blocking_step_id", self.blocking_step_id)
        if self.allowed and self.blocking_step_id:
            raise ValueError("allowed scope decision cannot carry blocking step")


@dataclass(frozen=True)
class ActiveStepScope:
    task_revision: int
    evaluated_at_state_version: int
    snapshot_id: str
    activity_status: StepActivityStatus
    active_step_id: str | None
    permitted_target_ids: tuple[str, ...] = ()
    permitted_action_kinds: tuple[str, ...] = ()
    permitted_destination_ids: tuple[str, ...] = ()
    finish_allowed: bool = False

    @classmethod
    def from_active_step(
        cls,
        *,
        task_revision: int,
        evaluated_at_state_version: int,
        snapshot_id: str,
        step: StepSpec,
        activity_status: StepActivityStatus,
    ) -> "ActiveStepScope":
        if activity_status != StepActivityStatus.ACTIVE:
            raise ValueError("active step scope requires active status")
        return cls(
            task_revision=task_revision,
            evaluated_at_state_version=evaluated_at_state_version,
            snapshot_id=snapshot_id,
            activity_status=activity_status,
            active_step_id=step.step_id,
            permitted_target_ids=_interaction_target_ids(step),
            permitted_destination_ids=_interaction_destination_ids(step),
        )

    @classmethod
    def no_active_step(
        cls,
        *,
        task_revision: int,
        evaluated_at_state_version: int,
        snapshot_id: str,
        activity_status: StepActivityStatus,
    ) -> "ActiveStepScope":
        if activity_status == StepActivityStatus.ACTIVE:
            raise ValueError("active status requires active step")
        return cls(
            task_revision=task_revision,
            evaluated_at_state_version=evaluated_at_state_version,
            snapshot_id=snapshot_id,
            activity_status=activity_status,
            active_step_id=None,
        )

    def __post_init__(self) -> None:
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.evaluated_at_state_version < 0:
            raise ValueError("state version cannot be negative")
        _require_nonblank("snapshot_id", self.snapshot_id)
        if not isinstance(self.activity_status, StepActivityStatus):
            raise ValueError("unsupported step activity status")
        if self.activity_status == StepActivityStatus.ACTIVE:
            if self.active_step_id is None:
                raise ValueError("active status requires active step")
            _require_nonblank("active_step_id", self.active_step_id)
        elif self.active_step_id is not None:
            raise ValueError("inactive scope cannot carry active step")
        _require_tuple("permitted_target_ids", self.permitted_target_ids)
        _require_tuple("permitted_action_kinds", self.permitted_action_kinds)
        _require_tuple("permitted_destination_ids", self.permitted_destination_ids)
        _require_unique_nonblank("permitted target ids", self.permitted_target_ids)
        _require_unique_nonblank("permitted action kinds", self.permitted_action_kinds)
        _require_unique_nonblank("permitted destination ids", self.permitted_destination_ids)
        if not isinstance(self.finish_allowed, bool):
            raise ValueError("finish_allowed must be boolean")

    def evaluate(self, proposal: Any) -> ActiveStepScopeDecision:
        if proposal.based_on_task_revision != self.task_revision:
            return ActiveStepScopeDecision(False, "stale_task_revision")
        if proposal.based_on_state_version != self.evaluated_at_state_version:
            return ActiveStepScopeDecision(False, "stale_state_version")
        if proposal.snapshot_id != self.snapshot_id:
            return ActiveStepScopeDecision(False, "stale_snapshot")
        action_kind = getattr(proposal.action_kind, "value", proposal.action_kind)
        if action_kind == "finish":
            if self.finish_allowed:
                return ActiveStepScopeDecision(True, "finish_within_active_step_scope")
            return ActiveStepScopeDecision(False, "finish_outside_active_step")
        if action_kind not in _TARGET_ACTIONS:
            return ActiveStepScopeDecision(True, "non_target_action")
        if self.active_step_id is None:
            return ActiveStepScopeDecision(False, "no_active_step")
        if proposal.target_affordance_id not in self.permitted_target_ids:
            return ActiveStepScopeDecision(
                False,
                "target_outside_active_step",
                blocking_step_id=self.active_step_id,
            )
        if self.permitted_action_kinds and action_kind not in self.permitted_action_kinds:
            return ActiveStepScopeDecision(
                False,
                "action_outside_active_step",
                blocking_step_id=self.active_step_id,
            )
        destination_id = getattr(proposal, "destination_affordance_id", "")
        if action_kind == "drag" and self.permitted_destination_ids:
            if destination_id not in self.permitted_destination_ids:
                return ActiveStepScopeDecision(
                    False,
                    "destination_outside_active_step",
                    blocking_step_id=self.active_step_id,
                )
        return ActiveStepScopeDecision(True, "within_active_step_scope")


def _interaction_target_ids(step: StepSpec) -> tuple[str, ...]:
    interaction = step.interaction
    if isinstance(interaction, RelationIntent):
        if interaction.relation == "value_transfer":
            return (interaction.destination.target,)
        return (interaction.source.target,)
    if isinstance(interaction, CollectionIntent):
        return (interaction.collection.target,)
    if isinstance(interaction, ElementIntent):
        return (interaction.target,)
    return ()


def _interaction_destination_ids(step: StepSpec) -> tuple[str, ...]:
    interaction = step.interaction
    if isinstance(interaction, RelationIntent):
        return (interaction.destination.target,)
    return ()


def _require_nonblank(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} cannot be blank")


def _require_tuple(label: str, value: object) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be an immutable tuple")


def _require_no_blank_values(label: str, values: tuple[str, ...]) -> None:
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} cannot contain blank values")


def _require_unique_nonblank(label: str, values: tuple[str, ...]) -> None:
    _require_no_blank_values(label, values)
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")

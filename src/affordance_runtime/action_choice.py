"""Runtime-owned action choice construction for active-step execution.

This module is intentionally pure. It builds bounded semantic action choices
from the current active step and immutable observation, but it does not call a
Planner, construct an ActionContract, choose a backend, mutate StateKernel, or
write trace.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Awaitable, Protocol, TypeAlias, cast

from affordance_runtime.active_step_scope import ActiveStepScope
from affordance_runtime.immutable import FrozenDict, freeze_json, to_json_compatible
from affordance_runtime.interaction_grounding import (
    GroundingResult,
    GroundingRole,
    GroundingStatus,
    GroundingTarget,
    InteractionGrounder,
)
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.recovery_protocol import FailureKind, FailureOwner
from affordance_runtime.semantics import CriterionRelation
from affordance_runtime.simplified_runtime_contracts import (
    CollectionIntent,
    ElementIntent,
    ElementOperationKind,
    RelationIntent,
    StateCriterion,
    StepSpec,
)
from affordance_runtime.unified_observation import (
    UnifiedObservation,
    UnifiedObservationTarget,
)


class ChoiceSource(StrEnum):
    RUNTIME = "runtime"


class ChoiceRole(StrEnum):
    DIRECT = "direct"
    ENABLING = "enabling"
    INFORMATION = "information"


FrozenJsonObject: TypeAlias = FrozenDict
ActionChoiceBuildResult: TypeAlias = "ActionChoiceSet | ActionChoiceFailure"


@dataclass(frozen=True)
class ActionChoice:
    choice_id: str
    task_revision: int
    state_version: int
    snapshot_id: str
    active_step_id: str
    action_kind: PlannerActionKind
    target_id: str = ""
    destination_id: str = ""
    parameters: FrozenJsonObject = field(default_factory=lambda: FrozenDict({}))
    criterion_ids: tuple[str, ...] = ()
    role: ChoiceRole = ChoiceRole.DIRECT
    source: ChoiceSource = ChoiceSource.RUNTIME

    def __init__(
        self,
        *,
        choice_id: str,
        task_revision: int,
        state_version: int,
        snapshot_id: str,
        active_step_id: str,
        action_kind: PlannerActionKind,
        target_id: str = "",
        destination_id: str = "",
        parameters: dict[str, object] | FrozenJsonObject | None = None,
        criterion_ids: tuple[str, ...] = (),
        role: ChoiceRole = ChoiceRole.DIRECT,
        source: ChoiceSource = ChoiceSource.RUNTIME,
    ) -> None:
        object.__setattr__(self, "choice_id", choice_id)
        object.__setattr__(self, "task_revision", task_revision)
        object.__setattr__(self, "state_version", state_version)
        object.__setattr__(self, "snapshot_id", snapshot_id)
        object.__setattr__(self, "active_step_id", active_step_id)
        object.__setattr__(self, "action_kind", action_kind)
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(self, "destination_id", destination_id)
        object.__setattr__(
            self,
            "parameters",
            parameters if isinstance(parameters, FrozenDict) else FrozenDict(parameters or {}),
        )
        object.__setattr__(self, "criterion_ids", tuple(criterion_ids))
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "source", source)
        self.__post_init__()

    def __post_init__(self) -> None:
        _require_nonblank("choice_id", self.choice_id)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.state_version < 0:
            raise ValueError("state version cannot be negative")
        _require_nonblank("snapshot_id", self.snapshot_id)
        _require_nonblank("active_step_id", self.active_step_id)
        if not isinstance(self.action_kind, PlannerActionKind):
            raise ValueError("unsupported action kind")
        if self.target_id:
            _require_nonblank("target_id", self.target_id)
        if self.destination_id:
            _require_nonblank("destination_id", self.destination_id)
        if not isinstance(self.parameters, FrozenDict):
            raise ValueError("choice parameters must be deeply immutable")
        _require_tuple("criterion_ids", self.criterion_ids)
        _require_unique_nonblank("criterion ids", self.criterion_ids)
        if not isinstance(self.role, ChoiceRole):
            raise ValueError("unsupported choice role")
        if not isinstance(self.source, ChoiceSource):
            raise ValueError("unsupported choice source")


@dataclass(frozen=True)
class ActionChoiceSet:
    task_revision: int
    state_version: int
    snapshot_id: str
    active_step_id: str
    grounding: GroundingResult
    choices: tuple[ActionChoice, ...]

    def __post_init__(self) -> None:
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.state_version < 0:
            raise ValueError("state version cannot be negative")
        _require_nonblank("snapshot_id", self.snapshot_id)
        _require_nonblank("active_step_id", self.active_step_id)
        if self.grounding.status != GroundingStatus.RESOLVED:
            raise ValueError("action choice set requires resolved grounding")
        _require_tuple("choices", self.choices)
        if not self.choices:
            raise ValueError("action choice set cannot be empty")
        choice_ids = tuple(item.choice_id for item in self.choices)
        _require_unique_nonblank("choice ids", choice_ids)
        for choice in self.choices:
            if choice.task_revision != self.task_revision:
                raise ValueError("choice task revision mismatch")
            if choice.state_version != self.state_version:
                raise ValueError("choice state version mismatch")
            if choice.snapshot_id != self.snapshot_id:
                raise ValueError("choice snapshot mismatch")
            if choice.active_step_id != self.active_step_id:
                raise ValueError("choice active step mismatch")


@dataclass(frozen=True)
class ActionChoiceFailure:
    kind: FailureKind
    reason_code: str
    owner: FailureOwner = FailureOwner.RUNTIME_RECOVERY

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FailureKind):
            raise ValueError("unsupported failure kind")
        _require_nonblank("reason_code", self.reason_code)
        if not isinstance(self.owner, FailureOwner):
            raise ValueError("unsupported failure owner")


@dataclass(frozen=True)
class ActionSelection:
    choice_id: str
    task_revision: int
    state_version: int
    snapshot_id: str
    active_step_id: str
    reason_summary: str = ""

    def __post_init__(self) -> None:
        _require_nonblank("choice_id", self.choice_id)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.state_version < 0:
            raise ValueError("state version cannot be negative")
        _require_nonblank("snapshot_id", self.snapshot_id)
        _require_nonblank("active_step_id", self.active_step_id)
        if self.reason_summary:
            _require_nonblank("reason_summary", self.reason_summary)


@dataclass(frozen=True)
class ChoicePlanningRequest:
    task_revision: int
    state_version: int
    snapshot_id: str
    active_step_id: str
    grounding: GroundingResult
    choices: tuple[ActionChoice, ...]

    @classmethod
    def from_choice_set(cls, choices: ActionChoiceSet) -> "ChoicePlanningRequest":
        return cls(
            task_revision=choices.task_revision,
            state_version=choices.state_version,
            snapshot_id=choices.snapshot_id,
            active_step_id=choices.active_step_id,
            grounding=choices.grounding,
            choices=choices.choices,
        )

    def __post_init__(self) -> None:
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.state_version < 0:
            raise ValueError("state version cannot be negative")
        _require_nonblank("snapshot_id", self.snapshot_id)
        _require_nonblank("active_step_id", self.active_step_id)
        _require_tuple("choices", self.choices)
        if len(self.choices) < 2:
            raise ValueError("choice planning request requires multiple choices")
        for choice in self.choices:
            if choice.task_revision != self.task_revision:
                raise ValueError("choice request task revision mismatch")
            if choice.state_version != self.state_version:
                raise ValueError("choice request state version mismatch")
            if choice.snapshot_id != self.snapshot_id:
                raise ValueError("choice request snapshot mismatch")
            if choice.active_step_id != self.active_step_id:
                raise ValueError("choice request active step mismatch")


class StepChoicePlannerPort(Protocol):
    def select(
        self,
        request: ChoicePlanningRequest,
    ) -> ActionSelection | Awaitable[ActionSelection]: ...


class ActionSelectionValidator:
    def validate(
        self,
        selection: ActionSelection,
        choices: ActionChoiceSet,
    ) -> ActionChoice:
        if selection.task_revision != choices.task_revision:
            raise ValueError("stale action selection task revision")
        if selection.state_version != choices.state_version:
            raise ValueError("stale action selection state version")
        if selection.snapshot_id != choices.snapshot_id:
            raise ValueError("stale action selection snapshot")
        if selection.active_step_id != choices.active_step_id:
            raise ValueError("stale action selection active step")
        by_id = {choice.choice_id: choice for choice in choices.choices}
        choice = by_id.get(selection.choice_id)
        if choice is None:
            raise ValueError("unknown choice_id")
        return choice


class ActionChoiceDispatcher:
    def choose(
        self,
        result: ActionChoiceBuildResult,
        *,
        planner: StepChoicePlannerPort,
    ) -> ActionSelection | ActionChoiceFailure | Awaitable[ActionSelection | ActionChoiceFailure]:
        if isinstance(result, ActionChoiceFailure):
            return result
        if len(result.choices) == 1:
            choice = result.choices[0]
            return ActionSelection(
                choice_id=choice.choice_id,
                task_revision=choice.task_revision,
                state_version=choice.state_version,
                snapshot_id=choice.snapshot_id,
                active_step_id=choice.active_step_id,
                reason_summary="runtime_unique_choice",
            )
        request = ChoicePlanningRequest.from_choice_set(result)
        selection = planner.select(request)
        if hasattr(selection, "__await__"):
            return _await_validated_selection(cast(Awaitable[ActionSelection], selection), result)
        try:
            ActionSelectionValidator().validate(selection, result)
        except ValueError:
            return ActionChoiceFailure(
                kind=FailureKind.MODEL_DEFERRAL_WITH_ACTION_SPACE,
                reason_code="invalid_action_choice_selection",
            )
        return selection


async def _await_validated_selection(
    selection: Awaitable[ActionSelection],
    choices: ActionChoiceSet,
) -> ActionSelection | ActionChoiceFailure:
    try:
        resolved = await selection
    except ValueError:
        return ActionChoiceFailure(
            kind=FailureKind.MODEL_DEFERRAL_WITH_ACTION_SPACE,
            reason_code="invalid_action_choice_selection",
        )
    try:
        ActionSelectionValidator().validate(resolved, choices)
    except ValueError:
        return ActionChoiceFailure(
            kind=FailureKind.MODEL_DEFERRAL_WITH_ACTION_SPACE,
            reason_code="invalid_action_choice_selection",
        )
    return resolved


class ActionChoiceBuilder:
    def build(
        self,
        *,
        task_revision: int,
        state_version: int,
        step: StepSpec,
        scope: ActiveStepScope,
        observation: UnifiedObservation,
    ) -> ActionChoiceBuildResult:
        stale_reason = _validate_scope_identity(
            task_revision=task_revision,
            state_version=state_version,
            step=step,
            scope=scope,
            observation=observation,
        )
        if stale_reason:
            return ActionChoiceFailure(
                kind=FailureKind.AUTHORITY_BLOCKED,
                reason_code=stale_reason,
                owner=FailureOwner.TERMINAL,
            )
        if scope.active_step_id is None:
            return ActionChoiceFailure(
                kind=FailureKind.NO_FEASIBLE_ACTION,
                reason_code="no_active_step",
            )

        targets = {item.target_id: item for item in observation.targets}
        grounding = InteractionGrounder().ground(
            step.interaction,
            tuple(_grounding_target(item) for item in observation.targets),
        )
        if grounding.status != GroundingStatus.RESOLVED:
            return ActionChoiceFailure(
                kind=(
                    FailureKind.CAPABILITY_MISSING
                    if grounding.status == GroundingStatus.CAPABILITY_MISSING
                    else FailureKind.GROUNDING_AMBIGUOUS
                ),
                reason_code=grounding.reason_code or "interaction_grounding_failed",
                owner=FailureOwner.STEP_PLANNER,
            )
        choices: list[ActionChoice] = []
        criteria = tuple(
            item for item in step.completion_criteria if isinstance(item, StateCriterion)
        )
        criterion_ids = tuple(item.criterion_id for item in criteria)
        if grounding.role == GroundingRole.ENABLING:
            target = targets.get(grounding.targets[0].target_id)
            enabler = step.interaction.enabler if isinstance(step.interaction, ElementIntent) else None
            if target is not None and enabler is not None:
                choice = _element_operation_choice(
                    task_revision=task_revision,
                    state_version=state_version,
                    snapshot_id=observation.snapshot_id,
                    step_id=step.step_id,
                    intent=enabler,
                    target=target,
                    role=ChoiceRole.ENABLING,
                )
                if choice is not None:
                    choices.append(choice)
        elif isinstance(step.interaction, CollectionIntent):
            target = targets.get(grounding.targets[0].target_id)
            if target is not None and _supports(target, PlannerActionKind.SELECT_OPTION):
                choices.append(
                    _make_choice(
                        task_revision=task_revision,
                        state_version=state_version,
                        snapshot_id=observation.snapshot_id,
                        step_id=step.step_id,
                        action_kind=PlannerActionKind.SELECT_OPTION,
                        target_id=target.target_id,
                        parameters=dict(grounding.parameters),
                        criterion_ids=criterion_ids,
                    )
                )
        elif isinstance(step.interaction, RelationIntent):
            source = targets.get(grounding.targets[0].target_id)
            destination = targets.get(grounding.destinations[0].target_id)
            if (
                source is not None
                and destination is not None
                and _supports(source, PlannerActionKind.DRAG)
            ):
                choices.append(
                    _make_choice(
                        task_revision=task_revision,
                        state_version=state_version,
                        snapshot_id=observation.snapshot_id,
                        step_id=step.step_id,
                        action_kind=PlannerActionKind.DRAG,
                        target_id=source.target_id,
                        destination_id=destination.target_id,
                        parameters={},
                        criterion_ids=criterion_ids,
                    )
                )
        elif (
            isinstance(step.interaction, ElementIntent)
            and step.interaction.operation != ElementOperationKind.AUTO
        ):
            target = targets.get(grounding.targets[0].target_id)
            if target is not None:
                choice = _element_operation_choice(
                    task_revision=task_revision,
                    state_version=state_version,
                    snapshot_id=observation.snapshot_id,
                    step_id=step.step_id,
                    intent=step.interaction,
                    target=target,
                    role=ChoiceRole.DIRECT,
                    criterion_ids=criterion_ids,
                )
                if choice is not None:
                    choices.append(choice)
        else:
            grounded_targets = tuple(
                targets[item.target_id]
                for item in grounding.targets
                if item.target_id in targets
            )
            for criterion in criteria:
                for target in grounded_targets:
                    choice = _choice_for_criterion(
                        task_revision=task_revision,
                        state_version=state_version,
                        snapshot_id=observation.snapshot_id,
                        step_id=step.step_id,
                        criterion=criterion,
                        target=target,
                    )
                    if choice is not None:
                        choices.append(choice)

        choices = _coalesce_semantic_choices(choices)
        if not choices:
            return ActionChoiceFailure(
                kind=FailureKind.NO_FEASIBLE_ACTION,
                reason_code="no_feasible_action_choice",
            )
        return ActionChoiceSet(
            task_revision=task_revision,
            state_version=state_version,
            snapshot_id=observation.snapshot_id,
            active_step_id=step.step_id,
            grounding=grounding,
            choices=tuple(choices),
        )


def _coalesce_semantic_choices(choices: list[ActionChoice]) -> list[ActionChoice]:
    grouped: dict[tuple[object, ...], list[ActionChoice]] = {}
    for choice in choices:
        key = (
            choice.task_revision,
            choice.state_version,
            choice.snapshot_id,
            choice.active_step_id,
            choice.action_kind,
            choice.target_id,
            choice.destination_id,
            choice.role,
            json.dumps(
                to_json_compatible(choice.parameters),
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        grouped.setdefault(key, []).append(choice)
    return [
        _make_choice(
            task_revision=members[0].task_revision,
            state_version=members[0].state_version,
            snapshot_id=members[0].snapshot_id,
            step_id=members[0].active_step_id,
            action_kind=members[0].action_kind,
            target_id=members[0].target_id,
            destination_id=members[0].destination_id,
            parameters=dict(members[0].parameters),
            criterion_ids=tuple(
                dict.fromkeys(
                    criterion_id
                    for member in members
                    for criterion_id in member.criterion_ids
                )
            ),
            role=members[0].role,
        )
        for members in grouped.values()
    ]


def _choice_for_criterion(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    criterion: StateCriterion,
    target: UnifiedObservationTarget,
) -> ActionChoice | None:
    if target.state.get("enabled") is False or target.state.get("visible") is False:
        return None
    if criterion.relation != CriterionRelation.EQUALS:
        if criterion.relation == CriterionRelation.IS_CHECKED:
            return _checked_choice(
                task_revision=task_revision,
                state_version=state_version,
                snapshot_id=snapshot_id,
                step_id=step_id,
                criterion=criterion,
                target=target,
            )
        if criterion.relation == CriterionRelation.IS_EXPANDED:
            return _expanded_choice(
                task_revision=task_revision,
                state_version=state_version,
                snapshot_id=snapshot_id,
                step_id=step_id,
                criterion=criterion,
                target=target,
            )
        if criterion.relation == CriterionRelation.IS_SELECTED:
            return _selected_choice(
                task_revision=task_revision,
                state_version=state_version,
                snapshot_id=snapshot_id,
                step_id=step_id,
                criterion=criterion,
                target=target,
            )
        if criterion.relation == CriterionRelation.IS_COMPLETED:
            return _activation_choice(
                task_revision=task_revision,
                state_version=state_version,
                snapshot_id=snapshot_id,
                step_id=step_id,
                criterion=criterion,
                target=target,
            )
        if criterion.relation == CriterionRelation.HAS_CHANGED:
            return _changed_activation_choice(
                task_revision=task_revision,
                state_version=state_version,
                snapshot_id=snapshot_id,
                step_id=step_id,
                criterion=criterion,
                target=target,
            )
        return None
    if isinstance(criterion.expected_value, str) and _supports(
        target,
        PlannerActionKind.TYPE_TEXT,
    ):
        return _make_choice(
            task_revision=task_revision,
            state_version=state_version,
            snapshot_id=snapshot_id,
            step_id=step_id,
            action_kind=PlannerActionKind.TYPE_TEXT,
            target_id=target.target_id,
            parameters={"text": criterion.expected_value},
            criterion_ids=(criterion.criterion_id,),
        )
    numeric_expected_value = _numeric_expected_value(criterion.expected_value)
    if numeric_expected_value is not None and _supports(target, PlannerActionKind.PRESS_KEY):
        current_value = _numeric_state_value(target)
        if current_value is None and numeric_expected_value == 0:
            return None
        if current_value == numeric_expected_value:
            return None
        key = (
            "ArrowRight"
            if current_value is None and numeric_expected_value > 0
            else (
                "ArrowLeft"
                if current_value is None
                else ("ArrowRight" if numeric_expected_value > current_value else "ArrowLeft")
            )
        )
        return _make_choice(
            task_revision=task_revision,
            state_version=state_version,
            snapshot_id=snapshot_id,
            step_id=step_id,
            action_kind=PlannerActionKind.PRESS_KEY,
            target_id=target.target_id,
            parameters={"key": key},
            criterion_ids=(criterion.criterion_id,),
        )
    return None


def _grounding_target(target: UnifiedObservationTarget) -> GroundingTarget:
    return GroundingTarget(
        target_id=target.target_id,
        role=target.role,
        label=target.label,
        supported_actions=target.supported_actions,
        state=target.state,
    )


def _element_operation_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    intent: ElementIntent,
    target: UnifiedObservationTarget,
    role: ChoiceRole,
    criterion_ids: tuple[str, ...] = (),
) -> ActionChoice | None:
    if intent.operation == ElementOperationKind.AUTO:
        action_kind = PlannerActionKind.ACTIVATE
        parameters: dict[str, object] = {}
    else:
        action_kind = PlannerActionKind.PRESS_KEY
        parameters = {
            "key": (
                "PageDown"
                if intent.operation == ElementOperationKind.SCROLL_FORWARD
                else "PageUp"
            )
        }
    if not _supports(target, action_kind):
        return None
    return _make_choice(
        task_revision=task_revision,
        state_version=state_version,
        snapshot_id=snapshot_id,
        step_id=step_id,
        action_kind=action_kind,
        target_id=target.target_id,
        parameters=parameters,
        criterion_ids=criterion_ids,
        role=role,
    )


def _expanded_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    criterion: StateCriterion,
    target: UnifiedObservationTarget,
) -> ActionChoice | None:
    if target.state.get("expanded") is not False:
        return None
    return _activation_choice(
        task_revision=task_revision,
        state_version=state_version,
        snapshot_id=snapshot_id,
        step_id=step_id,
        criterion=criterion,
        target=target,
    )


def _checked_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    criterion: StateCriterion,
    target: UnifiedObservationTarget,
) -> ActionChoice | None:
    if not _supports(target, PlannerActionKind.ACTIVATE):
        return None
    if target.state.get("checked") is True:
        return None
    return _activation_choice(
        task_revision=task_revision,
        state_version=state_version,
        snapshot_id=snapshot_id,
        step_id=step_id,
        criterion=criterion,
        target=target,
    )


def _selected_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    criterion: StateCriterion,
    target: UnifiedObservationTarget,
) -> ActionChoice | None:
    if not isinstance(criterion.expected_value, str):
        return None
    if not _supports(target, PlannerActionKind.SELECT_OPTION):
        return None
    selected_value = _selected_value(target)
    if (
        selected_value is not None
        and criterion.expected_value.strip().casefold() == selected_value.strip().casefold()
    ):
        return None
    return _make_choice(
        task_revision=task_revision,
        state_version=state_version,
        snapshot_id=snapshot_id,
        step_id=step_id,
        action_kind=PlannerActionKind.SELECT_OPTION,
        target_id=target.target_id,
        parameters={"option": criterion.expected_value},
        criterion_ids=(criterion.criterion_id,),
    )


def _selected_value(target: UnifiedObservationTarget) -> str | None:
    for key in ("selected_value", "value", "current_value", "control_value"):
        value = target.state.get(key)
        if isinstance(value, str) and value.strip():
            return value
    selected = target.state.get("selected")
    if isinstance(selected, str) and selected.strip():
        return selected
    return None


def _activation_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    criterion: StateCriterion,
    target: UnifiedObservationTarget,
) -> ActionChoice | None:
    if not _supports(target, PlannerActionKind.ACTIVATE):
        return None
    return _make_choice(
        task_revision=task_revision,
        state_version=state_version,
        snapshot_id=snapshot_id,
        step_id=step_id,
        action_kind=PlannerActionKind.ACTIVATE,
        target_id=target.target_id,
        parameters={},
        criterion_ids=(criterion.criterion_id,),
    )


def _changed_activation_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    criterion: StateCriterion,
    target: UnifiedObservationTarget,
) -> ActionChoice | None:
    if _target_looks_text_entry(target) or _target_looks_slider(target):
        return None
    return _activation_choice(
        task_revision=task_revision,
        state_version=state_version,
        snapshot_id=snapshot_id,
        step_id=step_id,
        criterion=criterion,
        target=target,
    )


def _make_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    action_kind: PlannerActionKind,
    target_id: str,
    parameters: dict[str, object],
    criterion_ids: tuple[str, ...],
    destination_id: str = "",
    role: ChoiceRole = ChoiceRole.DIRECT,
) -> ActionChoice:
    payload = {
        "task_revision": task_revision,
        "state_version": state_version,
        "snapshot_id": snapshot_id,
        "active_step_id": step_id,
        "action_kind": action_kind.value,
        "target_id": target_id,
        "destination_id": destination_id,
        "parameters": to_json_compatible(freeze_json(parameters)),
        "criterion_ids": criterion_ids,
        "role": role.value,
        "source": ChoiceSource.RUNTIME.value,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ActionChoice(
        choice_id=f"choice:{digest}",
        task_revision=task_revision,
        state_version=state_version,
        snapshot_id=snapshot_id,
        active_step_id=step_id,
        action_kind=action_kind,
        target_id=target_id,
        destination_id=destination_id,
        parameters=parameters,
        criterion_ids=criterion_ids,
        role=role,
    )


def _validate_scope_identity(
    *,
    task_revision: int,
    state_version: int,
    step: StepSpec,
    scope: ActiveStepScope,
    observation: UnifiedObservation,
) -> str:
    if task_revision != scope.task_revision:
        return "stale_scope_task_revision"
    if state_version != scope.evaluated_at_state_version:
        return "stale_scope_state_version"
    if observation.snapshot_id != scope.snapshot_id:
        return "stale_scope_snapshot"
    if scope.active_step_id != step.step_id:
        return "scope_active_step_mismatch"
    return ""


def _supports(target: UnifiedObservationTarget, kind: PlannerActionKind) -> bool:
    compatible = {
        PlannerActionKind.ACTIVATE: {"activate", "click"},
        PlannerActionKind.TYPE_TEXT: {"fill", "type", "type_text"},
        PlannerActionKind.SELECT_OPTION: {"select", "select_option"},
        PlannerActionKind.PRESS_KEY: {"press", "press_key"},
    }.get(kind, set())
    return bool(compatible.intersection(target.supported_actions))


def _numeric_state_value(target: UnifiedObservationTarget) -> int | float | None:
    for key in ("value", "current_value", "aria-valuenow"):
        value = target.state.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    context_values = re.findall(
        r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])",
        str(target.state.get("context_text") or ""),
    )
    if len(context_values) == 1:
        return float(context_values[0])
    return None


def _numeric_expected_value(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d+(?:\.\d+)?", value.strip()):
        return float(value)
    return None


def _target_looks_text_entry(target: UnifiedObservationTarget) -> bool:
    role = target.role.casefold()
    input_type = str(target.state.get("input_type", "")).casefold()
    return role in {"textbox", "searchbox", "textarea"} or input_type in {
        "email",
        "number",
        "password",
        "search",
        "tel",
        "text",
        "textarea",
        "url",
    }


def _target_looks_slider(target: UnifiedObservationTarget) -> bool:
    role = target.role.casefold()
    input_type = str(target.state.get("input_type", "")).casefold()
    return role in {"slider", "range"} or input_type == "range"


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

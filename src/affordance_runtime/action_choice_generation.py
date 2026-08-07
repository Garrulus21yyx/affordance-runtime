"""Pure criterion grounding and semantic action-choice generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TypeAlias

from affordance_runtime.action_choice_generation_support import (
    _action_criteria,
    _ActionCriterion,
    _exact_transfer_value,
    _grounding_target,
    _numeric_expected_value,
    _numeric_state_value,
    _supports,
    _target_looks_slider,
    _target_looks_text_entry,
    _validate_scope_identity,
)
from affordance_runtime.active_step_scope import ActiveStepScope
from affordance_runtime.choice_contracts import (
    ActionChoice,
    ActionChoiceFailure,
    ChoiceRole,
    ChoiceSource,
)
from affordance_runtime.criteria import (
    criterion_ids as canonical_criterion_ids,
)
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.interaction_grounding import (
    GroundingResult,
    GroundingRole,
    GroundingStatus,
    InteractionGrounder,
)
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.recovery_protocol import FailureKind, FailureOwner
from affordance_runtime.semantics import CriterionRelation
from affordance_runtime.simplified_runtime_contracts import (
    CollectionIntent,
    ElementIntent,
    ElementOperationKind,
    RegionIntent,
    RelationIntent,
    StepSpec,
)
from affordance_runtime.unified_observation import (
    CanonicalTarget,
    UnifiedObservation,
)

CanonicalChoiceTarget: TypeAlias = CanonicalTarget


@dataclass(frozen=True)
class _GeneratedChoiceSet:
    grounding: GroundingResult
    choices: tuple[ActionChoice, ...]


ActionChoiceBuildResult: TypeAlias = _GeneratedChoiceSet | ActionChoiceFailure


class _SemanticChoiceGenerator:
    def build(
        self,
        *,
        task_revision: int,
        state_version: int,
        step: StepSpec,
        scope: ActiveStepScope,
        observation: UnifiedObservation,
        capabilities: frozenset[str] = frozenset(),
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
            tuple(_grounding_target(item, observation.bindings) for item in observation.targets),
            capabilities=capabilities,
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
        criterion_ids = canonical_criterion_ids(step.completion_criteria)
        criteria = tuple(item for expression in step.completion_criteria for item in _action_criteria(expression))
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
                step.interaction.relation == "value_transfer"
                and source is not None
                and destination is not None
                and source.target_id != destination.target_id
                and _supports(destination, PlannerActionKind.TYPE_TEXT)
                and (transfer_value := _exact_transfer_value(source)) is not None
            ):
                choices.append(
                    _make_choice(
                        task_revision=task_revision,
                        state_version=state_version,
                        snapshot_id=observation.snapshot_id,
                        step_id=step.step_id,
                        action_kind=PlannerActionKind.TYPE_TEXT,
                        target_id=destination.target_id,
                        parameters={"text": transfer_value},
                        criterion_ids=criterion_ids,
                    )
                )
            elif (
                step.interaction.relation != "value_transfer"
                and source is not None
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
        elif isinstance(step.interaction, RegionIntent):
            target = targets.get(grounding.targets[0].target_id)
            if target is not None and _supports(target, PlannerActionKind.POINT_ACTIVATE):
                choices.append(
                    _make_choice(
                        task_revision=task_revision,
                        state_version=state_version,
                        snapshot_id=observation.snapshot_id,
                        step_id=step.step_id,
                        action_kind=PlannerActionKind.POINT_ACTIVATE,
                        target_id=target.target_id,
                        parameters={},
                        criterion_ids=criterion_ids,
                    )
                )
        elif isinstance(step.interaction, ElementIntent) and step.interaction.operation != ElementOperationKind.AUTO:
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
            grounded_targets = tuple(targets[item.target_id] for item in grounding.targets if item.target_id in targets)
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
        return _GeneratedChoiceSet(grounding=grounding, choices=tuple(choices))


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
                dict.fromkeys(criterion_id for member in members for criterion_id in member.criterion_ids)
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
    criterion: _ActionCriterion,
    target: CanonicalChoiceTarget,
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


def _element_operation_choice(
    *,
    task_revision: int,
    state_version: int,
    snapshot_id: str,
    step_id: str,
    intent: ElementIntent,
    target: CanonicalTarget,
    role: ChoiceRole,
    criterion_ids: tuple[str, ...] = (),
) -> ActionChoice | None:
    if intent.operation == ElementOperationKind.AUTO:
        action_kind = PlannerActionKind.ACTIVATE
        parameters: dict[str, object] = {}
    elif intent.operation == ElementOperationKind.FOCUS:
        action_kind = PlannerActionKind.FOCUS
        parameters = {}
    else:
        action_kind = PlannerActionKind.PRESS_KEY
        parameters = {"key": ("PageDown" if intent.operation == ElementOperationKind.SCROLL_FORWARD else "PageUp")}
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
    criterion: _ActionCriterion,
    target: CanonicalTarget,
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
    criterion: _ActionCriterion,
    target: CanonicalTarget,
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
    criterion: _ActionCriterion,
    target: CanonicalTarget,
) -> ActionChoice | None:
    if not isinstance(criterion.expected_value, str):
        return None
    if not _supports(target, PlannerActionKind.SELECT_OPTION):
        return None
    selected_value = _selected_value(target)
    if selected_value is not None and criterion.expected_value.strip().casefold() == selected_value.strip().casefold():
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


def _selected_value(target: CanonicalTarget) -> str | None:
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
    criterion: _ActionCriterion,
    target: CanonicalTarget,
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
    criterion: _ActionCriterion,
    target: CanonicalTarget,
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
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
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

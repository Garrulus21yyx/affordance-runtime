"""Typed helpers for semantic action-choice generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypeAlias

from affordance_runtime.active_step_scope import ActiveStepScope
from affordance_runtime.criteria import (
    LiteralValue,
    PredicateExpr,
    PredicateOperator,
    criterion_nodes,
)
from affordance_runtime.grounding import GroundingCandidate
from affordance_runtime.interaction_grounding import GroundingTarget
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.semantics import CriterionRelation
from affordance_runtime.simplified_runtime_contracts import StepSpec
from affordance_runtime.unified_observation import (
    CanonicalTarget,
    UnifiedObservation,
    UnifiedObservationTarget,
)

CanonicalChoiceTarget: TypeAlias = CanonicalTarget | UnifiedObservationTarget


@dataclass(frozen=True)
class _ActionCriterion:
    criterion_id: str
    subject: str
    relation: CriterionRelation
    expected_value: object | None


def _action_criteria(expression: object) -> tuple[_ActionCriterion, ...]:
    relations = {
        PredicateOperator.EQUALS: CriterionRelation.EQUALS,
        PredicateOperator.CONTAINS: CriterionRelation.CONTAINS,
        PredicateOperator.SELECTED: CriterionRelation.IS_SELECTED,
        PredicateOperator.CHECKED: CriterionRelation.IS_CHECKED,
        PredicateOperator.CHANGED: CriterionRelation.HAS_CHANGED,
    }
    return tuple(
        _ActionCriterion(
            item.criterion_id,
            item.subject.reference,
            relations.get(item.operator, CriterionRelation.IS_COMPLETED),
            item.value.value if isinstance(item.value, LiteralValue) else None,
        )
        for item in criterion_nodes(expression)  # type: ignore[arg-type]
        if isinstance(item, PredicateExpr)
    )


def _grounding_target(
    target: CanonicalChoiceTarget,
    bindings: tuple[GroundingCandidate, ...] = (),
) -> GroundingTarget:
    if isinstance(target, CanonicalTarget):
        surface = target.surfaces[0].value if len(target.surfaces) == 1 else "multi_surface"
        target_bindings = tuple(item for item in bindings if item.semantic_target_id == target.target_id)
        confidence = None
        source_refs = tuple(
            dict.fromkeys(
                (
                    *target.source_assertion_refs,
                    *(ref for item in target_bindings for ref in item.evidence_refs),
                )
            )
        )
    else:
        surface = target.surface
        confidence = target.confidence
        source_refs = target.source_refs
    return GroundingTarget(
        target_id=target.target_id,
        role=target.role,
        label=target.label,
        supported_actions=target.supported_actions,
        state=target.state,
        surface=surface,
        confidence=confidence,
        source_refs=source_refs,
    )


def _exact_transfer_value(target: CanonicalChoiceTarget) -> str | None:
    if target.state.get("input_type") == "password":
        return None
    if "control_value_prefix" in target.state or "control_value_suffix" in target.state:
        return None
    value = target.state.get("control_value")
    if not isinstance(value, str) or not value or len(value) > 240:
        return None
    return value


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
        PlannerActionKind.FOCUS: {"focus", "fill", "type", "type_text"},
        PlannerActionKind.TYPE_TEXT: {"fill", "type", "type_text"},
        PlannerActionKind.SELECT_OPTION: {"select", "select_option"},
        PlannerActionKind.PRESS_KEY: {"press", "press_key"},
        PlannerActionKind.DRAG: {"drag"},
        PlannerActionKind.POINT_ACTIVATE: {"point_activate"},
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

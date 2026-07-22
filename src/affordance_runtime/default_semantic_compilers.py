"""Declarative assembly for the runtime's default semantic compiler profile."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.semantic_compilers import (
    SemanticCompileFn,
    SemanticCompilerContext,
    SemanticCompilerEvidence,
    SemanticCompilerRegistry,
    SemanticCompilerRule,
    SemanticConstraintFn,
    SemanticConstraintRule,
)

_OPERATION_CLASSES = (
    "read_only",
    "navigation",
    "reversible_write",
    "external_side_effect",
    "irreversible",
)
_POSTCONDITION = ("fresh independent postcondition evidence bound by ContractBuilder",)


@dataclass(frozen=True)
class DefaultSemanticCompilerCallbacks:
    """Semantic algorithms injected into the declarative default profile."""

    calendar_event: SemanticCompileFn
    copy_operation: SemanticCompileFn
    incremental_control: SemanticCompileFn
    semantic_operation: SemanticCompileFn
    planner_constraints: SemanticConstraintFn


def build_default_semantic_compiler_registry(
    callbacks: DefaultSemanticCompilerCallbacks,
) -> SemanticCompilerRegistry:
    """Build the ordered, evidence-declared default System-1 profile."""

    return SemanticCompilerRegistry(
        rules=(
            SemanticCompilerRule(
                compiler_id="authored-calendar-range-v1",
                supported_intents=("create bounded calendar event",),
                operation_classes=_OPERATION_CLASSES,
                applicability_description=(
                    "objective describes an event range and current affordances expose typed range_selectable state"
                ),
                applicability=_has_range_selectable_affordance,
                compile=callbacks.calendar_event,
                evidence=SemanticCompilerEvidence(
                    required_state_keys=("range_selectable",),
                    output_action_kinds=("drag", "type_text", "activate"),
                    verifier_requirements=_POSTCONDITION,
                    negative_examples=(
                        "ordinary lists with time-like text but no range_selectable state",
                        "ambiguous or non-half-hour event windows",
                    ),
                    source="runtime-generic-calendar-conformance",
                    version="1",
                ),
            ),
            SemanticCompilerRule(
                compiler_id="bounded-text-transform-v1",
                supported_intents=("copy or transform explicitly observed text",),
                operation_classes=_OPERATION_CLASSES,
                applicability_description=(
                    "objective requests a bounded text copy/transform and the current inventory has a writable target"
                ),
                applicability=_has_writable_affordance,
                compile=callbacks.copy_operation,
                evidence=SemanticCompilerEvidence(
                    required_state_keys=(),
                    output_action_kinds=("type_text", "activate"),
                    verifier_requirements=_POSTCONDITION,
                    negative_examples=(
                        "page text not explicitly named by the task",
                        "password or truncated content without an exact observed boundary",
                    ),
                    source="runtime-generic-text-transform-conformance",
                    version="1",
                ),
            ),
            SemanticCompilerRule(
                compiler_id="typed-incremental-control-v1",
                supported_intents=("move a typed incremental control toward an explicit value",),
                operation_classes=_OPERATION_CLASSES,
                applicability_description=(
                    "objective names one slider value and one current typed slider exposes its observed value"
                ),
                applicability=_has_one_incremental_control,
                compile=callbacks.incremental_control,
                evidence=SemanticCompilerEvidence(
                    required_state_keys=("context_text",),
                    output_action_kinds=("press_key",),
                    verifier_requirements=(
                        "fresh control-state evidence must show one value transition",
                    ),
                    negative_examples=(
                        "multiple sliders without a uniquely named target",
                        "missing, nonnumeric, or already-satisfied target value",
                    ),
                    source="runtime-generic-incremental-control-conformance",
                    version="1",
                ),
            ),
            SemanticCompilerRule(
                compiler_id="typed-affordance-semantics-v1",
                supported_intents=(
                    "owner-scoped collection action",
                    "typed quantity adjustment",
                    "observed visual or SVG target",
                    "selection, hierarchy, relation, discovery, or semantic drag",
                ),
                operation_classes=_OPERATION_CLASSES,
                applicability_description=(
                    "current typed affordance state and objective jointly identify one bounded semantic operation"
                ),
                applicability=_has_affordances,
                compile=callbacks.semantic_operation,
                evidence=SemanticCompilerEvidence(
                    required_state_keys=(),
                    output_action_kinds=(
                        "activate",
                        "point_activate",
                        "select_option",
                        "drag",
                        "finish",
                    ),
                    verifier_requirements=_POSTCONDITION,
                    negative_examples=(
                        "same labels without owner/container/geometry evidence",
                        "objective values absent from the current typed inventory",
                        "ambiguous source or destination candidates",
                    ),
                    source="runtime-generic-affordance-conformance",
                    version="1",
                ),
            ),
        ),
        constraint_rules=(
            SemanticConstraintRule(
                compiler_id="typed-planner-constraints-v1",
                applicability_description=(
                    "current semantic inventory can safely narrow targets, exact observed values, "
                    "or one-step keyboard transitions without creating backend authority"
                ),
                applicability=_has_affordances,
                constrain=callbacks.planner_constraints,
                evidence=SemanticCompilerEvidence(
                    required_state_keys=(),
                    output_action_kinds=tuple(item.value for item in PlannerActionKind),
                    verifier_requirements=_POSTCONDITION,
                    negative_examples=(
                        "ambiguous labels without a unique typed target",
                        "unobserved source values or backend-derived execution fields",
                        "already satisfied or progress-blocked action signatures",
                    ),
                    source="runtime-generic-planner-constraint-conformance",
                    version="1",
                ),
            ),
        ),
    )


def _has_range_selectable_affordance(context: SemanticCompilerContext) -> bool:
    return any(item.state.get("range_selectable") is True for item in context.affordances)


def _has_writable_affordance(context: SemanticCompilerContext) -> bool:
    return any(item.action in {"fill", "type", "type_text"} for item in context.affordances)


def _has_one_incremental_control(context: SemanticCompilerContext) -> bool:
    return (
        len(
            [
                item
                for item in context.affordances
                if item.role == "slider" and item.action in {"press", "press_key"}
            ]
        )
        == 1
    )


def _has_affordances(context: SemanticCompilerContext) -> bool:
    return bool(context.affordances)

"""Typed, stateless strict-planner admission constraints."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.collection_window import OrdinalRouteConstraint, resolve_global_ordinal_constraint
from affordance_runtime.planner_context import PlannerContext
from affordance_runtime.planner_model_orchestrator import SemanticTextInputConstraint, semantic_text_input_constraint
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.terminal_readiness import (
    TaskObligationViewCompiler,
    TerminalEffectBindingResolver,
    TerminalReadinessEvaluator,
)


@dataclass(frozen=True)
class DecisionConstraintSet:
    permitted_action_kinds: tuple[str, ...]
    compatible_target_ids: dict[str, tuple[str, ...]]
    allowed_text_values: tuple[str, ...] = ()
    require_bound_text_source: bool = False
    text_constraint: SemanticTextInputConstraint | None = None
    ordinal_constraint: OrdinalRouteConstraint | None = None


@dataclass(frozen=True)
class StrictDecisionConstraintBuilder:
    """Apply typed text and ordinal admission without planning or state mutation."""

    def build(
        self,
        context: PlannerContext,
        permitted_action_kinds: list[str],
        compatible_target_ids: dict[str, list[str]],
        *,
        allowed_text_values: tuple[str, ...] = (),
        require_bound_text_source: bool = False,
    ) -> DecisionConstraintSet:
        permitted = list(permitted_action_kinds)
        targets = {key: list(value) for key, value in compatible_target_ids.items()}
        text = semantic_text_input_constraint(context, targets)
        if text is not None:
            if text.satisfied:
                targets[PlannerActionKind.TYPE_TEXT.value] = [
                    item for item in targets.get(PlannerActionKind.TYPE_TEXT.value, []) if item != text.target_id
                ]
            else:
                permitted = [PlannerActionKind.TYPE_TEXT.value]
                targets = {PlannerActionKind.TYPE_TEXT.value: [text.target_id]}
                allowed_text_values = text.allowed_text_values
                require_bound_text_source = False
        ordinal = resolve_global_ordinal_constraint(
            objective=context.active_subgoal,
            targets=tuple(str(item) for item in context.task_spec.get("targets", ())),
            affordances=context.affordances,
        )
        if ordinal is not None:
            permitted = [PlannerActionKind.ACTIVATE.value]
            targets = {PlannerActionKind.ACTIVATE.value: [ordinal.target_id]}
            allowed_text_values = ()
            require_bound_text_source = False
        return DecisionConstraintSet(
            permitted_action_kinds=tuple(permitted),
            compatible_target_ids={key: tuple(value) for key, value in targets.items()},
            allowed_text_values=allowed_text_values,
            require_bound_text_source=require_bound_text_source,
            text_constraint=text,
            ordinal_constraint=ordinal,
        )

    def narrow_terminal_candidates(
        self,
        context: PlannerContext,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> tuple[PlannerContext, dict[str, object]]:
        plan = state.task_plan
        progress = state.plan_progress
        if plan is None or progress is None or not snapshot.unified_affordances:
            return context, {}
        resolution = TerminalEffectBindingResolver().resolve(
            plan=plan,
            progress=progress,
            unified_affordances=snapshot.unified_affordances,
            observation=snapshot.observation,
        )
        if not resolution.bindings and not resolution.unresolved_target_ids:
            return context, {}
        view = TaskObligationViewCompiler().compile(
            plan=plan,
            progress=progress,
            bindings=resolution.bindings,
            task_revision=context.task_revision,
            observation_epoch_id=context.snapshot_id,
            target_fingerprints=snapshot.observation.target_fingerprints,
        )
        decision = TerminalReadinessEvaluator().evaluate(
            task_revision=context.task_revision,
            observation_epoch_id=context.snapshot_id,
            candidates=view.candidates,
            obligations=view.obligations,
        )
        excluded = set(resolution.unresolved_target_ids) | set(decision.blocked_target_ids)
        narrowed = context.model_copy(
            update={"affordances": tuple(item for item in context.affordances if item.id not in excluded)}
        )
        return narrowed, {
            "excluded_target_ids": sorted(excluded),
            "unresolved_target_ids": list(resolution.unresolved_target_ids),
            "candidates": [
                {
                    "semantic_target_id": item.semantic_target_id,
                    "status": item.status.value,
                    "blocking_obligation_ids": list(item.blocking_obligation_ids),
                    "unknown_obligation_ids": list(item.unknown_obligation_ids),
                }
                for item in decision.candidates
            ],
        }

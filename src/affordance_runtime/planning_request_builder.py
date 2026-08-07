"""Read-only projection builder for immutable Step Planner requests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from affordance_runtime.grounding import GroundingSource
from affordance_runtime.interaction_grounding import (
    GroundingStatus,
    GroundingTarget,
    InteractionGrounder,
)
from affordance_runtime.planning_request import (
    PlannerAdmissionSource,
    PlannerAdmissionView,
    PlannerAffordanceView,
    PlannerObservationView,
    PlannerOutcomeSummary,
    PlannerRecoverySummary,
    PlannerStepProjectionStatus,
    PlannerStepView,
    PlannerTaskView,
    PlanningRequest,
    PlanningRequestIdentity,
    RuntimeBudgetView,
    TargetAdmissionDecision,
    TargetAdmissionStatus,
    freeze_request_mapping,
)
from affordance_runtime.runtime import RunRequest
from affordance_runtime.simplified_runtime_contracts import StepActivityStatus
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import task_constraint_values, task_semantic_scope_terms
from affordance_runtime.task_plan_contracts import project_task_plan_views
from affordance_runtime.unified_observation import (
    CanonicalTarget,
    ConflictStatus,
    FactStatus,
    UnifiedObservation,
)

_EFFECTFUL_ACTION_KINDS = {
    "activate",
    "point_activate",
    "type_text",
    "select_option",
    "press_key",
    "drag",
    "navigate",
    "scroll",
}


@dataclass(frozen=True)
class PlanningRequestLimits:
    max_steps: int = 20
    max_observations: int = 30
    max_recoveries: int = 3
    max_effectful_actions: int = 5
    max_model_calls: int = 0
    max_affordances: int = 80
    max_artifact_refs: int = 3


@dataclass(frozen=True)
class PlanningRequestBuilder:
    limits: PlanningRequestLimits = PlanningRequestLimits()
    accepted_knowledge: tuple[str, ...] = ()
    allow_finish: bool = True

    def build(
        self,
        envelope: RunRequest,
        state: StateKernel,
        observation: UnifiedObservation,
    ) -> PlanningRequest:
        task_spec = envelope.task_spec
        if task_spec is None:
            raise ValueError("PlanningRequestBuilder requires a validated TaskSpec")
        before_version = state.version

        task_completion_criterion = None
        limits = self.limits
        step_view = _planner_step_view(task_spec.identity, task_spec.revision, state)
        permitted_action_kinds = _permitted_action_kinds(
            observation,
            allow_finish=self.allow_finish,
        )
        if not step_view.permits_effectful_actions:
            permitted_action_kinds = tuple(
                item for item in permitted_action_kinds if item not in _EFFECTFUL_ACTION_KINDS
            )
        admission = _active_step_admission(
            task_revision=task_spec.revision,
            step_view=step_view,
            observation=observation,
        )
        request = PlanningRequest(
            identity=PlanningRequestIdentity(
                task_spec_identity=task_spec.identity,
                task_revision=task_spec.revision,
                evaluated_at_state_version=state.version,
                snapshot_id=observation.epoch_id,
                page_revision=observation.page_revision,
                environment_revision=observation.environment_revision,
            ),
            task=PlannerTaskView(
                task_spec_identity=task_spec.identity,
                task_revision=task_spec.revision,
                objective=task_spec.objective,
                constraints=task_constraint_values(task_spec),
                capabilities=tuple(sorted(set(envelope.capabilities))),
                task_completion_criterion=task_completion_criterion,
                task_completion_projection_status="typed_task_completion_external",
                task_summary=freeze_request_mapping(_task_summary(task_spec.model_dump(mode="json"))),
            ),
            step=step_view,
            observation=PlannerObservationView(
                snapshot_id=observation.epoch_id,
                page_revision=observation.page_revision,
                environment_revision=observation.environment_revision,
                observed_text=observation.observed_text[:2_000],
                affordances=tuple(
                    _target_view(item)
                    for item in _bounded_targets(
                        list(observation.targets),
                        task_spec.objective,
                        task_semantic_scope_terms(task_spec),
                        limits.max_affordances,
                    )
                ),
                artifact_refs=tuple(
                    _opaque_artifact_ref(item) for item in observation.artifact_refs[-limits.max_artifact_refs :]
                ),
            ),
            recent_outcomes=_recent_outcomes(state),
            recovery=_recovery_summary(state),
            latest_outcome=freeze_request_mapping(_latest_outcome(state)),
            recent_proposals=tuple(
                freeze_request_mapping(item)
                for item in ((state.latest_planner_proposal,) if state.latest_planner_proposal else ())
            ),
            verified_effects=_verified_effects(state),
            pending_evidence_obligations=(),
            remaining_budget=RuntimeBudgetView(
                steps=max(0, limits.max_steps - state.step_count),
                observations=max(0, limits.max_observations - state.observation_count),
                recoveries=max(0, limits.max_recoveries - state.recovery_count),
                effectful_actions=max(
                    0,
                    limits.max_effectful_actions - state.effectful_action_count,
                ),
                model_calls=max(0, limits.max_model_calls),
            ),
            permitted_action_kinds=permitted_action_kinds,
            satisfied_action_targets=tuple(sorted(_satisfied_action_targets(state).items())),
            admission=admission,
        )
        if state.version != before_version:
            raise ValueError("planning request build changed state version")
        return request


def _planner_step_view(
    task_spec_identity: str,
    task_revision: int,
    state: StateKernel,
) -> PlannerStepView:
    if state.task_plan is None or state.task_progress is None:
        return PlannerStepView(
            plan=None,
            progress=None,
            active_step=None,
            activity_status=StepActivityStatus.NO_PLAN,
            projection_status=PlannerStepProjectionStatus.NO_PLAN,
        )
    plan, progress = project_task_plan_views(
        state.task_plan,
        task_spec_identity=task_spec_identity,
        task_revision=task_revision,
        progress=state.task_progress,
    )
    active_step = None
    if progress.activity_status == StepActivityStatus.ACTIVE:
        active_step = next(
            (item for item in plan.steps if item.step_id == progress.active_step_id),
            None,
        )
        if active_step is None:
            raise ValueError("active step is absent from canonical plan")
    return PlannerStepView(
        plan=plan,
        progress=progress,
        active_step=active_step,
        activity_status=progress.activity_status,
        projection_status=PlannerStepProjectionStatus.PROJECTED,
        active_step_action_family=_active_step_action_family(active_step),
    )


def _active_step_admission(
    *,
    task_revision: int,
    step_view: PlannerStepView,
    observation: UnifiedObservation,
) -> PlannerAdmissionView | None:
    active_step = step_view.active_step
    if active_step is None or step_view.activity_status != StepActivityStatus.ACTIVE:
        return None
    inventory = list(observation.targets)
    grounding = InteractionGrounder().ground(
        active_step.interaction,
        tuple(
            GroundingTarget(
                target_id=item.target_id,
                role=item.role,
                label=item.label,
                supported_actions=item.supported_actions,
                state=item.state,
            )
            for item in inventory
        ),
    )
    if grounding.status != GroundingStatus.RESOLVED:
        return None
    allowed = frozenset(item.target_id for item in (*grounding.targets, *grounding.destinations))
    current_target_ids = tuple(dict.fromkeys(item.target_id for item in inventory))
    decisions = tuple(
        TargetAdmissionDecision(
            target_id=target_id,
            status=TargetAdmissionStatus.BLOCKED,
            reason_code="outside_active_step_scope",
            blocking_step_ids=(active_step.step_id,),
        )
        for target_id in current_target_ids
        if target_id not in allowed
    )
    if not decisions:
        return PlannerAdmissionView(
            source=PlannerAdmissionSource.ACTIVE_STEP_SCOPE,
            task_revision=task_revision,
            snapshot_id=observation.epoch_id,
        )
    return PlannerAdmissionView(
        source=PlannerAdmissionSource.ACTIVE_STEP_SCOPE,
        task_revision=task_revision,
        snapshot_id=observation.epoch_id,
        target_decisions=decisions,
        excluded_target_ids=tuple(item.target_id for item in decisions),
    )


def _compatibility_active_step_objective(state: StateKernel) -> str:
    """Carry legacy active-step text as immutable context, not step authority."""

    plan = state.task_plan
    progress = state.task_progress
    if plan is None or progress is None or not progress.active_step_id:
        return ""
    return next(
        (item.objective for item in plan.steps if item.step_id == progress.active_step_id),
        "",
    )


def _compatibility_active_step_action_family(state: StateKernel) -> str:
    plan = state.task_plan
    progress = state.task_progress
    if plan is None or progress is None or not progress.active_step_id:
        return ""
    return next(
        ("" for item in plan.steps if item.step_id == progress.active_step_id),
        "",
    )


def _target_view(item: CanonicalTarget) -> PlannerAffordanceView:
    accepted_state = {fact.property_name: fact.value for fact in item.state_facts if fact.status == FactStatus.ACCEPTED}
    return PlannerAffordanceView(
        target_id=item.target_id,
        surface=(_presentation_surface(item.surfaces[0]) if len(item.surfaces) == 1 else "multi_surface"),
        role=item.role,
        label=_bounded_text(item.label, 240),
        supported_actions=item.supported_actions,
        state=_compact_target_state(accepted_state),
        confidence=None,
        conflict_codes=(
            (item.conflict_status.value,)
            if item.conflict_status in {ConflictStatus.MATERIAL_CONFLICT, ConflictStatus.INCONCLUSIVE}
            else ()
        ),
        source_refs=item.source_assertion_refs,
    )


def _presentation_surface(source: GroundingSource) -> str:
    return "visual" if source == GroundingSource.SOM else source.value


def _bounded_targets(
    targets_to_bound: list[CanonicalTarget],
    objective: str,
    targets: tuple[str, ...],
    limit: int,
) -> list[CanonicalTarget]:
    if len(targets_to_bound) <= limit:
        return targets_to_bound
    terms = {
        word.casefold()
        for text in (objective, *targets)
        for word in str(text).replace("-", " ").split()
        if len(word) >= 3
    }

    def relevance_text(item: CanonicalTarget) -> str:
        return f"{item.label} {item.role} {item.state}".casefold()

    ranked = sorted(
        enumerate(targets_to_bound),
        key=lambda pair: (
            -sum(term in relevance_text(pair[1]) for term in terms),
            pair[0],
        ),
    )
    selected_indexes = {index for index, _item in ranked[: max(1, limit)]}
    return [item for index, item in enumerate(targets_to_bound) if index in selected_indexes]


def _compact_target_state(value: dict[str, object]) -> dict[str, object]:
    """Bound accepted canonical facts without reconstructing acquisition objects."""

    compact: dict[str, object] = {}
    semantic_priority = (
        "element_tag",
        "input_type",
        "control_value_prefix",
        "control_value_suffix",
        "control_value",
        "visible",
        "enabled",
        "checked",
        "selected",
        "selected_options",
        "expanded",
        "relative_size",
        "collection_position",
        "collection_cardinality",
        "collection_owner",
        "container_context",
        "group_context",
        "scroll_top",
        "scroll_height",
        "client_height",
        "value",
        "min",
        "max",
        "step",
    )
    ordered_keys = tuple(key for key in semantic_priority if key in value) + tuple(
        key for key in sorted(value) if key not in semantic_priority
    )
    for key in ordered_keys[:12]:
        item = value[key]
        if isinstance(item, str):
            compact[key] = _bounded_text(item, 240)
        elif isinstance(item, (list, tuple)):
            compact[key] = tuple(item[:8])
        elif isinstance(item, (bool, int, float)) or item is None:
            compact[key] = item
    return compact


def _permitted_action_kinds(
    observation: UnifiedObservation,
    *,
    allow_finish: bool,
) -> tuple[str, ...]:
    action_map = {
        "activate": "activate",
        "click": "activate",
        "download": "activate",
        "invoke": "activate",
        "write_property": "activate",
        "point_activate": "point_activate",
        "fill": "type_text",
        "type": "type_text",
        "type_text": "type_text",
        "select": "select_option",
        "select_option": "select_option",
        "press": "press_key",
        "press_key": "press_key",
        "drag": "drag",
        "navigate": "navigate",
        "scroll": "scroll",
        "wait": "wait",
    }
    permitted = {"ask_user"}
    if allow_finish:
        permitted.add("finish")
    canonical_actions = {action for target in observation.targets for action in target.supported_actions}
    permitted.update(action_map[action] for action in canonical_actions if action in action_map)
    if canonical_actions & {"fill", "type", "type_text"}:
        permitted.add("focus")
    return tuple(sorted(permitted))


def _recent_outcomes(state: StateKernel) -> tuple[PlannerOutcomeSummary, ...]:
    receipt = state.last_receipt
    verification = state.latest_verification
    if receipt is None and verification is None:
        return ()
    evidence_refs = (
        tuple(item.evidence_id for item in verification.evidence if item.evidence_id)
        if verification is not None
        else ()
    )
    return (
        PlannerOutcomeSummary(
            receipt_status="success" if receipt and receipt.success else "failed" if receipt else "",
            verification_status=verification.status.value if verification else "",
            verified_criterion_ids=(),
            evidence_refs=evidence_refs,
            error_code=receipt.error_code.value if receipt and receipt.error_code else "",
        ),
    )


def _latest_outcome(state: StateKernel) -> dict[str, object]:
    receipt = state.last_receipt
    verification = state.latest_verification
    return {
        "receipt_success": receipt.success if receipt else None,
        "receipt_backend": receipt.backend if receipt else "",
        "error_code": receipt.error_code.value if receipt and receipt.error_code else "",
        "verification_status": verification.status.value if verification else "",
        "verification_reason": verification.reason if verification else "",
        "verified_state_delta": [
            {
                "verifier_kind": item.verifier_kind,
                "target": item.target,
                "passed": item.passed,
                "observed": item.observed,
                "expected": item.expected,
            }
            for item in (verification.evidence[-1:] if verification else [])
        ],
    }


def _verified_effects(state: StateKernel) -> tuple[str, ...]:
    verification = state.latest_verification
    latest_proposal = state.latest_planner_proposal
    return (
        tuple(str(item) for item in latest_proposal.get("expected_effects", []))
        if verification and verification.passed
        else ()
    )


def _recovery_summary(state: StateKernel) -> PlannerRecoverySummary | None:
    if state.latest_progress_guard:
        event = state.latest_progress_guard
        return PlannerRecoverySummary(
            kind="progress_guard",
            reason_code=str(event.get("reason") or ""),
            message=str(event.get("signature") or "")[:240],
        )
    failure = state.current_failure
    if failure is not None:
        return PlannerRecoverySummary(
            kind=failure.phase.value,
            reason_code=failure.error_code,
            message=failure.message[:240],
        )
    return None


def _satisfied_action_targets(state: StateKernel) -> dict[str, tuple[str, ...]]:
    current_revision = state.current_revision()
    current_page_revision = state.current_page_revision()
    collected: dict[str, list[str]] = {}
    for record in state.recent_action_outcomes.records:
        same_page = (
            record.post_page_revision == current_page_revision
            if record.post_page_revision and current_page_revision
            else record.post_environment_revision == current_revision
        )
        if not record.effect_satisfied or not same_page:
            continue
        action_kind = record.key.action_kind
        target_id = record.key.target_id
        if not action_kind or not target_id:
            continue
        targets = collected.setdefault(action_kind, [])
        if target_id not in targets:
            targets.append(target_id)
    return {action_kind: tuple(target_ids) for action_kind, target_ids in collected.items()}


def _opaque_artifact_ref(value: str) -> str:
    return f"artifact:sha256:{hashlib.sha256(value.encode()).hexdigest()}"


def _bounded_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    marker = " ...[truncated]... "
    prefix_length = (limit - len(marker)) // 2
    suffix_length = limit - len(marker) - prefix_length
    return value[:prefix_length] + marker + value[-suffix_length:]


def _active_step_action_family(active_step: object) -> str:
    return ""


def _task_summary(task_spec: dict[str, object]) -> dict[str, object]:
    keys = (
        "revision",
        "operation_class",
        "requirements",
        "inputs",
        "allowed_effect_refs",
        "hard_constraint_refs",
        "preference_refs",
        "forbidden_effect_refs",
        "capability_ceiling",
        "risk_policy",
        "success",
        "required_outputs",
    )
    return {key: task_spec[key] for key in keys if key in task_spec}

"""Read-only projection builder for immutable Step Planner requests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Affordance
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
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.simplified_runtime_contracts import StepActivityStatus
from affordance_runtime.simplified_step_projection import (
    LegacyStepProjectionResult,
    LegacyStepProjectionStatus,
    TaskCompletionProjectionStatus,
    project_state_legacy_task_plan_to_step_view,
    project_task_completion_criterion,
)
from affordance_runtime.state_kernel import StateKernel

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
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlanningRequest:
        task_spec = envelope.task_spec
        if task_spec is None:
            raise ValueError("PlanningRequestBuilder requires a validated TaskSpec")
        before_version = state.version
        step_projection = project_state_legacy_task_plan_to_step_view(
            task_spec=task_spec,
            state=state,
        )
        if state.version != before_version:
            raise ValueError("planning request projection cannot mutate state")

        completion_projection = project_task_completion_criterion(task_spec)
        task_completion_criterion = (
            completion_projection.criterion
            if completion_projection.status == TaskCompletionProjectionStatus.PROJECTED
            else None
        )
        limits = self.limits
        step_view = _planner_step_view(step_projection, state)
        permitted_action_kinds = _permitted_action_kinds(
            snapshot,
            allow_finish=self.allow_finish,
        )
        if not step_view.permits_effectful_actions:
            permitted_action_kinds = tuple(
                item
                for item in permitted_action_kinds
                if item not in _EFFECTFUL_ACTION_KINDS
            )
        admission = _active_step_admission(
            task_revision=task_spec.revision,
            step_view=step_view,
            snapshot=snapshot,
        )
        request = PlanningRequest(
            identity=PlanningRequestIdentity(
                task_spec_identity=task_spec.identity,
                task_revision=task_spec.revision,
                evaluated_at_state_version=state.version,
                snapshot_id=snapshot.observation.snapshot_id,
                page_revision=snapshot.observation.page_revision,
                environment_revision=snapshot.observation.environment_revision,
            ),
            task=PlannerTaskView(
                task_spec_identity=task_spec.identity,
                task_revision=task_spec.revision,
                objective=task_spec.objective,
                constraints=tuple(str(item) for item in task_spec.constraints),
                capabilities=tuple(sorted(set(envelope.capabilities))),
                task_completion_criterion=task_completion_criterion,
                task_completion_projection_status=completion_projection.status.value,
                task_summary=freeze_request_mapping(_task_summary(task_spec.model_dump(mode="json"))),
            ),
            step=step_view,
            observation=PlannerObservationView(
                snapshot_id=snapshot.observation.snapshot_id,
                page_revision=snapshot.observation.page_revision,
                environment_revision=snapshot.observation.environment_revision,
                observed_text=str(snapshot.observation.metadata.get("visible_text") or "")[:2_000],
                affordances=tuple(
                    _affordance_view(item)
                    for item in _bounded_affordances(
                        _planner_affordance_inventory(snapshot),
                        task_spec.objective,
                        task_spec.targets,
                        limits.max_affordances,
                    )
                ),
                artifact_refs=tuple(
                    _opaque_artifact_ref(item)
                    for item in snapshot.observation.artifact_refs[-limits.max_artifact_refs :]
                ),
            ),
            recent_outcomes=_recent_outcomes(state),
            recovery=_recovery_summary(state),
            latest_outcome=freeze_request_mapping(_latest_outcome(state)),
            recent_proposals=tuple(
                freeze_request_mapping(item)
                for item in state.planner_history[-1:]
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
            satisfied_action_targets=tuple(
                sorted(_satisfied_action_targets(state).items())
            ),
            admission=admission,
        )
        if state.version != before_version:
            raise ValueError("planning request build changed state version")
        return request


def _planner_step_view(
    projection: LegacyStepProjectionResult,
    state: StateKernel,
) -> PlannerStepView:
    if projection.status != LegacyStepProjectionStatus.PROJECTED:
        return PlannerStepView(
            plan=None,
            progress=None,
            active_step=None,
            activity_status=StepActivityStatus.NO_PLAN,
            projection_status=_planner_step_projection_status(projection.status),
            projection_reason=projection.reason,
            active_step_action_family=_compatibility_active_step_action_family(state),
            compatibility_active_step_objective=_compatibility_active_step_objective(state),
        )
    plan = projection.task_plan_view
    progress = projection.step_progress_view
    if plan is None or progress is None:
        raise ValueError("projected legacy step view is incomplete")
    active_step = None
    if progress.activity_status == StepActivityStatus.ACTIVE:
        active_step = next(
            (item for item in plan.steps if item.step_id == progress.active_step_id),
            None,
        )
        if active_step is None:
            raise ValueError("active step is absent from projected plan")
    return PlannerStepView(
        plan=plan,
        progress=progress,
        active_step=active_step,
        activity_status=progress.activity_status,
        projection_status=PlannerStepProjectionStatus.PROJECTED,
        active_step_action_family=_active_step_action_family(active_step)
        or _compatibility_active_step_action_family(state),
    )


def _active_step_admission(
    *,
    task_revision: int,
    step_view: PlannerStepView,
    snapshot: BrowserSnapshot,
) -> PlannerAdmissionView | None:
    active_step = step_view.active_step
    if active_step is None or step_view.activity_status != StepActivityStatus.ACTIVE:
        return None
    allowed = _active_step_subjects(active_step)
    if not allowed:
        return None
    current_target_ids = tuple(dict.fromkeys(item.id for item in _planner_affordance_inventory(snapshot)))
    if not set(current_target_ids).intersection(allowed):
        return None
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
            snapshot_id=snapshot.observation.snapshot_id,
        )
    return PlannerAdmissionView(
        source=PlannerAdmissionSource.ACTIVE_STEP_SCOPE,
        task_revision=task_revision,
        snapshot_id=snapshot.observation.snapshot_id,
        target_decisions=decisions,
        excluded_target_ids=tuple(item.target_id for item in decisions),
    )


def _active_step_subjects(active_step: object) -> frozenset[str]:
    subjects: list[str] = []
    for criterion in getattr(active_step, "completion_criteria", ()) + getattr(active_step, "preconditions", ()):
        subject = getattr(criterion, "subject", "")
        if isinstance(subject, str) and subject.strip():
            subjects.append(subject)
    return frozenset(subjects)


def _compatibility_active_step_objective(state: StateKernel) -> str:
    """Carry legacy active-step text as immutable context, not step authority."""

    plan = state.task_plan
    progress = state.plan_progress
    if plan is None or progress is None or not progress.active_subgoal_id:
        return ""
    return next(
        (
            item.objective
            for item in plan.subgoals
            if item.subgoal_id == progress.active_subgoal_id
        ),
        "",
    )


def _compatibility_active_step_action_family(state: StateKernel) -> str:
    plan = state.task_plan
    progress = state.plan_progress
    if plan is None or progress is None or not progress.active_subgoal_id:
        return ""
    return next(
        (
            item.action_family.value
            for item in plan.subgoals
            if item.subgoal_id == progress.active_subgoal_id and item.action_family is not None
        ),
        "",
    )


def _planner_step_projection_status(
    status: LegacyStepProjectionStatus,
) -> PlannerStepProjectionStatus:
    try:
        return PlannerStepProjectionStatus(status.value)
    except ValueError as exc:
        raise ValueError("unsupported legacy step projection status") from exc


def _affordance_view(item: Affordance) -> PlannerAffordanceView:
    return PlannerAffordanceView(
        target_id=item.id,
        surface=item.surface.value,
        role=item.role,
        label=_bounded_text(item.label, 240),
        supported_actions=(item.action,),
        state=_compact_affordance_state(item.state),
        confidence=item.confidence,
        conflict_codes=(),
        source_refs=tuple(str(ref) for ref in item.evidence),
    )


def _planner_affordance_inventory(snapshot: BrowserSnapshot) -> list[Affordance]:
    if not snapshot.unified_affordances:
        return [
            item
            for item in snapshot.affordance_model.affordances
            if item.state.get("visible") is not False
        ]
    source_by_id = {item.id: item for item in snapshot.affordance_model.affordances}
    inventory: list[Affordance] = []
    for target in snapshot.unified_affordances:
        representative = next(
            (
                source_by_id[candidate.source_affordance_id]
                for candidate in target.grounding_candidates
                if candidate.source_affordance_id in source_by_id
            ),
            None,
        )
        if representative is None or representative.state.get("visible") is False:
            continue
        actions = sorted(target.supported_actions)
        if len(actions) != 1:
            continue
        inventory.append(
            replace(
                representative,
                id=target.semantic_target_id,
                role=target.role,
                label=target.label,
                action=actions[0],
                locator={},
                backend_candidates=[],
                confidence=max(item.confidence for item in target.grounding_candidates),
                state={
                    **representative.state,
                    "grounding_source_count": len(target.grounding_candidates),
                },
            )
        )
    return inventory


def _bounded_affordances(
    affordances: list[Affordance],
    objective: str,
    targets: tuple[str, ...],
    limit: int,
) -> list[Affordance]:
    if len(affordances) <= limit:
        return affordances
    terms = {
        word.casefold()
        for text in (objective, *targets)
        for word in str(text).replace("-", " ").split()
        if len(word) >= 3
    }

    def relevance_text(item: Affordance) -> str:
        return f"{item.label} {item.role} {item.state}".casefold()

    ranked = sorted(
        enumerate(affordances),
        key=lambda pair: (
            -sum(term in relevance_text(pair[1]) for term in terms),
            -pair[1].confidence,
            pair[0],
        ),
    )
    selected_indexes = {index for index, _item in ranked[: max(1, limit)]}
    return [item for index, item in enumerate(affordances) if index in selected_indexes]


def _compact_affordance_state(value: dict[str, object]) -> dict[str, object]:
    """Mirror legacy PlannerContext state bounds before freezing request input."""

    compact: dict[str, object] = {}
    for key in sorted(value)[:12]:
        item = value[key]
        if isinstance(item, str):
            compact[key] = _bounded_text(item, 240)
        elif isinstance(item, (list, tuple)):
            compact[key] = tuple(item[:8])
        elif isinstance(item, (bool, int, float)) or item is None:
            compact[key] = item
    return compact


def _permitted_action_kinds(
    snapshot: BrowserSnapshot,
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
    permitted.update(
        action_map[item.action]
        for item in _planner_affordance_inventory(snapshot)
        if item.action in action_map
    )
    return tuple(sorted(permitted))


def _recent_outcomes(state: StateKernel) -> tuple[PlannerOutcomeSummary, ...]:
    receipt = state.receipts[-1] if state.receipts else None
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
    receipt = state.receipts[-1] if state.receipts else None
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
    latest_proposal = state.planner_history[-1] if state.planner_history else {}
    return (
        tuple(str(item) for item in latest_proposal.get("expected_effects", []))
        if verification and verification.passed
        else ()
    )


def _recovery_summary(state: StateKernel) -> PlannerRecoverySummary | None:
    if state.progress_guard_events:
        event = state.progress_guard_events[-1]
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
        "objective",
        "operation_class",
        "task_structure",
        "targets",
        "success_criteria",
        "constraints",
        "semantic_value_constraints",
        "forbidden_effects",
        "evidence_requirements",
        "requested_capabilities",
        "ambiguity_status",
    )
    return {key: task_spec[key] for key in keys if key in task_spec}

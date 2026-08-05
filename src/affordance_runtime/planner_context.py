"""Bounded, untrusted observation context for environment-general planners."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Any

from pydantic import BaseModel, ConfigDict

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Affordance
from affordance_runtime.planning_request import (
    PlanningRequest,
    thaw_request_mapping,
    thaw_request_value,
)
from affordance_runtime.runtime import RunRequest
from affordance_runtime.state_kernel import StateKernel


class AffordanceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    surface: str
    role: str
    label: str
    action: str
    supported_actions: tuple[str, ...] = ()
    confidence: float
    state: dict[str, Any]


class PlannerContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_spec: dict[str, Any]
    active_subgoal: str
    active_subgoal_action_family: str = ""
    observed_text: str
    affordances: tuple[AffordanceSummary, ...]
    permitted_action_kinds: tuple[str, ...]
    selected_artifact_refs: tuple[str, ...]
    granted_capabilities: tuple[str, ...]
    approval_handling: str
    remaining_budgets: dict[str, int]
    pending_evidence_obligations: tuple[str, ...]
    latest_outcome: dict[str, Any]
    recent_proposals: tuple[dict[str, Any], ...]
    verified_effects: tuple[str, ...]
    satisfied_action_targets: dict[str, tuple[str, ...]]
    recovery_summary: dict[str, Any]
    accepted_knowledge: tuple[str, ...]
    task_revision: int
    state_version: int
    snapshot_id: str


@dataclass(frozen=True)
class PlannerLimits:
    max_steps: int = 20
    max_observations: int = 30
    max_recoveries: int = 3
    max_effectful_actions: int = 5
    max_affordances: int = 80
    max_artifact_refs: int = 3
    max_accepted_knowledge: int = 3


@dataclass(frozen=True)
class PlannerContextBuilder:
    limits: PlannerLimits = PlannerLimits()
    accepted_knowledge: tuple[str, ...] = ()
    allow_finish: bool = True

    def build(
        self,
        envelope: RunRequest | PlanningRequest,
        state: StateKernel | None = None,
        snapshot: BrowserSnapshot | None = None,
    ) -> PlannerContext:
        if isinstance(envelope, PlanningRequest):
            if state is not None or snapshot is not None:
                raise ValueError("request-based PlannerContext build cannot receive legacy state")
            return self._build_from_request(envelope)
        if state is None or snapshot is None:
            raise ValueError("legacy PlannerContext build requires state and snapshot")
        task_spec = envelope.task_spec
        if task_spec is None:
            raise ValueError("GeneralistLMPlanner requires a validated TaskSpec")
        receipt = state.last_receipt
        verification = state.latest_verification
        latest_outcome = {
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
        latest_proposal = state.latest_planner_proposal
        verified_effects = (
            tuple(str(item) for item in latest_proposal.get("expected_effects", []))
            if verification and verification.passed
            else ()
        )
        limits = self.limits
        active_subgoal = state.active_subgoal() or task_spec.objective
        return PlannerContext(
            task_spec=_task_summary(task_spec.model_dump(mode="json")),
            active_subgoal=active_subgoal,
            active_subgoal_action_family=_active_subgoal_action_family(state),
            observed_text=str(snapshot.observation.metadata.get("visible_text") or "")[:2_000],
            affordances=tuple(
                AffordanceSummary(
                    id=item.id,
                    surface=item.surface.value,
                    role=item.role,
                    label=_bounded_observed_text(item.label),
                    action=item.action,
                    confidence=item.confidence,
                    state=_compact_mapping(item.state),
                )
                for item in _bounded_affordances(
                    _planner_affordance_inventory(snapshot),
                    task_spec.objective,
                    task_spec.targets,
                    limits.max_affordances,
                )
            ),
            permitted_action_kinds=_permitted_action_kinds(
                snapshot,
                allow_finish=self.allow_finish,
            ),
            selected_artifact_refs=tuple(
                _opaque_artifact_ref(item)
                for item in snapshot.observation.artifact_refs[-limits.max_artifact_refs :]
            ),
            granted_capabilities=tuple(sorted(set(envelope.capabilities))),
            approval_handling="coordinator_managed",
            remaining_budgets={
                "steps": max(0, limits.max_steps - state.step_count),
                "observations": max(0, limits.max_observations - state.observation_count),
                "recoveries": max(0, limits.max_recoveries - state.recovery_count),
                "effectful_actions": max(
                    0,
                    limits.max_effectful_actions - state.effectful_action_count,
                ),
            },
            pending_evidence_obligations=(),
            latest_outcome=latest_outcome,
            recent_proposals=((state.latest_planner_proposal,) if state.latest_planner_proposal else ()),
            verified_effects=verified_effects,
            satisfied_action_targets=_satisfied_action_targets(state),
            recovery_summary=_one_relevant_failure(state),
            accepted_knowledge=self.accepted_knowledge[-limits.max_accepted_knowledge :],
            task_revision=task_spec.revision,
            state_version=state.version,
            snapshot_id=snapshot.observation.snapshot_id,
        )

    def _build_from_request(self, request: PlanningRequest) -> PlannerContext:
        latest_outcome = thaw_request_mapping(request.latest_outcome)
        recent_proposals = tuple(
            thaw_request_mapping(item) for item in request.recent_proposals
        )
        recovery_summary = (
            {
                "kind": request.recovery.kind,
                "reason_code": request.recovery.reason_code,
                "message": request.recovery.message,
                "attempted_changes": list(request.recovery.attempted_changes),
            }
            if request.recovery is not None
            else {}
        )
        active_subgoal = (
            request.step.active_step.objective
            if request.step.active_step is not None
            else request.step.compatibility_active_step_objective or request.task.objective
        )
        return PlannerContext(
            task_spec=_task_summary_from_request(request),
            active_subgoal=active_subgoal,
            active_subgoal_action_family=request.step.active_step_action_family,
            observed_text=request.observation.observed_text,
            affordances=tuple(
                AffordanceSummary(
                    id=item.target_id,
                    surface=item.surface,
                    role=item.role,
                    label=item.label,
                    action=next(
                        (
                            action
                            for action in item.supported_actions
                            if action != "focus"
                        ),
                        item.supported_actions[0] if item.supported_actions else "",
                    ),
                    supported_actions=item.supported_actions,
                    confidence=item.confidence if item.confidence is not None else 0.0,
                    state={key: thaw_request_value(value) for key, value in item.state},
                )
                for item in request.observation.affordances
            ),
            permitted_action_kinds=request.permitted_action_kinds,
            selected_artifact_refs=request.observation.artifact_refs,
            granted_capabilities=request.task.capabilities,
            approval_handling="coordinator_managed",
            remaining_budgets={
                "steps": request.remaining_budget.steps,
                "observations": request.remaining_budget.observations,
                "recoveries": request.remaining_budget.recoveries,
                "effectful_actions": request.remaining_budget.effectful_actions,
            },
            pending_evidence_obligations=request.pending_evidence_obligations,
            latest_outcome=latest_outcome,
            recent_proposals=recent_proposals,
            verified_effects=request.verified_effects,
            satisfied_action_targets={
                key: value for key, value in request.satisfied_action_targets
            },
            recovery_summary=recovery_summary,
            accepted_knowledge=self.accepted_knowledge[
                -self.limits.max_accepted_knowledge :
            ],
            task_revision=request.identity.task_revision,
            state_version=request.identity.evaluated_at_state_version,
            snapshot_id=request.identity.snapshot_id,
        )


def build_planner_context(
    envelope: RunRequest,
    state: StateKernel,
    snapshot: BrowserSnapshot,
    *,
    limits: PlannerLimits = PlannerLimits(),
    accepted_knowledge: tuple[str, ...] = (),
    allow_finish: bool = True,
) -> PlannerContext:
    """Compatibility function around the explicit context builder."""

    return PlannerContextBuilder(
        limits=limits,
        accepted_knowledge=accepted_knowledge,
        allow_finish=allow_finish,
    ).build(envelope, state, snapshot)


def _task_summary(task_spec: dict[str, Any]) -> dict[str, Any]:
    # Run/task identifiers are trace and audit metadata. The step planner gets
    # local revision/state identities separately and must not learn suite,
    # manifest, seed, or caller naming conventions through task_id.
    keys = (
        "revision",
        "objective",
        "operation_class",
        "task_structure",
        "targets",
        "entities",
        "success_criteria",
        "constraints",
        "semantic_value_constraints",
        "forbidden_effects",
        "evidence_requirements",
        "requested_capabilities",
        "ambiguity_status",
    )
    return {key: task_spec[key] for key in keys if key in task_spec}


def _task_summary_from_request(request: PlanningRequest) -> dict[str, Any]:
    summary = thaw_request_mapping(request.task.task_summary)
    if summary:
        return summary
    return {
        "revision": request.task.task_revision,
        "objective": request.task.objective,
        "constraints": list(request.task.constraints),
        "requested_capabilities": list(request.task.capabilities),
    }


def _opaque_artifact_ref(value: str) -> str:
    """Keep planner correlation without exposing run or suite names in paths."""

    return f"artifact:sha256:{hashlib.sha256(value.encode()).hexdigest()}"


def _planner_affordance_inventory(snapshot: BrowserSnapshot) -> list[Affordance]:
    """Expose semantic target ids while retaining bounded source-derived state."""

    if not snapshot.unified_affordances:
        return [item for item in snapshot.affordance_model.affordances if item.state.get("visible") is not False]
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
                locator={
                    "semantic_target_id": target.semantic_target_id,
                    "candidate_ids": [item.candidate_id for item in target.grounding_candidates],
                },
                backend_candidates=list(
                    dict.fromkeys(item.compatible_executor for item in target.grounding_candidates)
                ),
                confidence=max(item.confidence for item in target.grounding_candidates),
                state={
                    **representative.state,
                    "grounding_source_count": len(target.grounding_candidates),
                },
            )
        )
    return inventory


def _compact_mapping(value: dict[str, Any]) -> dict[str, Any]:
    """Bound page-derived state without interpreting it as authority."""

    compact: dict[str, Any] = {}
    for key in sorted(value)[:12]:
        item = value[key]
        if isinstance(item, str):
            compact[key] = _bounded_observed_text(item)
        elif isinstance(item, (list, tuple)):
            compact[key] = list(item[:8])
        elif isinstance(item, (bool, int, float)) or item is None:
            compact[key] = item
    return compact


def _bounded_observed_text(value: str, limit: int = 240) -> str:
    """Bound untrusted text while retaining both relationally useful ends."""

    if len(value) <= limit:
        return value
    marker = " ...[truncated]... "
    prefix_length = (limit - len(marker)) // 2
    suffix_length = limit - len(marker) - prefix_length
    return value[:prefix_length] + marker + value[-suffix_length:]


def _bounded_affordances(
    affordances: list[Any],
    objective: str,
    targets: tuple[str, ...],
    limit: int,
) -> list[Any]:
    if len(affordances) <= limit:
        return affordances
    terms = {
        word.casefold()
        for text in (objective, *targets)
        for word in str(text).replace("-", " ").split()
        if len(word) >= 3
    }
    noisy_context_fields = {"container_context", "context_text", "group_context"}

    def relevance_text(item: Any) -> str:
        local_state = {
            key: value
            for key, value in item.state.items()
            if key not in noisy_context_fields
        }
        return f"{item.label} {item.role} {local_state}".casefold()

    ranked = sorted(
        enumerate(affordances),
        key=lambda pair: (
            -sum(term in relevance_text(pair[1]) for term in terms),
            -pair[1].confidence,
            pair[0],
        ),
    )
    selected_indexes: set[int] = set()
    action_family_counts: dict[str, int] = {}
    budget = max(1, limit)
    for index, item in ranked:
        if len(selected_indexes) >= budget:
            break
        action_family = str(item.action)
        if action_family_counts.get(action_family, 0) >= 4:
            continue
        selected_indexes.add(index)
        action_family_counts[action_family] = action_family_counts.get(action_family, 0) + 1
    for index, _item in ranked:
        if len(selected_indexes) >= budget:
            break
        selected_indexes.add(index)
    return [item for index, item in enumerate(affordances) if index in selected_indexes]


def _one_relevant_failure(state: StateKernel) -> dict[str, Any]:
    if state.latest_progress_guard:
        return {"kind": "progress_guard", **state.latest_progress_guard}
    receipt = state.last_receipt
    if receipt is not None and not receipt.success:
        return {
            "kind": "execution",
            "error_code": receipt.error_code.value if receipt.error_code else "execution_failed",
            "message": receipt.message[:240],
        }
    verification = state.latest_verification
    if verification is not None and not verification.passed:
        return {
            "kind": "verification",
            "status": verification.status.value,
            "reason": verification.reason[:240],
        }
    failure = state.current_failure
    if failure is not None:
        return {
            "kind": failure.phase.value,
            "error_code": failure.error_code,
            "message": failure.message[:240],
            "recoverable": failure.recoverable,
            "proposal_rejection": (
                failure.proposal_rejection.model_dump(mode="json")
                if failure.proposal_rejection is not None
                else None
            ),
        }
    return {}


def _satisfied_action_targets(state: StateKernel) -> dict[str, tuple[str, ...]]:
    """Compact current-revision progress memory into action/target blocklists."""

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


def _active_subgoal_action_family(state: StateKernel) -> str:
    if state.task_plan is None or state.task_progress is None:
        return ""
    active_id = state.task_progress.active_subgoal_id
    subgoal = next(
        (item for item in state.task_plan.subgoals if item.subgoal_id == active_id),
        None,
    )
    return subgoal.action_family.value if subgoal is not None and subgoal.action_family else ""


def _permitted_action_kinds(
    snapshot: BrowserSnapshot,
    *,
    allow_finish: bool = True,
) -> tuple[str, ...]:
    """Expose only semantic actions which the current adapter can bind."""

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
    if any(
        item.action in {"fill", "type", "type_text"}
        for item in _planner_affordance_inventory(snapshot)
    ):
        permitted.add("focus")
    return tuple(sorted(permitted))

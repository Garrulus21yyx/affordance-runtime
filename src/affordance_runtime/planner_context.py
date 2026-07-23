"""Bounded, untrusted observation context for environment-general planners."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from pydantic import BaseModel, ConfigDict

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Affordance
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.state_kernel import StateKernel


class AffordanceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    surface: str
    role: str
    label: str
    action: str
    confidence: float
    state: dict[str, Any]


class PlannerContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_spec: dict[str, Any]
    active_subgoal: str
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
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerContext:
        task_spec = envelope.task_spec
        if task_spec is None:
            raise ValueError("GeneralistLMPlanner requires a validated TaskSpec")
        receipt = state.receipts[-1] if state.receipts else None
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
        latest_proposal = state.planner_history[-1] if state.planner_history else {}
        verified_effects = (
            tuple(str(item) for item in latest_proposal.get("expected_effects", []))
            if verification and verification.passed
            else ()
        )
        limits = self.limits
        return PlannerContext(
            task_spec=_task_summary(task_spec.model_dump(mode="json")),
            active_subgoal=state.active_subgoal() or task_spec.objective,
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
                snapshot.observation.artifact_refs[-limits.max_artifact_refs :]
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
            pending_evidence_obligations=tuple(state.pending_obligations[-5:]),
            latest_outcome=latest_outcome,
            recent_proposals=tuple(state.planner_history[-1:]),
            verified_effects=verified_effects,
            satisfied_action_targets=_satisfied_action_targets(state),
            recovery_summary=_one_relevant_failure(state),
            accepted_knowledge=self.accepted_knowledge[-limits.max_accepted_knowledge :],
            task_revision=task_spec.revision,
            state_version=state.version,
            snapshot_id=snapshot.observation.snapshot_id,
        )


def build_planner_context(
    envelope: TaskEnvelope,
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
        "targets",
        "success_criteria",
        "constraints",
        "forbidden_effects",
        "evidence_requirements",
        "requested_capabilities",
        "ambiguity_status",
    )
    return {key: task_spec[key] for key in keys if key in task_spec}


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
    if state.progress_guard_events:
        return {"kind": "progress_guard", **state.progress_guard_events[-1]}
    receipt = state.receipts[-1] if state.receipts else None
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
    if state.recovery_diagnostics:
        findings = state.recovery_diagnostics.get("findings")
        return {
            "kind": "recovery",
            "incident_id": state.recovery_diagnostics.get("incident_id", ""),
            "finding": findings[-1] if isinstance(findings, list) and findings else "",
            "terminal_outcome": state.recovery_diagnostics.get("terminal_outcome", ""),
        }
    return {}


def _satisfied_action_targets(state: StateKernel) -> dict[str, tuple[str, ...]]:
    """Compact current-revision progress memory into action/target blocklists."""

    current_revision = state.current_revision()
    current_page_revision = state.current_page_revision()
    collected: dict[str, list[str]] = {}
    for record in state.action_progress[-40:]:
        same_page = (
            record.post_page_revision == current_page_revision
            if record.post_page_revision and current_page_revision
            else record.post_environment_revision == current_revision
        )
        if not record.effect_satisfied or not same_page:
            continue
        try:
            signature = json.loads(record.signature)
        except json.JSONDecodeError:
            continue
        action_kind = str(signature.get("action_kind") or "")
        target_id = str(signature.get("target") or "")
        if not action_kind or not target_id:
            continue
        targets = collected.setdefault(action_kind, [])
        if target_id not in targets:
            targets.append(target_id)
    return {action_kind: tuple(target_ids) for action_kind, target_ids in collected.items()}


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
    return tuple(sorted(permitted))

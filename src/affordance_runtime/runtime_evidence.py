"""Canonical evidence projections used by the Runtime coordinator."""

from __future__ import annotations

import json
from typing import Any

from affordance_runtime.contracts import ActionContract
from affordance_runtime.planning import PlannerProposal
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.unified_observation import UnifiedObservation
from affordance_runtime.verification.mechanical import VerificationReport, VerificationStatus


def action_progress_signature(
    proposal: PlannerProposal | None,
    contract: ActionContract,
) -> str:
    """Return the canonical semantic identity used by progress guards."""

    if proposal is not None:
        payload: dict[str, Any] = {
            "action_kind": proposal.action_kind.value,
            "target": proposal.target_affordance_id,
            "parameters": proposal.parameters,
        }
        if proposal.subgoal:
            payload["subgoal"] = proposal.subgoal
        if proposal.destination_affordance_id:
            payload["destination"] = proposal.destination_affordance_id
    else:
        payload = {
            "action_kind": contract.action,
            "target": contract.locator.get("backend_handle") or contract.affordance_id,
            "parameters": contract.parameters,
        }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def verification_satisfies_effect(report: VerificationReport) -> bool:
    if not report.passed:
        return False
    return not any(
        item.verifier_kind == "control_state"
        and isinstance(item.expected, dict)
        and "changed_from" in item.expected
        for item in report.evidence
    )


def verification_confirms_effect_absent(report: VerificationReport) -> bool:
    return (
        report.status == VerificationStatus.FAILED
        and bool(report.evidence)
        and any(
            not item.passed and item.strength == "strong" for item in report.evidence
        )
    )


def semantic_progress_fingerprint(state: StateKernel) -> str:
    progress = {
        "completed_subgoals": (
            list(state.task_progress.completed_subgoal_ids)
            if state.task_progress is not None
            else []
        ),
        "satisfied_effects": [
            f"{item.key.action_kind}:{item.key.target_id}:{item.key.parameter_digest}"
            for item in state.recent_action_outcomes.records
            if item.verification_passed and item.effect_satisfied
        ],
    }
    return json.dumps(progress, sort_keys=True, separators=(",", ":"))


def semantic_target_descriptor(
    snapshot: UnifiedObservation,
    semantic_target_id: str,
) -> dict[str, str] | None:
    if not semantic_target_id:
        return None
    target = next(
        (
            item
            for item in snapshot.targets
            if item.target_id == semantic_target_id
        ),
        None,
    )
    if target is None:
        return None
    return {
        "semantic_target_id": target.target_id,
        "role": target.role,
        "label": target.label,
    }

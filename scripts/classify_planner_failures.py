#!/usr/bin/env python3
"""Classify planning-layer residuals from a BrowserGym diagnostic report.

The classifier is intentionally read-only. It consumes the aggregate
``browsergym-report.json`` and the referenced per-episode trace files, then
emits a compact JSON summary for SAR-8 recovery protocol design.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

PLANNER_WAITING = "planner_waiting_clarification"
ALREADY_SATISFIED = "entry_outcome_already_satisfied"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _event_payloads(trace_path: Path, event_type: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    if not trace_path.exists():
        return payloads
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event_type") == event_type:
            payload = event.get("payload")
            if isinstance(payload, dict):
                payloads.append(payload)
    return payloads


def _first_trace_path(envelope: dict[str, Any]) -> Path | None:
    refs = envelope.get("artifact_refs")
    if not isinstance(refs, list):
        return None
    for ref in refs:
        if isinstance(ref, str) and ref.endswith("events.jsonl"):
            return Path(ref)
    return None


def _last_context(trace_path: Path | None) -> dict[str, Any]:
    if trace_path is None:
        return {}
    payloads = _event_payloads(trace_path, "PlannerContextBuilt")
    if not payloads:
        return {}
    context = payloads[-1].get("context")
    return context if isinstance(context, dict) else {}


def _last_proposal(trace_path: Path | None) -> dict[str, Any]:
    if trace_path is None:
        return {}
    payloads = _event_payloads(trace_path, "PlannerProposalProduced")
    if not payloads:
        return {}
    proposal = payloads[-1].get("proposal")
    return proposal if isinstance(proposal, dict) else {}


def _non_ask_actions(actions: object) -> tuple[str, ...]:
    if not isinstance(actions, list):
        return ()
    return tuple(str(action) for action in actions if str(action) != "ask_user")


def classify_failure(envelope: dict[str, Any]) -> dict[str, Any]:
    trace_path = _first_trace_path(envelope)
    context = _last_context(trace_path)
    proposal = _last_proposal(trace_path)
    signature = str(envelope.get("failure_signature") or "")
    runtime_failure = envelope.get("runtime_failure")
    detail_code = ""
    if isinstance(runtime_failure, dict):
        detail_code = str(runtime_failure.get("detail_code") or "")
    permitted_actions = _non_ask_actions(
        context.get("permitted_action_kinds") or envelope.get("permitted_action_kinds")
    )
    affordance_count = int(envelope.get("affordance_count") or context.get("affordance_count") or 0)
    action_kind = str(proposal.get("action_kind") or envelope.get("action_kind") or "")
    active_step = str(context.get("active_subgoal") or "")
    active_step_action_family = str(context.get("active_subgoal_action_family") or "")

    if ALREADY_SATISFIED in signature or detail_code == ALREADY_SATISFIED:
        category = "current_step_already_satisfied_owner"
        recommended_owner = "progress_precheck"
        recovery_semantics = "complete_step_then_continue"
    elif signature == PLANNER_WAITING and permitted_actions and affordance_count > 0:
        category = "model_deferral_with_action_space"
        recommended_owner = "planner_model_or_action_choice_builder"
        recovery_semantics = "bounded_retry_or_deterministic_choice"
    elif signature == PLANNER_WAITING:
        category = "missing_or_filtered_action_space"
        recommended_owner = "projection_or_constraints"
        recovery_semantics = "reobserve_reground_or_reproject"
    elif "planner_proposal_rejected" in signature:
        category = "validator_rejected_planning_output"
        recommended_owner = "planner_validator_boundary"
        recovery_semantics = "fix_duplicate_validator_semantics_or_replan"
    else:
        category = "outside_planner_classification_scope"
        recommended_owner = "non_planning_owner"
        recovery_semantics = "classify_by_existing_failure_envelope"

    return {
        "task": envelope.get("task", ""),
        "seed": envelope.get("seed", ""),
        "family": envelope.get("family", ""),
        "root_layer": envelope.get("root_layer", ""),
        "failure_signature": signature,
        "phase": envelope.get("phase", ""),
        "category": category,
        "recommended_owner": recommended_owner,
        "recovery_semantics": recovery_semantics,
        "active_step": active_step,
        "active_step_action_family": active_step_action_family,
        "affordance_count": affordance_count,
        "permitted_action_kinds": permitted_actions,
        "model_action_kind": action_kind,
        "trace_path": str(trace_path or ""),
    }


def classify_report(report_path: Path) -> dict[str, Any]:
    report = _load_json(report_path)
    failures = report.get("failure_envelopes")
    if not isinstance(failures, list):
        failures = []
    classified = [classify_failure(item) for item in failures if isinstance(item, dict)]
    category_counts = Counter(str(item["category"]) for item in classified)
    recovery_counts = Counter(str(item["recovery_semantics"]) for item in classified)
    waiting = [item for item in classified if item["failure_signature"] == PLANNER_WAITING]
    already = [
        item
        for item in classified
        if ALREADY_SATISFIED in str(item["failure_signature"])
    ]
    return {
        "schema_version": "planner-failure-classification-v1",
        "source_report": str(report_path),
        "run_git_sha": (
            report.get("evaluation_run_identity", {})
            .get("canonical_dimensions", "")
            .split('"git_sha":"')[-1]
            .split('"')[0]
            if isinstance(report.get("evaluation_run_identity"), dict)
            else ""
        ),
        "expected_episode_count": report.get("expected_episode_count"),
        "observed_episode_count": report.get("observed_episode_count"),
        "runtime_failure_count": report.get("runtime_failure_count"),
        "planner_waiting_clarification_count": len(waiting),
        "entry_outcome_already_satisfied_count": len(already),
        "category_counts": dict(sorted(category_counts.items())),
        "recovery_semantics_counts": dict(sorted(recovery_counts.items())),
        "failures": classified,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    summary = classify_report(args.report)
    rendered = json.dumps(summary, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

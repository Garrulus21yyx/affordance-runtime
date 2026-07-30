from __future__ import annotations

import json
from pathlib import Path

from scripts.classify_planner_failures import classify_report


def _write_trace(path: Path, *, permitted: list[str], action_kind: str = "ask_user") -> None:
    events = [
        {
            "event_type": "PlannerContextBuilt",
            "payload": {
                "context": {
                    "active_subgoal": "slider_value=7 is available",
                    "active_subgoal_action_family": "",
                    "affordance_count": 2,
                    "permitted_action_kinds": permitted,
                }
            },
        },
        {
            "event_type": "PlannerProposalProduced",
            "payload": {"proposal": {"action_kind": action_kind}},
        },
    ]
    path.write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")


def test_classifies_planner_waiting_with_remaining_action_space(tmp_path: Path) -> None:
    trace = tmp_path / "events.jsonl"
    _write_trace(trace, permitted=["ask_user", "press_key"])
    report = tmp_path / "browsergym-report.json"
    report.write_text(
        json.dumps(
            {
                "expected_episode_count": 1,
                "observed_episode_count": 1,
                "runtime_failure_count": 1,
                "failure_envelopes": [
                    {
                        "task": "use-slider",
                        "seed": 0,
                        "family": "spatial_value",
                        "failure_signature": "planner_waiting_clarification",
                        "artifact_refs": [str(trace)],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = classify_report(report)

    assert summary["planner_waiting_clarification_count"] == 1
    assert summary["category_counts"] == {"model_deferral_with_action_space": 1}
    assert summary["failures"][0]["recovery_semantics"] == "bounded_retry_or_deterministic_choice"


def test_classifies_already_satisfied_as_progress_precheck_owner(tmp_path: Path) -> None:
    trace = tmp_path / "events.jsonl"
    _write_trace(trace, permitted=[])
    report = tmp_path / "browsergym-report.json"
    report.write_text(
        json.dumps(
            {
                "expected_episode_count": 1,
                "observed_episode_count": 1,
                "runtime_failure_count": 1,
                "failure_envelopes": [
                    {
                        "task": "search-engine",
                        "seed": 1,
                        "family": "navigation",
                        "failure_signature": (
                            "task_planning:validation:planner_proposal_rejected:"
                            "entry_outcome_already_satisfied"
                        ),
                        "artifact_refs": [str(trace)],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = classify_report(report)

    assert summary["entry_outcome_already_satisfied_count"] == 1
    assert summary["category_counts"] == {"current_step_already_satisfied_owner": 1}
    assert summary["failures"][0]["recommended_owner"] == "progress_precheck"

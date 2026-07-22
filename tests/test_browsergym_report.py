from __future__ import annotations

from affordance_runtime.benchmarks import browsergym_matrix as matrix
from affordance_runtime.benchmarks import browsergym_report as report_adapter
from affordance_runtime.benchmarks.browsergym_types import BrowserGymEpisodeResult


def _failed_episode(*, task_id: str, actions: list[str]) -> BrowserGymEpisodeResult:
    return BrowserGymEpisodeResult(
        task_id=task_id,
        seed=0,
        runtime_status="done",
        official_success=False,
        official_reward=0.0,
        terminated=True,
        truncated=False,
        action_count=len(actions),
        action_families=actions,
        unsupported_actions=[],
        runtime_error="",
        policy_stopped=False,
        trace_path="trace.jsonl",
    )


def test_matrix_preserves_report_adapter_exports() -> None:
    assert matrix.browsergym_failure_envelope is report_adapter.browsergym_failure_envelope
    assert matrix.cluster_browsergym_failure_envelopes is report_adapter.cluster_browsergym_failure_envelopes
    assert matrix.write_browsergym_report is report_adapter.write_browsergym_report


def test_failure_family_uses_observed_capability_without_task_name_dispatch() -> None:
    envelope = report_adapter.browsergym_failure_envelope(
        _failed_episode(task_id="outside-fixed-manifest", actions=["click", "fill"])
    )

    assert envelope is not None
    assert envelope["family"] == "observed:text_entry"
    assert envelope["action_kind"] == "fill"


def test_failure_family_retains_evidence_gap_when_no_action_was_observed() -> None:
    envelope = report_adapter.browsergym_failure_envelope(
        _failed_episode(task_id="outside-fixed-manifest", actions=[])
    )

    assert envelope is not None
    assert envelope["family"] == "unresolved:no_action_evidence"


def test_declared_protocol_family_precedes_observed_action() -> None:
    envelope = report_adapter.browsergym_failure_envelope(
        _failed_episode(task_id="declared", actions=["fill"]),
        task_family_map={"declared": "controlled-family"},
    )

    assert envelope is not None
    assert envelope["family"] == "controlled-family"

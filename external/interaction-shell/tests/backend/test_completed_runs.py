from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from interaction_shell.api import create_app
from interaction_shell.completed_runs import CompletedRunSummaryResolver


def _write_run(root, *, attempt_id: str = "attempt:" + "a" * 32):
    (root / "cases").mkdir(parents=True)
    (root / "run.json").write_text(
        json.dumps({"identity": {"run_attempt_id": attempt_id}}),
        encoding="utf-8",
    )
    case = {
        "case_id": "case-1",
        "run_attempt_id": attempt_id,
        "status": "done",
        "measurements": {
            "turns": {"value": 3, "measured": True},
            "prompt_tokens": {"value": 100, "measured": True},
            "completion_tokens": {"value": 20, "measured": True},
            "action_policy_recovery_calls": {"value": 1, "measured": True},
            "control_stall_count": {"value": 1, "measured": True},
            "state_oscillation_count": {"value": 0, "measured": True},
        },
    }
    result = root / "cases" / "case-1.json"
    result.write_text(json.dumps(case), encoding="utf-8")
    return result


def test_resolver_reads_only_configured_results_and_exposes_no_absolute_path(tmp_path):
    run = tmp_path / "run"
    result = _write_run(run)
    resolver = CompletedRunSummaryResolver(
        (run,),
        langfuse_base_url="https://langfuse.example.test",
        local_evidence_enabled=True,
    )

    summaries = resolver.list()

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.case_id == "case-1"
    assert summary.turns == 3
    assert summary.provider_input_tokens == 100
    assert summary.langfuse_url.endswith("/sessions/attempt%3A" + "a" * 32)
    assert summary.local_evidence_url == f"/labs/completed-runs/evidence/{summary.locator_id}/result"
    assert str(tmp_path) not in summary.model_dump_json()
    assert resolver.result_path(summary.locator_id) == result.resolve()


def test_resolver_rejects_unknown_locator_and_identity_mismatch(tmp_path):
    run = tmp_path / "run"
    _write_run(run)
    payload = json.loads((run / "cases" / "case-1.json").read_text())
    payload["run_attempt_id"] = "attempt:" + "b" * 32
    (run / "cases" / "case-1.json").write_text(json.dumps(payload))
    resolver = CompletedRunSummaryResolver((run,), local_evidence_enabled=True)

    assert resolver.list() == ()
    with pytest.raises(FileNotFoundError):
        resolver.result_path("0" * 32)


def test_diagnostics_api_is_read_only_summary_and_fixed_result_locator(tmp_path):
    run = tmp_path / "run"
    _write_run(run)
    app = create_app(
        completed_run_resolver=CompletedRunSummaryResolver(
            (run,), local_evidence_enabled=True
        ),
        evidence_access_key="engineering-test-key",
    )
    with TestClient(app) as client:
        listed = client.get("/labs/completed-runs")
        summary = listed.json()[0]
        unauthorized = client.get(summary["local_evidence_url"])
        result = client.get(
            summary["local_evidence_url"],
            headers={"X-Engineering-Key": "engineering-test-key"},
        )
        post = client.post("/labs/completed-runs", json={})
        traversal = client.get("/labs/completed-runs/evidence/../../run.json/result")

    assert listed.status_code == 200
    assert unauthorized.status_code == 404
    assert result.status_code == 200
    assert result.json()["case_id"] == "case-1"
    assert post.status_code == 405
    assert traversal.status_code in {404, 422}

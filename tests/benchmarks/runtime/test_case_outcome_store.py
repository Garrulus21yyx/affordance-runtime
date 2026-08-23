import os
import sqlite3
import subprocess
import sys
from dataclasses import replace

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from affordance_runtime.benchmarks.target_loop.result_store import (
    CaseOutcomeRecord,
    CaseRecordRevision,
    CleanupDisposition,
    ExportDisposition,
    ProjectionDisposition,
    ReportDisposition,
    RunResultStoreError,
    SQLiteRunResultStore,
    SuiteReportDisposition,
)


def _body(case_id: str = "case:sequence") -> CaseOutcomeRecord:
    return CaseOutcomeRecord(case_id, CaseRecordRevision.BODY, "done")


def _cleanup(body: CaseOutcomeRecord) -> CaseOutcomeRecord:
    return replace(
        body,
        revision=CaseRecordRevision.CLEANUP,
        cleanup_disposition=CleanupDisposition.SUCCEEDED,
    )


def _final(cleanup: CaseOutcomeRecord) -> CaseOutcomeRecord:
    return replace(
        cleanup,
        revision=CaseRecordRevision.FINAL,
        projection_disposition=ProjectionDisposition.PROJECTED,
        report_disposition=ReportDisposition.COMMITTED,
        export_disposition=ExportDisposition.EXPORTED,
        finished=True,
    )


def test_case_outcome_revisions_are_monotonic_idempotent_and_finish_atomically(tmp_path) -> None:
    store = SQLiteRunResultStore(tmp_path / "results.sqlite3")
    body = _body()
    cleanup = _cleanup(body)
    final = _final(cleanup)

    store.commit_case_outcome(body)
    store.commit_case_outcome(body)
    store.commit_case_outcome(cleanup)
    store.commit_case_outcome(cleanup)
    store.commit_case_outcome(final)
    store.commit_case_outcome(final)

    assert store.load_case_outcome(body.case_id) == final
    assert store.load_case_phases(body.case_id) == ("CASE_FINISHED",)
    assert store.load_lifecycle(body.case_id)["current_phase"] == "CASE_FINISHED"
    with pytest.raises(RunResultStoreError, match="stale"):
        store.commit_case_outcome(cleanup)
    with pytest.raises(RunResultStoreError, match="stale"):
        store.commit_case_outcome(body)


def test_case_outcome_rejects_skipped_and_conflicting_equal_revisions(tmp_path) -> None:
    store = SQLiteRunResultStore(tmp_path / "results.sqlite3")
    body = _body()
    store.commit_case_outcome(body)

    with pytest.raises(RunResultStoreError, match="equal-revision"):
        store.commit_case_outcome(replace(body, failure_code="different"))
    with pytest.raises(RunResultStoreError, match="stale or skipped"):
        store.commit_case_outcome(_final(_cleanup(body)))


def test_loaded_case_outcome_fails_closed_when_official_join_payload_diverges(tmp_path) -> None:
    from affordance_runtime.benchmarks.target_loop.outcome_checkpoint import OfficialOutcomeCheckpoint
    from affordance_runtime.evaluation import (
        TaskEvaluation,
        TaskEvaluationStatus,
        TaskOutcomeFact,
        TaskOutcomeKind,
    )

    store = SQLiteRunResultStore(tmp_path / "results.sqlite3")
    checkpoint = OfficialOutcomeCheckpoint.from_evaluation(
        "case:official",
        TaskEvaluation(
            "task:official",
            "world:final",
            TaskEvaluationStatus.COMPLETE,
            "complete",
            completion_evidence_refs=("fact:complete",),
            outcome=TaskOutcomeFact(
                TaskOutcomeKind.TERMINAL_SUCCESS,
                "native_success",
                ("fact:complete",),
            ),
        ),
    )
    store.commit_official_outcome(checkpoint)
    digest = checkpoint.checkpoint_id.removeprefix("checkpoint:")
    body = CaseOutcomeRecord(
        checkpoint.case_id,
        CaseRecordRevision.BODY,
        "done",
        official_checkpoint_id=checkpoint.checkpoint_id,
        official_checkpoint_digest=digest,
    )
    store.commit_case_outcome(body)
    assert store.load_case_outcome(checkpoint.case_id) == body

    with sqlite3.connect(store.location) as connection:
        connection.execute(
            "UPDATE official_outcomes SET outcome_code = 'tampered' WHERE case_id = ?",
            (checkpoint.case_id,),
        )
    with pytest.raises(RunResultStoreError, match="divergent"):
        store.load_case_outcome(checkpoint.case_id)


def test_subprocess_late_body_writer_cannot_overwrite_final(tmp_path) -> None:
    store = SQLiteRunResultStore(tmp_path / "results.sqlite3")
    body = _body("case:late-writer")
    store.commit_case_outcome(body)
    store.commit_case_outcome(_cleanup(body))
    final = _final(_cleanup(body))
    store.commit_case_outcome(final)
    script = """
import sys
from pathlib import Path
from affordance_runtime.benchmarks.target_loop.result_store import CaseOutcomeRecord, CaseRecordRevision, RunResultStoreError, SQLiteRunResultStore
store = SQLiteRunResultStore(Path(sys.argv[1]))
try:
    store.commit_case_outcome(CaseOutcomeRecord('case:late-writer', CaseRecordRevision.BODY, 'done'))
except RunResultStoreError:
    raise SystemExit(0)
raise SystemExit(9)
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "src:tests"
    completed = subprocess.run(
        (sys.executable, "-c", script, str(store.location)),
        cwd="/home/yang/projects/affordance-runtime",
        env=environment,
        check=False,
    )

    assert completed.returncode == 0
    assert store.load_case_outcome(body.case_id) == final


@given(
    expected_case_count=st.integers(min_value=0, max_value=100),
    disposition=st.sampled_from(
        (
            (ReportDisposition.NOT_ATTEMPTED, ExportDisposition.NOT_ATTEMPTED, ""),
            (ReportDisposition.COMMITTED, ExportDisposition.EXPORTED, ""),
            (ReportDisposition.FAILED, ExportDisposition.NOT_ATTEMPTED, "suite_report_commit_failed"),
            (ReportDisposition.COMMITTED, ExportDisposition.FAILED, "suite_report_export_failed"),
        )
    ),
)
@settings(suppress_health_check=(HealthCheck.function_scoped_fixture,))
def test_suite_report_disposition_round_trips_as_one_typed_current_row(
    tmp_path,
    expected_case_count,
    disposition,
) -> None:
    store = SQLiteRunResultStore(tmp_path / "suite-disposition.sqlite3")
    report, export, failure_code = disposition
    expected = SuiteReportDisposition(
        f"run:property:{expected_case_count}:{report.value}:{export.value}",
        expected_case_count,
        report,
        export,
        failure_code,
    )

    store.record_suite_report_disposition(expected)

    assert store.load_suite_report_disposition(expected.run_id) == expected


def test_late_suite_start_cannot_overwrite_terminal_report_disposition(tmp_path) -> None:
    store = SQLiteRunResultStore(tmp_path / "suite-late-start.sqlite3")
    terminal = SuiteReportDisposition(
        "run:late-start",
        1,
        ReportDisposition.COMMITTED,
        ExportDisposition.EXPORTED,
    )
    store.record_suite_report_disposition(terminal)

    with pytest.raises(RunResultStoreError, match="already terminal"):
        store.record_suite_report_disposition(
            SuiteReportDisposition(
                terminal.run_id,
                1,
                ReportDisposition.NOT_ATTEMPTED,
                ExportDisposition.NOT_ATTEMPTED,
            )
        )

    assert store.load_suite_report_disposition(terminal.run_id) == terminal

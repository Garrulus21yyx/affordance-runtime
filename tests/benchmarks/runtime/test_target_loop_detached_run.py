import json
import os
import sys
import time
from dataclasses import replace

import pytest

from affordance_runtime.benchmarks.target_loop.detached_run import (
    DETACHED_RUN_SCHEMA_VERSION,
    detached_status,
    launch_detached,
)
from affordance_runtime.benchmarks.target_loop.result_store import (
    CaseOutcomeRecord,
    CaseRecordRevision,
    CleanupDisposition,
    ExportDisposition,
    ProjectionDisposition,
    ReportDisposition,
    SQLiteRunResultStore,
    SuiteReportDisposition,
)


def test_detached_run_is_session_leader_with_durable_real_pid(tmp_path) -> None:
    output_dir = tmp_path / "run"
    identity = launch_detached(
        (sys.executable, "-c", "import time; time.sleep(0.2)"),
        output_dir,
        cwd=tmp_path,
    )

    assert identity.schema_version == DETACHED_RUN_SCHEMA_VERSION
    assert identity.pid > 0
    assert identity.session_id == identity.pid
    assert os.getsid(identity.pid) == identity.pid
    assert (output_dir / "run.pid").read_text(encoding="utf-8") == f"{identity.pid}\n"
    launch = json.loads((output_dir / "launch.json").read_text(encoding="utf-8"))
    assert launch["pid"] == identity.pid
    assert launch["session_id"] == identity.pid
    assert detached_status(output_dir)["state"] == "running"

    deadline = time.monotonic() + 2
    while detached_status(output_dir)["state"] == "running" and time.monotonic() < deadline:
        time.sleep(0.02)
    assert detached_status(output_dir)["state"] == "stopped_without_report"
    _reap_if_child(identity.pid)


def test_detached_status_uses_formal_reports_after_process_exit(tmp_path) -> None:
    output_dir = tmp_path / "reported"
    identity = launch_detached((sys.executable, "-c", "pass"), output_dir, cwd=tmp_path)
    (output_dir / "run.json").write_text("{}\n", encoding="utf-8")
    (output_dir / "summary.json").write_text("{}\n", encoding="utf-8")

    deadline = time.monotonic() + 2
    status = detached_status(output_dir)
    while status["state"] == "running" and time.monotonic() < deadline:
        time.sleep(0.02)
        status = detached_status(output_dir)
    assert status["state"] == "completed_reported"
    assert status["run_report"] == str(output_dir / "run.json")
    assert status["summary_report"] == str(output_dir / "summary.json")
    _reap_if_child(identity.pid)


def test_detached_launch_refuses_to_overwrite_existing_run_identity(tmp_path) -> None:
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    (output_dir / "run.pid").write_text("123\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already contains run evidence"):
        launch_detached((sys.executable, "-c", "pass"), output_dir)


def test_detached_status_distinguishes_complete_cases_suite_failure_and_partial_run(tmp_path) -> None:
    output_dir = tmp_path / "sqlite-status"
    identity = launch_detached((sys.executable, "-c", "pass"), output_dir, cwd=tmp_path)
    deadline = time.monotonic() + 2
    while detached_status(output_dir)["state"] == "running" and time.monotonic() < deadline:
        time.sleep(0.02)
    store = SQLiteRunResultStore(output_dir / "run-results.sqlite3")
    run_id = "run:detached-status"
    store.record_suite_report_disposition(
        SuiteReportDisposition(
            run_id,
            2,
            ReportDisposition.NOT_ATTEMPTED,
            ExportDisposition.NOT_ATTEMPTED,
        )
    )
    body = CaseOutcomeRecord("case:one", CaseRecordRevision.BODY, "done")
    store.commit_case_outcome(body)
    assert detached_status(output_dir)["durable_status"] == "partial_run"

    for case_id in ("case:one", "case:two"):
        body = CaseOutcomeRecord(case_id, CaseRecordRevision.BODY, "done")
        cleanup = replace(
            body,
            revision=CaseRecordRevision.CLEANUP,
            cleanup_disposition=CleanupDisposition.SUCCEEDED,
        )
        final = replace(
            cleanup,
            revision=CaseRecordRevision.FINAL,
            projection_disposition=ProjectionDisposition.PROJECTED,
            report_disposition=ReportDisposition.COMMITTED,
            export_disposition=ExportDisposition.EXPORTED,
            finished=True,
        )
        if case_id == "case:one":
            store.commit_case_outcome(cleanup)
        else:
            store.commit_case_outcome(body)
            store.commit_case_outcome(cleanup)
        store.commit_case_outcome(final)
    complete = detached_status(output_dir)
    assert complete["durable_status"] == "case_complete"
    assert complete["state"] == "stopped_with_complete_cases"

    store.record_suite_report_disposition(
        SuiteReportDisposition(
            run_id,
            2,
            ReportDisposition.FAILED,
            ExportDisposition.NOT_ATTEMPTED,
            "suite_report_commit_failed",
        )
    )
    failed = detached_status(output_dir)
    assert failed["durable_status"] == "suite_report_failed"
    assert failed["state"] == "stopped_with_suite_report_failure"
    _reap_if_child(identity.pid)


def _reap_if_child(pid: int) -> None:
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass

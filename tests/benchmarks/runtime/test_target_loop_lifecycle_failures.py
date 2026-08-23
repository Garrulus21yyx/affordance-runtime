import asyncio
import json
import sqlite3
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from affordance_runtime.agent import RunStatus
from affordance_runtime.agent.episode_snapshot import EpisodeSnapshot
from affordance_runtime.agent.observability import RunTraceRecorder
from affordance_runtime.benchmarks.target_loop.case_projection import project_case_result
from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest, CaseFailureOrigin
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.outcome_checkpoint import (
    OfficialOutcomeCheckpointRecorder,
)
from affordance_runtime.benchmarks.target_loop.reporting import write_case_report
from affordance_runtime.benchmarks.target_loop.result_store import (
    CaseRecordRevision,
    ProjectionDisposition,
    RunResultStoreError,
    SQLiteRunResultStore,
)
from affordance_runtime.benchmarks.target_loop.runner import run_suite
from affordance_runtime.evaluation import (
    TaskEvaluation,
    TaskEvaluationStatus,
    TaskOutcomeFact,
    TaskOutcomeKind,
)


def test_environment_factory_failure_is_contained_and_suite_continues() -> None:
    manifest = get_manifest("internal-core", "deterministic", 7)

    def fail(_instrumentation):
        raise RuntimeError("fixture construction failed")

    failed = replace(manifest.cases[0], environment_factory=fail, expected_terminal_statuses=(RunStatus.FAILED,))
    reduced = BenchmarkManifest(
        manifest.schema_version,
        manifest.suite_id,
        manifest.profile_id,
        manifest.seed,
        (failed, manifest.cases[1]),
    )
    result = asyncio.run(run_suite(reduced))

    assert result.cases[0].execution_completed is False
    assert "environment factory" in result.cases[0].failure_reason
    assert result.cases[1].execution_completed is True


def test_composition_failure_closes_created_environment_once() -> None:
    manifest = get_manifest("internal-core", "deterministic", 7)
    closed = []
    original = manifest.cases[0]

    def environment(instrumentation):
        value = original.environment_factory(instrumentation)

        async def close():
            closed.append("closed")

        value.close = close
        return value

    def composition(_instrumentation):
        raise RuntimeError("composition failed")

    case = replace(
        original,
        environment_factory=environment,
        composition_factory=composition,
        expected_terminal_statuses=(RunStatus.FAILED,),
    )
    result = asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (case,),
            )
        )
    )

    assert result.cases[0].execution_completed is False
    assert "composition factory" in result.cases[0].failure_reason
    assert closed == ["closed"]


def test_sync_hung_cleanup_does_not_block_loop_and_persists_report(monkeypatch, tmp_path) -> None:
    from affordance_runtime.benchmarks.target_loop import runner

    monkeypatch.setattr(runner, "_CLEANUP_TIMEOUT_S", 0.02)
    manifest = get_manifest("internal-core", "deterministic", 7)
    original = manifest.cases[0]
    baseline = asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (original,),
            )
        )
    ).cases[0]
    phases = []

    def environment(instrumentation):
        value = original.environment_factory(instrumentation)

        def close():
            time.sleep(0.2)

        value.close = close
        return value

    case = replace(original, environment_factory=environment)
    started = time.perf_counter()
    result = asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (case,),
            ),
            case_completed=lambda _index, item: write_case_report(item, tmp_path),
            trace_dir=tmp_path,
            status_changed=phases.append,
        )
    ).cases[0]

    assert time.perf_counter() - started < 0.15
    assert result.cleanup_failure_code == "cleanup_timeout"
    assert result.cleanup_status == "timeout"
    assert result.cleanup_diagnostic is not None
    assert result.cleanup_diagnostic.elapsed_ms >= 20
    assert "20 ms deadline" in result.cleanup_diagnostic.safe_message
    assert (tmp_path / "cases" / f"{case.case_id}.json").is_file()
    assert phases == [
        "running",
        "finalizing",
        "primary_persisted",
        "cleanup",
        "reporting",
    ]
    store = SQLiteRunResultStore(tmp_path / "run-results.sqlite3")
    with sqlite3.connect(store.location) as connection:
        checkpoint = connection.execute(
            """
            SELECT checkpoint_id, evaluation_status, run_status, evidence_refs_json
            FROM official_outcomes WHERE case_id = ?
            """,
            (case.case_id,),
        ).fetchone()
    assert checkpoint is not None
    assert checkpoint[0].startswith("checkpoint:")
    assert checkpoint[1:3] == ("complete", "done")
    assert json.loads(checkpoint[3])
    trace_path = tmp_path / "traces" / case.case_id / "trace.jsonl"
    events = [json.loads(line) for line in trace_path.read_text().splitlines()]
    primary_index = next(index for index, event in enumerate(events) if event["event"] == "primary_result_available")
    cleanup_index = next(
        index
        for index, event in enumerate(events)
        if event["event"] == "benchmark_lifecycle_phase" and event["phase"] == "cleanup"
    )
    assert primary_index < cleanup_index
    assert events[primary_index] == {
        "schema_version": "gui-agent-trace.v1",
        "run_id": events[primary_index]["run_id"],
        "sequence": events[primary_index]["sequence"],
        "event": "primary_result_available",
        "case_id": case.case_id,
        "checkpoint_id": checkpoint[0],
        "status": "done",
        "step_count": result.measurements["turns"].value,
    }
    lifecycle = [event for event in events if event["event"] == "benchmark_lifecycle_phase"]
    assert [event["phase"] for event in lifecycle] == [
        "finalizing",
        "primary_persisted",
        "cleanup",
        "reporting",
    ]
    assert lifecycle[0]["primary_result_available"] is False
    official = next(event for event in events if event["event"] == "native_evaluator_returned")
    assert official["evaluation_status"] == "complete"
    assert official["checkpoint_id"] == checkpoint[0]
    assert official["evidence_refs"] == json.loads(checkpoint[3])
    persistence = next(event for event in events if event["event"] == "official_outcome_persistence")
    assert persistence["persistence_status"] == "committed"
    assert persistence["checkpoint_id"] == checkpoint[0]
    assert store.load_lifecycle(case.case_id)["cleanup_status"] == "timeout"
    for name in (
        "policy_calls",
        "provider_attempts",
        "executions",
        "stop_send_count",
    ):
        assert result.measurements[name].value == baseline.measurements[name].value


def test_async_hung_cleanup_hits_independent_deadline(monkeypatch) -> None:
    from affordance_runtime.benchmarks.target_loop import runner

    monkeypatch.setattr(runner, "_CLEANUP_TIMEOUT_S", 0.02)
    manifest = get_manifest("internal-core", "deterministic", 7)
    original = manifest.cases[0]

    def environment(instrumentation):
        value = original.environment_factory(instrumentation)

        async def close():
            await asyncio.sleep(0.2)

        value.close = close
        return value

    result = asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (replace(original, environment_factory=environment),),
            )
        )
    ).cases[0]

    assert result.cleanup_failure_code == "cleanup_timeout"
    assert result.cleanup_status == "timeout"
    assert result.cleanup_exception_class == "CleanupTimeoutError"


def test_watchdog_cancel_wait_has_bounded_grace(monkeypatch) -> None:
    from affordance_runtime.benchmarks.target_loop import runner

    monkeypatch.setattr(runner, "_WATCHDOG_CANCEL_GRACE_S", 0.005)

    async def cancellation_resistant() -> None:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            await asyncio.Event().wait()

    loop = asyncio.new_event_loop()
    started = time.perf_counter()
    try:
        with pytest.raises(runner._HarnessWatchdogTimeout) as raised:
            loop.run_until_complete(runner._run_with_watchdog(cancellation_resistant(), 0.005))
        assert raised.value.task_detached is True
        assert time.perf_counter() - started < 0.05
        assert runner.abandon_detached_watchdog_tasks(loop) == 1
    finally:
        loop.close()


def test_terminal_runtime_fact_has_independent_case_return_deadline(monkeypatch) -> None:
    from affordance_runtime.benchmarks.target_loop import runner

    monkeypatch.setattr(runner, "_CASE_RETURN_TIMEOUT_S", 0.005)
    finished = asyncio.Event()

    async def terminal_but_not_returned() -> None:
        finished.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            return

    started = time.perf_counter()
    with pytest.raises(runner._CaseReturnTimeout) as raised:
        asyncio.run(
            runner._run_with_watchdog(
                terminal_but_not_returned(),
                10,
                runtime_finished=finished,
            )
        )

    assert raised.value.task_detached is False
    assert time.perf_counter() - started < 0.1


def test_case_return_timeout_persists_preliminary_result_before_cleanup(monkeypatch, tmp_path) -> None:
    from affordance_runtime.benchmarks.target_loop import runner

    manifest = get_manifest("internal-core", "deterministic", 7)
    case = manifest.cases[0]
    monkeypatch.setattr(runner, "_CASE_RETURN_TIMEOUT_S", 0.005)

    async def terminal_but_hung(_case, _runtime, _environment, _task, instrumentation, _holder):
        instrumentation.run_finished(SimpleNamespace(status=RunStatus.FAILED))
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            return None

    monkeypatch.setattr(runner, "_run_episode", terminal_but_hung)
    result = asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (case,),
            ),
            trace_dir=tmp_path,
        )
    ).cases[0]

    store = SQLiteRunResultStore(tmp_path / "run-results.sqlite3")
    phases = store.load_case_phases(case.case_id)
    assert result.failure_reason == "case return timeout"
    assert result.failure_facts.watchdog_code == "case_return_timeout"
    assert phases.index("RESULT_PERSISTED") < phases.index("CLEANUP_STARTED")


def test_watchdog_report_retains_persisted_official_outcome(tmp_path) -> None:
    instrumentation = BenchmarkInstrumentation(
        trace_recorder=RunTraceRecorder(),
    )
    recorder = OfficialOutcomeCheckpointRecorder(
        "synthetic-case",
        SQLiteRunResultStore(tmp_path / "run-results.sqlite3"),
        instrumentation.trace_recorder,
    )
    evaluation = TaskEvaluation(
        "synthetic-task",
        "world:final",
        TaskEvaluationStatus.COMPLETE,
        "native verifier confirmed completion",
        completion_evidence_refs=("fact:result:confirmed",),
        outcome=TaskOutcomeFact(
            TaskOutcomeKind.TERMINAL_SUCCESS,
            "native_success",
            ("fact:result:confirmed",),
        ),
    )
    recorder.native_evaluator_returned(evaluation)
    instrumentation.set_custom_metric("official_success_count", 1)
    timeout = RuntimeError("watchdog")
    instrumentation.record_watchdog("case_timeout", timeout)

    result = project_case_result(
        "synthetic-case",
        None,
        instrumentation,
        20.0,
        "case timeout",
        final_snapshot=EpisodeSnapshot(
            4,
            2,
            0,
            3,
            "complete",
            "changed",
            "satisfied",
            "native",
            "",
            0,
            0,
            0,
            "submit_final_response",
            0,
            1,
            "complete",
            "",
        ),
        official_checkpoint=recorder.durable_checkpoint,
    )

    assert result.status == "done"
    assert result.execution_completed is True
    assert result.partial_episode_available is False
    assert result.watchdog_triggered is True
    assert result.failure_facts.task_outcome_kind == "terminal_success"
    assert result.failure_facts.task_outcome_code == "native_success"
    with sqlite3.connect(tmp_path / "run-results.sqlite3") as connection:
        evidence_json = connection.execute(
            "SELECT evidence_refs_json FROM official_outcomes WHERE case_id = ?",
            ("synthetic-case",),
        ).fetchone()[0]
    assert json.loads(evidence_json) == ["fact:result:confirmed"]


def test_durable_checkpoint_precedes_conflicting_memory_result(tmp_path) -> None:
    instrumentation = BenchmarkInstrumentation(trace_recorder=RunTraceRecorder())
    recorder = OfficialOutcomeCheckpointRecorder(
        "synthetic-case",
        SQLiteRunResultStore(tmp_path / "run-results.sqlite3"),
        instrumentation.trace_recorder,
    )
    recorder.native_evaluator_returned(
        TaskEvaluation(
            "synthetic-task",
            "world:final",
            TaskEvaluationStatus.COMPLETE,
            "native verifier confirmed completion",
            completion_evidence_refs=("fact:result:confirmed",),
            outcome=TaskOutcomeFact(
                TaskOutcomeKind.TERMINAL_SUCCESS,
                "native_success",
                ("fact:result:confirmed",),
            ),
        )
    )
    conflicting = SimpleNamespace(
        status=RunStatus.BLOCKED,
        observation_count=1,
        execution_count=0,
        step_count=0,
        sent_unknown_count=0,
        task_outcome=TaskOutcomeFact(
            TaskOutcomeKind.TERMINAL_FAILURE,
            "stale_failure",
            ("fact:stale:failure",),
        ),
        outcome="",
        supervisor_state=None,
        policy_failure=None,
        failure_code=None,
        runtime_failure=None,
        last_step=None,
    )

    result = project_case_result(
        "synthetic-case",
        conflicting,
        instrumentation,
        1.0,
        "",
        official_checkpoint=recorder.durable_checkpoint,
    )

    assert result.status == "done"
    assert result.failure_facts.task_outcome_kind == "terminal_success"
    assert result.failure_facts.task_outcome_code == "native_success"


def test_failed_checkpoint_write_is_not_used_as_durable_outcome(
    tmp_path,
) -> None:
    phases = []
    trace = RunTraceRecorder()

    class FailingStore:
        location = tmp_path / "run-results.sqlite3"

        def commit_official_outcome(self, _checkpoint) -> None:
            raise RunResultStoreError("synthetic persistence failure")

    recorder = OfficialOutcomeCheckpointRecorder(
        "synthetic-case",
        FailingStore(),
        trace,
        phases.append,
    )
    recorder.native_evaluator_returned(
        TaskEvaluation(
            "synthetic-task",
            "world:final",
            TaskEvaluationStatus.INCOMPLETE,
            "native verifier returned",
        )
    )

    assert recorder.checkpoint is not None
    assert recorder.durable_checkpoint is None
    assert recorder.persistence_error == "RunResultStoreError"
    assert phases == ["finalizing"]
    native = next(item for item in trace.events if item["event"] == "native_evaluator_returned")
    event = next(item for item in trace.events if item["event"] == "official_outcome_persistence")
    assert native["checkpoint_id"] == event["checkpoint_id"]
    assert event["persistence_status"] == "failed"
    assert event["checkpoint_id"].startswith("checkpoint:")


def test_failed_checkpoint_write_projects_typed_harness_failure(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        SQLiteRunResultStore,
        "commit_official_outcome",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RunResultStoreError("synthetic persistence failure")),
    )
    manifest = get_manifest("internal-core", "deterministic", 7)
    case = manifest.cases[0]
    result = asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (case,),
            ),
            trace_dir=tmp_path,
        )
    ).cases[0]

    assert result.status == "failed"
    assert result.execution_completed is False
    assert result.failure_origin.value == "harness_persistence"
    assert result.failure_code == "official_checkpoint_persistence_failed"
    assert result.exception_class == "OfficialOutcomePersistenceError"
    with sqlite3.connect(tmp_path / "run-results.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM official_outcomes").fetchone()[0] == 0


def test_json_export_failure_keeps_regenerable_sqlite_report(
    monkeypatch,
    tmp_path,
) -> None:
    from affordance_runtime.benchmarks.target_loop import result_store as store_module

    original_projection = store_module._write_json_projection

    def fail_case_export(path, data):
        if path.parent.name == "cases":
            raise OSError("synthetic export failure")
        return original_projection(path, data)

    monkeypatch.setattr(store_module, "_write_json_projection", fail_case_export)
    manifest = get_manifest("internal-core", "deterministic", 7)
    case = manifest.cases[0]
    result = asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (case,),
            ),
            trace_dir=tmp_path,
        )
    ).cases[0]

    store = SQLiteRunResultStore(tmp_path / "run-results.sqlite3")
    lifecycle = store.load_lifecycle(case.case_id)
    assert lifecycle["report_status"] == "failed"
    assert lifecycle["report_failure_code"] == "json_export_failed"
    with sqlite3.connect(store.location) as connection:
        payload = connection.execute(
            "SELECT payload_json FROM case_reports WHERE case_id = ?",
            (case.case_id,),
        ).fetchone()[0]
    assert json.loads(payload)["failure_facts"]["component_code"] == result.failure_facts.component_code

    monkeypatch.setattr(store_module, "_write_json_projection", original_projection)
    regenerated = store.export_case_report(case.case_id, tmp_path)
    assert regenerated.is_file()


def test_report_payload_commit_failure_is_not_mislabeled_as_json_export(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_commit(*_args, **_kwargs):
        raise RunResultStoreError("synthetic report commit failure")

    monkeypatch.setattr(SQLiteRunResultStore, "commit_case_report", fail_commit)
    manifest = get_manifest("internal-core", "deterministic", 7)
    case = manifest.cases[0]
    asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (case,),
            ),
            trace_dir=tmp_path,
        )
    )

    store = SQLiteRunResultStore(tmp_path / "run-results.sqlite3")
    lifecycle = store.load_lifecycle(case.case_id)
    assert lifecycle["report_status"] == "failed"
    assert lifecycle["report_failure_code"] == "report_payload_commit_failed"
    with sqlite3.connect(store.location) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM case_reports WHERE case_id = ?",
                (case.case_id,),
            ).fetchone()[0]
            == 0
        )


def test_case_lifecycle_is_persisted_at_owner_boundaries(tmp_path) -> None:
    manifest = get_manifest("internal-core", "deterministic", 7)
    case = manifest.cases[0]

    asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (case,),
            ),
            trace_dir=tmp_path,
        )
    )

    store = SQLiteRunResultStore(tmp_path / "run-results.sqlite3")
    assert store.load_case_phases(case.case_id) == (
        "CASE_STARTED",
        "ENVIRONMENT_READY",
        "CASE_BODY_RETURNED",
        "RESULT_PERSISTED",
        "CLEANUP_STARTED",
        "CLEANUP_FINISHED",
        "FINAL_ATTEMPT",
        "CASE_FINISHED",
    )
    assert store.load_lifecycle(case.case_id)["current_phase"] == "CASE_FINISHED"


def test_hung_report_commit_has_independent_deadline_and_typed_failure(
    monkeypatch,
    tmp_path,
) -> None:
    from affordance_runtime.benchmarks.target_loop import runner

    monkeypatch.setattr(runner, "_REPORT_TIMEOUT_S", 0.02)

    def hang_commit(*args, **kwargs):
        del args, kwargs
        time.sleep(0.2)

    monkeypatch.setattr(SQLiteRunResultStore, "commit_case_report", hang_commit)
    manifest = get_manifest("internal-core", "deterministic", 7)
    case = manifest.cases[0]
    started = time.perf_counter()

    result = asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (case,),
            ),
            trace_dir=tmp_path,
        )
    ).cases[0]

    assert time.perf_counter() - started < 0.15
    assert result.failure_origin.value == "harness_persistence"
    assert result.failure_code == "report_payload_commit_failed"


def test_local_jsonl_failure_preserves_runtime_truth_but_invalidates_benchmark_acceptance(monkeypatch, tmp_path) -> None:
    def fail_open_emit(self, event_type, **_payload):
        self.errors.append(f"{event_type}:SyntheticTraceFailure")

    monkeypatch.setattr(RunTraceRecorder, "_emit", fail_open_emit)
    manifest = get_manifest("internal-core", "deterministic", 7)
    case = manifest.cases[0]

    suite = asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (case,),
            ),
            trace_dir=tmp_path,
        )
    )
    result = suite.cases[0]

    assert result.status == "done"
    assert result.failure_origin.value == "none"
    assert result.measurements["trace_recording_failures"].value > 0
    assert not suite.acceptance.accepted
    assert any("trace_recording_failures" in error for error in suite.acceptance.acceptance_errors)


def test_final_attempt_trace_failure_is_included_before_acceptance_projection(monkeypatch, tmp_path) -> None:
    original_emit = RunTraceRecorder._emit

    def fail_final_emit(self, event_type, **payload):
        if event_type == "case_lifecycle_phase" and payload.get("phase") == "FINAL_ATTEMPT":
            self.errors.append("FINAL_ATTEMPT:SyntheticTraceFailure")
            return
        original_emit(self, event_type, **payload)

    monkeypatch.setattr(RunTraceRecorder, "_emit", fail_final_emit)
    manifest = get_manifest("internal-core", "deterministic", 7)
    suite = asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (manifest.cases[0],),
            ),
            trace_dir=tmp_path,
        )
    )
    result = suite.cases[0]

    assert result.measurements["trace_recording_failures"].value == 1
    assert not suite.acceptance.accepted
    assert any("trace_recording_failures" in error for error in suite.acceptance.acceptance_errors)


def test_sync_and_async_target_closed_cleanup_are_idempotent_success() -> None:
    TargetClosedError = type("TargetClosedError", (RuntimeError,), {})

    manifest = get_manifest("internal-core", "deterministic", 7)
    original = manifest.cases[0]
    results = []
    for async_owner in (False, True):

        def environment(instrumentation, *, async_owner=async_owner):
            value = original.environment_factory(instrumentation)
            if async_owner:

                async def close():
                    raise TargetClosedError("synthetic already closed")

            else:

                def close():
                    raise TargetClosedError("synthetic already closed")

            value.close = close
            return value

        results.append(
            asyncio.run(
                run_suite(
                    BenchmarkManifest(
                        manifest.schema_version,
                        manifest.suite_id,
                        manifest.profile_id,
                        manifest.seed,
                        (replace(original, environment_factory=environment),),
                    )
                )
            ).cases[0]
        )

    assert [item.cleanup_status for item in results] == [
        "already_closed",
        "already_closed",
    ]
    assert all(item.cleanup_failure_code == "" for item in results)
    assert all(item.execution_completed for item in results)


def test_projection_failure_occurs_after_cleanup_and_is_durable_as_orthogonal_disposition(
    monkeypatch,
    tmp_path,
) -> None:
    from affordance_runtime.benchmarks.target_loop import runner

    original_projection = runner.project_case_result

    def fail_projection(*args, **kwargs):
        raise RuntimeError("synthetic projection failure")

    monkeypatch.setattr(runner, "project_case_result", fail_projection)
    manifest = get_manifest("internal-core", "deterministic", 7)
    case = manifest.cases[0]
    result = asyncio.run(run_suite(
        BenchmarkManifest(
            manifest.schema_version,
            manifest.suite_id,
            manifest.profile_id,
            manifest.seed,
            (case,),
        ),
        trace_dir=tmp_path,
    )).cases[0]
    monkeypatch.setattr(runner, "project_case_result", original_projection)

    stored = SQLiteRunResultStore(tmp_path / "run-results.sqlite3").load_case_outcome(case.case_id)
    assert result.failure_origin is CaseFailureOrigin.HARNESS_PROJECTION
    assert result.cleanup_status == "succeeded"
    assert stored is not None
    assert stored.revision is CaseRecordRevision.FINAL
    assert stored.projection_disposition is ProjectionDisposition.FAILED
    assert stored.finished


def test_final_commit_failure_leaves_cleanup_revision_and_no_finished_phase(monkeypatch, tmp_path) -> None:
    original_commit = SQLiteRunResultStore.commit_case_outcome

    def fail_final(self, record):
        if record.revision is CaseRecordRevision.FINAL:
            raise RunResultStoreError("synthetic final commit failure")
        return original_commit(self, record)

    monkeypatch.setattr(SQLiteRunResultStore, "commit_case_outcome", fail_final)
    manifest = get_manifest("internal-core", "deterministic", 7)
    case = manifest.cases[0]
    asyncio.run(run_suite(
        BenchmarkManifest(
            manifest.schema_version,
            manifest.suite_id,
            manifest.profile_id,
            manifest.seed,
            (case,),
        ),
        trace_dir=tmp_path,
    ))

    store = SQLiteRunResultStore(tmp_path / "run-results.sqlite3")
    stored = store.load_case_outcome(case.case_id)
    assert stored is not None
    assert stored.revision is CaseRecordRevision.CLEANUP
    assert not stored.finished
    assert "CASE_FINISHED" not in store.load_case_phases(case.case_id)
    events = [
        json.loads(line)
        for line in (tmp_path / "traces" / case.case_id / "trace.jsonl").read_text().splitlines()
    ]
    terminal = [event for event in events if event["event"] == "benchmark_case_finished"]
    assert len(terminal) == 1
    assert terminal[0]["final_commit_disposition"] == "failed"


def test_terminal_case_event_is_exactly_once_after_finalization_and_before_viewer_close(monkeypatch, tmp_path) -> None:
    from affordance_runtime.benchmarks.target_loop import runner

    recorders = []

    class OrderingRecorder(RunTraceRecorder):
        def __init__(self, directory):
            super().__init__(directory)
            self.order = []
            recorders.append(self)

        def benchmark_case_finished(self, **event):
            self.order.append(("terminal", dict(event)))
            super().benchmark_case_finished(**event)

        def flush_viewer(self, *, timeout_s):
            del timeout_s
            self.order.append(("viewer_close", {}))
            raise RuntimeError("synthetic viewer close failure")

    monkeypatch.setattr(
        runner,
        "trace_recorder_from_environment",
        lambda *_args, directory, **_kwargs: OrderingRecorder(directory),
    )
    manifest = get_manifest("internal-core", "deterministic", 7)
    case = manifest.cases[0]

    suite = asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (case,),
            ),
            trace_dir=tmp_path,
        )
    )

    assert suite.cases[0].status == "done"
    assert len(recorders) == 1
    assert [kind for kind, _ in recorders[0].order] == ["terminal", "viewer_close"]
    terminal = recorders[0].order[0][1]
    assert terminal == {
        "case_id": case.case_id,
        "status": "done",
        "projection_disposition": "projected",
        "report_disposition": "committed",
        "export_disposition": "exported",
        "final_commit_disposition": "committed",
    }
    assert sum(event["event"] == "benchmark_case_finished" for event in recorders[0].events) == 1


@pytest.mark.parametrize(
    ("fault_owner", "report_disposition", "export_disposition", "failure_code"),
    (
        ("commit", "failed", "not_attempted", "suite_report_commit_failed"),
        ("export", "committed", "failed", "suite_report_export_failed"),
    ),
)
def test_suite_report_faults_are_typed_and_do_not_replace_case_finalization(
    monkeypatch,
    tmp_path,
    fault_owner,
    report_disposition,
    export_disposition,
    failure_code,
) -> None:
    def fail(*_args, **_kwargs):
        raise RunResultStoreError(f"synthetic suite {fault_owner} failure")

    monkeypatch.setattr(
        SQLiteRunResultStore,
        "commit_run_report" if fault_owner == "commit" else "export_run_report",
        fail,
    )
    manifest = get_manifest("internal-core", "deterministic", 7)
    case = manifest.cases[0]
    suite = asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (case,),
            ),
            trace_dir=tmp_path,
        )
    )

    assert suite.cases[0].status == "done"
    store = SQLiteRunResultStore(tmp_path / "run-results.sqlite3")
    case_record = store.load_case_outcome(case.case_id)
    disposition = store.load_suite_report_disposition(suite.identity.run_id)
    assert case_record is not None and case_record.revision is CaseRecordRevision.FINAL
    assert disposition is not None
    assert disposition.report_disposition.value == report_disposition
    assert disposition.export_disposition.value == export_disposition
    assert disposition.failure_code == failure_code


def test_hung_suite_report_commit_is_bounded_and_preserves_final_case(monkeypatch, tmp_path) -> None:
    from affordance_runtime.benchmarks.target_loop import runner

    monkeypatch.setattr(runner, "_REPORT_TIMEOUT_S", 0.02)

    def hang(*_args, **_kwargs):
        time.sleep(0.2)

    monkeypatch.setattr(SQLiteRunResultStore, "commit_run_report", hang)
    manifest = get_manifest("internal-core", "deterministic", 7)
    case = manifest.cases[0]
    started = time.perf_counter()
    suite = asyncio.run(
        run_suite(
            BenchmarkManifest(
                manifest.schema_version,
                manifest.suite_id,
                manifest.profile_id,
                manifest.seed,
                (case,),
            ),
            trace_dir=tmp_path,
        )
    )

    assert time.perf_counter() - started < 0.15
    store = SQLiteRunResultStore(tmp_path / "run-results.sqlite3")
    case_record = store.load_case_outcome(case.case_id)
    disposition = store.load_suite_report_disposition(suite.identity.run_id)
    assert case_record is not None and case_record.revision is CaseRecordRevision.FINAL
    assert disposition is not None
    assert disposition.report_disposition.value == "failed"
    assert disposition.failure_code == "suite_report_commit_failed"

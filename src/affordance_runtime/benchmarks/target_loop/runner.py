"""Sequential isolated benchmark execution through the production TargetRuntime."""

from __future__ import annotations

import asyncio
import inspect
import os
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from affordance_runtime.agent.core_loop import CoreLoopStartError
from affordance_runtime.agent.episode_snapshot import snapshot_episode
from affordance_runtime.agent.monitor import EpisodeMonitor
from affordance_runtime.agent.observability import (
    RunTraceRecorder,
    trace_recorder_from_environment,
)
from affordance_runtime.agent.run_state import RunState, RunStatus
from affordance_runtime.app.composition import compose_target_runtime
from affordance_runtime.benchmarks.target_loop.acceptance import accept_case, accept_suite, safe_rate
from affordance_runtime.benchmarks.target_loop.analysis import (
    export_case_analysis,
    project_case_analysis,
)
from affordance_runtime.benchmarks.target_loop.case_projection import project_case_result
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    BenchmarkManifest,
    BenchmarkRunIdentity,
    BenchmarkSuiteResult,
    CaseFailureOrigin,
    FailureFacts,
    MetricMeasurement,
)
from affordance_runtime.benchmarks.target_loop.instrumentation import (
    BenchmarkInstrumentation,
    CountingActionOutcomeProjector,
    CountingEnvironment,
    instrument_policy,
    instrument_task_evaluator,
)
from affordance_runtime.benchmarks.target_loop.manifest import manifest_digest
from affordance_runtime.benchmarks.target_loop.metric_registry import CANONICAL_METRICS
from affordance_runtime.benchmarks.target_loop.outcome_checkpoint import (
    OfficialOutcomeCheckpointRecorder,
    OfficialOutcomePersistenceError,
)
from affordance_runtime.benchmarks.target_loop.presentation_sidecar import (
    PresentationReportingStatus,
    project_case_presentation,
    report_case_presentation,
)
from affordance_runtime.benchmarks.target_loop.result_store import (
    CaseLifecyclePhase,
    CaseOutcomeRecord,
    CaseRecordRevision,
    CleanupDisposition,
    ExportDisposition,
    FinalCommitDisposition,
    ProjectionDisposition,
    ReportDisposition,
    RunResultStoreError,
    SQLiteRunResultStore,
    SuiteReportDisposition,
)

_CLEANUP_TIMEOUT_S = 10.0
_REPORT_TIMEOUT_S = 5.0
_VIEWER_FLUSH_TIMEOUT_S = 5.0
_WATCHDOG_CANCEL_GRACE_S = 2.0
_CASE_RETURN_TIMEOUT_S = 2.0
_DETACHED_WATCHDOG_TASKS: set[asyncio.Task] = set()


class _CaseLifecycle:
    def __init__(self, case_id, store, instrumentation) -> None:
        self.case_id = case_id
        self.store = store
        self.instrumentation = instrumentation
        self.persistence_error = ""

    def transition(self, phase: CaseLifecyclePhase) -> None:
        self.instrumentation.case_lifecycle_phase(phase.value)
        if self.store is None:
            return
        try:
            self.store.record_case_phase(self.case_id, phase)
        except RunResultStoreError as exc:
            self.persistence_error = type(exc).__name__


async def run_suite(
    manifest: BenchmarkManifest,
    case_completed: Callable[[int, BenchmarkCaseResult], None] | None = None,
    trace_dir: Path | None = None,
    interruption_requested: asyncio.Event | None = None,
    status_changed: Callable[[str], None] | None = None,
) -> BenchmarkSuiteResult:
    digest = manifest_digest(manifest)
    identity = BenchmarkRunIdentity.create(
        manifest.suite_id,
        digest,
        manifest.profile_id,
        manifest.seed,
    )
    store = None
    store_initialization_error = ""
    if trace_dir is not None:
        try:
            store = SQLiteRunResultStore(trace_dir / "run-results.sqlite3")
        except RunResultStoreError as exc:
            store_initialization_error = type(exc).__name__
    if store is not None:
        try:
            await _bounded_report_store_call(
                lambda: store.record_suite_report_disposition(
                    SuiteReportDisposition(
                        identity.run_id,
                        len(manifest.cases),
                        ReportDisposition.NOT_ATTEMPTED,
                        ExportDisposition.NOT_ATTEMPTED,
                    )
                ),
                "suite-start",
            )
        except Exception:
            # Case BODY/CLEANUP/FINAL remains independently durable.
            pass
    completed = []
    for index, case in enumerate(manifest.cases, 1):
        if interruption_requested is not None and interruption_requested.is_set():
            break
        result = await _run_case(
            case,
            trace_dir=trace_dir,
            interruption_requested=interruption_requested,
            status_changed=status_changed,
            result_store=store,
            store_initialization_error=store_initialization_error,
            session_id=identity.run_attempt_id,
            run_identity=identity,
        )
        completed.append(result)
        if case_completed is not None:
            case_completed(index, result)
        if result.failure_code == "interrupted_external":
            break
    results = tuple(completed)
    decisions = tuple(
        accept_case(
            result,
            case.expected_terminal_statuses,
            case.required_measurements,
            case.metric_expectations,
        )
        for case, result in zip(manifest.cases, results)
    )
    accepted = accept_suite(
        results,
        decisions,
        expected_case_count=len(manifest.cases),
    )
    sent_unknown = sum(_measured_int(item, "sent_unknown_count") for item in results)
    stale = sum(_measured_int(item, "stale_opportunities") for item in results)
    rates = {
        "unknown_duplicate_rate": safe_rate(
            MetricMeasurement(
                sum(_measured_int(item, "duplicate_unknown_attempts") for item in results),
                True,
                sent_unknown,
            )
        ),
        "stale_zero_call_rate": safe_rate(
            MetricMeasurement(
                stale - sum(_measured_int(item, "stale_zero_call_violations") for item in results),
                True,
                stale,
            )
        ),
    }
    suite_result = BenchmarkSuiteResult(identity, results, accepted, rates)
    if store is not None and trace_dir is not None:
        suite_report_disposition = ReportDisposition.NOT_ATTEMPTED
        suite_export_disposition = ExportDisposition.NOT_ATTEMPTED
        suite_failure_code = ""
        try:
            await _bounded_report_store_call(
                lambda: store.commit_run_report(suite_result),
                "suite-report-commit",
            )
        except Exception:
            suite_report_disposition = ReportDisposition.FAILED
            suite_failure_code = "suite_report_commit_failed"
        else:
            suite_report_disposition = ReportDisposition.COMMITTED
            try:
                await _bounded_report_store_call(
                    lambda: store.export_run_report(identity.run_id, trace_dir),
                    "suite-report-export",
                )
            except Exception:
                suite_export_disposition = ExportDisposition.FAILED
                suite_failure_code = "suite_report_export_failed"
            else:
                suite_export_disposition = ExportDisposition.EXPORTED
        try:
            await _bounded_report_store_call(
                lambda: store.record_suite_report_disposition(
                    SuiteReportDisposition(
                        identity.run_id,
                        len(manifest.cases),
                        suite_report_disposition,
                        suite_export_disposition,
                        suite_failure_code,
                    )
                ),
                "suite-report-disposition",
            )
        except Exception:
            # The committed case prefix and run report (when present) remain authoritative.
            pass
    return suite_result


async def _run_case(
    case,
    *,
    trace_dir: Path | None = None,
    interruption_requested: asyncio.Event | None = None,
    status_changed: Callable[[str], None] | None = None,
    result_store: SQLiteRunResultStore | None = None,
    store_initialization_error: str = "",
    session_id: str = "",
    run_identity: BenchmarkRunIdentity | None = None,
) -> BenchmarkCaseResult:
    trace_recorder = (
        trace_recorder_from_environment(
            os.environ,
            directory=trace_dir / "traces" / case.case_id,
            run_id=f"case:{session_id}:{case.case_id}",
            session_id=session_id,
            benchmark_managed=True,
            analysis_identity={
                "run_id": run_identity.run_id if run_identity is not None else "",
                "run_attempt_id": (
                    run_identity.run_attempt_id if run_identity is not None else session_id
                ),
                "suite_id": run_identity.suite_id if run_identity is not None else case.suite_id,
                "profile_id": run_identity.profile_id if run_identity is not None else "",
                "case_id": case.case_id,
                "seed": run_identity.seed if run_identity is not None else case.seed,
                "git_sha": run_identity.git_sha if run_identity is not None else "",
                "manifest_digest": run_identity.manifest_digest if run_identity is not None else "",
                "environment": os.environ.get("LLM_ACTIVE_PROFILE", "local"),
                "release": run_identity.harness_schema_version if run_identity is not None else "",
            },
        )
        if trace_dir is not None
        else RunTraceRecorder()
    )
    if not isinstance(trace_recorder, RunTraceRecorder):
        raise TypeError("benchmark trace directory must produce a local recorder")
    instrumentation = BenchmarkInstrumentation(trace_recorder=trace_recorder)
    lifecycle = _CaseLifecycle(case.case_id, result_store, instrumentation)
    instrumentation.benchmark_case_started(
        case_id=case.case_id,
        description=case.description,
        timeout_s=case.timeout_s,
    )
    lifecycle.transition(CaseLifecyclePhase.CASE_STARTED)
    outcome_recorder = OfficialOutcomeCheckpointRecorder(
        case.case_id,
        result_store,
        instrumentation.trace_recorder,
        status_changed,
    )
    outcome_recorder.persistence_error = store_initialization_error
    environment = None
    cleanup_owned = False
    runtime = None
    result = None
    partial = None
    snapshot = None
    state_holder: dict[str, RunState] = {}
    failure = ""
    lifecycle_persistence_error = ""
    body_record = None
    cleanup_record = None
    started = time.perf_counter()
    _set_status(status_changed, "running")
    try:
        try:
            environment = case.environment_factory(instrumentation)
            cleanup_owned = True
            lifecycle.transition(CaseLifecyclePhase.ENVIRONMENT_READY)
        except Exception as exc:
            instrumentation.record_failure(
                CaseFailureOrigin.ENVIRONMENT_FACTORY,
                "environment_factory_exception",
                exc,
            )
            cleanup_diagnostic = getattr(
                exc,
                "__affordance_cleanup_diagnostic__",
                None,
            )
            if cleanup_diagnostic is not None:
                instrumentation.record_cleanup_diagnostic(
                    "cleanup_exception",
                    cleanup_diagnostic,
                )
            raise _CaseStageError("environment factory", exc) from exc
        try:
            task = case.task_factory()
        except Exception as exc:
            instrumentation.record_failure(CaseFailureOrigin.TASK_FACTORY, "task_factory_exception", exc)
            raise _CaseStageError("task factory", exc) from exc
        try:
            composition = case.composition_factory(instrumentation)
        except Exception as exc:
            instrumentation.record_failure(
                CaseFailureOrigin.COMPOSITION_FACTORY,
                "composition_factory_exception",
                exc,
            )
            raise _CaseStageError("composition factory", exc) from exc
        counted_environment = CountingEnvironment(
            environment,
            instrumentation,
            frozenset(task.forbidden_effects),
        )
        try:
            runtime = _build_runtime(composition, instrumentation, outcome_recorder)
        except Exception as exc:
            instrumentation.record_failure(
                CaseFailureOrigin.LOOP_CONSTRUCTION,
                "loop_construction_exception",
                exc,
            )
            raise _CaseStageError("CoreAgentLoop construction", exc) from exc
        run = _run_episode(case, runtime, counted_environment, task, instrumentation, state_holder)
        result = await _run_with_watchdog(
            run,
            case.timeout_s,
            interruption_requested=interruption_requested,
            runtime_finished=instrumentation.runtime_finished_event,
        )
    except ExternalInterruption as exc:
        failure = "external interruption"
        instrumentation.record_failure(
            CaseFailureOrigin.HARNESS_EXTERNAL_INTERRUPTION,
            "interrupted_external",
            exc,
        )
        state = state_holder.get("state")
        if state is not None:
            partial = snapshot_episode(
                state,
                episode_monitor=runtime.episode_monitor if runtime is not None else None,
            )
    except _HarnessWatchdogTimeout as exc:
        failure = "case timeout"
        instrumentation.record_watchdog("case_timeout", exc)
        state = state_holder.get("state")
        if state is not None:
            partial = snapshot_episode(
                state,
                episode_monitor=runtime.episode_monitor if runtime is not None else None,
            )
    except _CaseReturnTimeout as exc:
        failure = "case return timeout"
        instrumentation.record_watchdog("case_return_timeout", exc)
        result = state_holder.get("state")
        if result is not None:
            partial = snapshot_episode(
                result,
                episode_monitor=runtime.episode_monitor if runtime is not None else None,
            )
    except _CaseStageError as exc:
        failure = f"{exc.stage} failed: {type(exc.cause).__name__}"
    except Exception as exc:
        failure = f"case exception: {type(exc).__name__}"
        instrumentation.record_failure(
            CaseFailureOrigin.UNKNOWN,
            "runtime_exception",
            exc,
        )
        result = state_holder.get("state")
    finally:
        state = state_holder.get("state")
        if state is not None:
            snapshot = snapshot_episode(
                state,
                episode_monitor=runtime.episode_monitor if runtime is not None else None,
            )
        lifecycle.transition(CaseLifecyclePhase.CASE_BODY_RETURNED)
        checkpoint_id, checkpoint_digest = _checkpoint_join(
            outcome_recorder.durable_checkpoint
        )
        body_record = CaseOutcomeRecord(
            case.case_id,
            CaseRecordRevision.BODY,
            str(getattr(result, "status", RunStatus.FAILED)),
            instrumentation.failure_code,
            checkpoint_id,
            checkpoint_digest,
        )
        if result_store is not None:
            try:
                result_store.commit_case_outcome(body_record)
            except RunResultStoreError as exc:
                lifecycle_persistence_error = type(exc).__name__
            else:
                lifecycle.transition(CaseLifecyclePhase.RESULT_PERSISTED)
        if outcome_recorder.checkpoint is None:
            _set_status(status_changed, "finalizing")
            instrumentation.benchmark_lifecycle_phase(
                "finalizing",
                primary_result_available=result is not None,
                primary_snapshot_available=snapshot is not None or partial is not None,
            )
        durable_checkpoint = outcome_recorder.durable_checkpoint
        if durable_checkpoint is not None:
            instrumentation.primary_result_available(
                case_id=case.case_id,
                checkpoint_id=durable_checkpoint.checkpoint_id,
                status=durable_checkpoint.run_status.value,
                step_count=int(getattr(state, "step_count", 0)),
            )
        lifecycle.transition(CaseLifecyclePhase.CLEANUP_STARTED)
        if cleanup_owned:
            _set_status(status_changed, "cleanup")
            instrumentation.cleanup_status = "running"
            instrumentation.benchmark_lifecycle_phase(
                "cleanup",
                primary_result_available=result is not None,
                primary_snapshot_available=snapshot is not None or partial is not None,
            )
            cleanup_started = time.perf_counter()
            try:
                await asyncio.wait_for(_close(environment), timeout=_CLEANUP_TIMEOUT_S)
            except TimeoutError:
                exc = CleanupTimeoutError(f"cleanup exceeded {_CLEANUP_TIMEOUT_S * 1000:.0f} ms deadline")
                instrumentation.record_cleanup_failure(
                    "cleanup_timeout",
                    exc,
                    started_at=cleanup_started,
                )
                instrumentation.cleanup_status = "timeout"
                failure = _append_failure(failure, "cleanup timed out")
            except Exception as exc:
                if _is_target_closed_error(exc):
                    instrumentation.cleanup_status = "already_closed"
                else:
                    instrumentation.record_cleanup_failure(
                        "cleanup_exception",
                        exc,
                        started_at=cleanup_started,
                    )
                    instrumentation.cleanup_status = "failed"
                    failure = _append_failure(failure, "cleanup failed")
            else:
                instrumentation.cleanup_status = "succeeded"
        lifecycle.transition(CaseLifecyclePhase.CLEANUP_FINISHED)
        cleanup_record = replace(
            body_record,
            revision=CaseRecordRevision.CLEANUP,
            cleanup_disposition=_cleanup_disposition(
                instrumentation.cleanup_status,
                acquired=cleanup_owned,
            ),
        )
        if result_store is not None:
            try:
                result_store.commit_case_outcome(cleanup_record)
                result_store.record_cleanup(
                    case.case_id,
                    instrumentation.cleanup_status,
                    instrumentation.cleanup_failure_code,
                    instrumentation.cleanup_exception_class,
                )
            except RunResultStoreError as exc:
                lifecycle_persistence_error = type(exc).__name__
        _set_status(status_changed, "reporting")
        instrumentation.benchmark_lifecycle_phase(
            "reporting",
            primary_result_available=result is not None,
            primary_snapshot_available=snapshot is not None or partial is not None,
        )
    lifecycle.transition(CaseLifecyclePhase.FINAL_ATTEMPT)
    # Snapshot local trace integrity before projection. Remote viewer shutdown
    # happens only after the terminal local case event below.
    instrumentation.set_custom_metric("trace_recording_failures", len(instrumentation.trace_recorder.errors))
    instrumentation.set_custom_metric(
        "viewer_dropped_event_count",
        int(getattr(instrumentation.trace_recorder, "viewer_dropped_event_count", 0)),
    )
    instrumentation.set_custom_metric(
        "viewer_disabled",
        int(bool(getattr(instrumentation.trace_recorder, "viewer_disabled", False))),
    )
    persistence_failure_code = (
        "official_checkpoint_persistence_failed"
        if outcome_recorder.persistence_error
        else "lifecycle_persistence_failed"
        if lifecycle_persistence_error or lifecycle.persistence_error
        else ""
    )
    if persistence_failure_code:
        instrumentation.record_failure(
            CaseFailureOrigin.HARNESS_PERSISTENCE,
            persistence_failure_code,
            OfficialOutcomePersistenceError(
                outcome_recorder.persistence_error or lifecycle_persistence_error or lifecycle.persistence_error
            ),
        )
        failure = _append_failure(failure, persistence_failure_code.replace("_", " "))
    elapsed = (time.perf_counter() - started) * 1000
    projection_disposition = ProjectionDisposition.PROJECTED
    try:
        case_result = project_case_result(
            case.case_id,
            result,
            instrumentation,
            elapsed,
            failure,
            timeout_snapshot=partial,
            final_snapshot=snapshot,
            official_checkpoint=outcome_recorder.durable_checkpoint,
        )
    except Exception as exc:
        projection_disposition = ProjectionDisposition.FAILED
        instrumentation.record_failure(
            CaseFailureOrigin.HARNESS_PROJECTION,
            "case_projection_failed",
            exc,
        )
        failure = _append_failure(failure, "case projection failed")
        case_result = BenchmarkCaseResult(
            case.case_id,
            RunStatus.FAILED.value,
            False,
            failure,
            elapsed,
            measurements={name: MetricMeasurement(0, True) for name in CANONICAL_METRICS},
            cleanup_status=instrumentation.cleanup_status,
            failure_facts=FailureFacts(
                component_origin=CaseFailureOrigin.HARNESS_PROJECTION,
                component_code="case_projection_failed",
                component_exception_class=type(exc).__name__,
                cleanup_code=instrumentation.cleanup_failure_code,
                cleanup_exception_class=instrumentation.cleanup_exception_class,
            ),
        )
    if run_identity is not None:
        case_result = replace(
            case_result,
            suite_id=run_identity.suite_id,
            profile_id=run_identity.profile_id,
            seed=run_identity.seed,
            manifest_digest=run_identity.manifest_digest,
            harness_schema_version=run_identity.harness_schema_version,
            run_id=run_identity.run_id,
            run_attempt_id=run_identity.run_attempt_id,
        )
    report_disposition = ReportDisposition.NOT_ATTEMPTED
    export_disposition = ExportDisposition.NOT_ATTEMPTED
    if result_store is not None:
        report_failure_code = ""
        try:
            await asyncio.wait_for(
                _call_sync_owner(lambda: result_store.commit_case_report(case_result), "report-commit"),
                timeout=_REPORT_TIMEOUT_S,
            )
        except Exception as exc:
            report_failure_code = "report_payload_commit_failed"
            report_exception = exc
            report_disposition = ReportDisposition.FAILED
        else:
            report_disposition = ReportDisposition.COMMITTED
            try:
                await asyncio.wait_for(
                    _call_sync_owner(lambda: result_store.export_case_report(case.case_id, trace_dir), "report-export"),
                    timeout=_REPORT_TIMEOUT_S,
                )
            except Exception as exc:
                report_failure_code = "json_export_failed"
                report_exception = exc
                export_disposition = ExportDisposition.FAILED
            else:
                export_disposition = ExportDisposition.EXPORTED
        if report_failure_code:
            try:
                result_store.record_report_status(
                    case.case_id,
                    "failed",
                    report_failure_code,
                )
            except RunResultStoreError:
                pass
            instrumentation.record_failure(
                CaseFailureOrigin.HARNESS_PERSISTENCE,
                report_failure_code,
                report_exception,
            )
            failure = _append_failure(failure, report_failure_code.replace("_", " "))
            case_result = project_case_result(
                case.case_id,
                result,
                instrumentation,
                elapsed,
                failure,
                timeout_snapshot=partial,
                final_snapshot=snapshot,
                official_checkpoint=outcome_recorder.durable_checkpoint,
            )
            if run_identity is not None:
                case_result = replace(
                    case_result,
                    suite_id=run_identity.suite_id,
                    profile_id=run_identity.profile_id,
                    seed=run_identity.seed,
                    manifest_digest=run_identity.manifest_digest,
                    harness_schema_version=run_identity.harness_schema_version,
                    run_id=run_identity.run_id,
                    run_attempt_id=run_identity.run_attempt_id,
                )
            if report_failure_code == "json_export_failed":
                try:
                    await asyncio.wait_for(
                        _call_sync_owner(
                            lambda: result_store.commit_case_report(case_result),
                            "report-failure-commit",
                        ),
                        timeout=_REPORT_TIMEOUT_S,
                    )
                except Exception:
                    # The earlier committed payload remains regenerable; this
                    # projection-update failure cannot erase it.
                    pass
        presentation = project_case_presentation(
            case.case_id,
            result if isinstance(result, RunState) else None,
        )
        presentation_reporting = report_case_presentation(
            result_store,
            presentation,
            trace_dir,
        )
        if presentation_reporting.status is PresentationReportingStatus.FAILED:
            # Presentation reporting is additive evidence. It cannot alter the
            # native evaluator result or reclassify a GUI case outcome.
            instrumentation.set_custom_metric("presentation_sidecar_reporting_failures", 1)
    final_commit_disposition = FinalCommitDisposition.NOT_ATTEMPTED
    if result_store is not None and cleanup_record is not None:
        final_record = replace(
            cleanup_record,
            revision=CaseRecordRevision.FINAL,
            projection_disposition=projection_disposition,
            report_disposition=report_disposition,
            export_disposition=export_disposition,
            finished=True,
        )
        try:
            result_store.commit_case_outcome(final_record)
        except Exception as exc:
            final_commit_disposition = FinalCommitDisposition.FAILED
            instrumentation.record_failure(
                CaseFailureOrigin.HARNESS_PERSISTENCE,
                "final_case_commit_failed",
                exc,
            )
        else:
            final_commit_disposition = FinalCommitDisposition.COMMITTED
    case_analysis = project_case_analysis(case_result)
    if trace_dir is not None:
        try:
            export_case_analysis(case_analysis, trace_dir)
        except Exception:
            # Analysis is fail-open; result JSON/SQLite and trace remain authoritative.
            pass
    instrumentation.benchmark_case_finished(
        case_id=case.case_id,
        status=body_record.behavior_status,
        projection_disposition=projection_disposition.value,
        report_disposition=report_disposition.value,
        export_disposition=export_disposition.value,
        final_commit_disposition=final_commit_disposition.value,
        analysis=case_analysis,
    )
    flush = getattr(trace_recorder, "flush_viewer", None)
    if flush is not None:
        try:
            await asyncio.wait_for(
                _call_sync_owner(
                    lambda: flush(timeout_s=max(0.005, _VIEWER_FLUSH_TIMEOUT_S * 0.3)),
                    "viewer-flush",
                ),
                timeout=_VIEWER_FLUSH_TIMEOUT_S,
            )
        except Exception:
            # Viewer failure is already fail-open and never changes case truth.
            pass
    return case_result


def _build_runtime(composition, instrumentation, outcome_recorder):
    return compose_target_runtime(
        instrument_policy(composition.policy, instrumentation),
        CountingActionOutcomeProjector(composition.action_outcome_projector, instrumentation),
        instrument_task_evaluator(
            composition.task_evaluator,
            instrumentation,
        ),
        risk_policy=composition.risk_policy,
        required_decisions=composition.required_decisions,
        trace_sink=instrumentation,
        goal_compiler=composition.goal_compiler,
        episode_monitor=EpisodeMonitor(),
        official_outcome_sink=outcome_recorder,
    )


async def _run_episode(case, runtime, environment, task, instrumentation, state_holder):
    try:
        state = await runtime.initialize_task(environment, task)
    except CoreLoopStartError as exc:
        instrumentation.record_failure(CaseFailureOrigin.ENVIRONMENT_RESET, exc.reason_code, exc)
        raise
    except Exception as exc:
        instrumentation.record_failure(CaseFailureOrigin.SESSION_START, "session_start_exception", exc)
        raise
    state_holder["state"] = state
    result = await runtime.continue_task(environment, task, state)
    if case.auto_confirm and result.status is RunStatus.WAITING_CONFIRMATION:
        instrumentation.confirmations_submitted += 1
        result = await runtime.resume_confirmation(
            environment,
            task,
            result,
            approved=True,
        )
    finalization = result.finalization
    instrumentation.set_custom_metric(
        "stop_send_count",
        finalization.stop_send_count if finalization is not None else 0,
    )
    instrumentation.set_custom_metric(
        "post_stop_capture_count",
        finalization.post_stop_capture_count if finalization is not None else 0,
    )
    instrumentation.set_custom_metric(
        "native_evaluator_count",
        finalization.native_evaluator_count if finalization is not None else 0,
    )
    instrumentation.set_custom_metric(
        "action_policy_ordinary_calls",
        instrumentation.action_policy_ordinary_calls,
    )
    instrumentation.set_custom_metric(
        "action_policy_recovery_calls",
        instrumentation.action_policy_recovery_calls,
    )
    instrumentation.set_custom_metric(
        "representation_repair_calls",
        instrumentation.representation_repair_calls,
    )
    return result


async def _close(environment) -> None:
    for name in ("close", "shutdown"):
        method = getattr(environment, name, None)
        if method is None:
            continue
        outcome = method() if inspect.iscoroutinefunction(method) else await _call_sync_owner(method, "cleanup")
        if inspect.isawaitable(outcome):
            await outcome
        return


def _is_target_closed_error(exception: BaseException) -> bool:
    """Classify idempotent cleanup only; callers outside cleanup must not use this."""

    try:
        from playwright.async_api import TargetClosedError
    except ImportError:
        return type(exception).__name__ == "TargetClosedError"
    return isinstance(exception, TargetClosedError)


async def _call_sync_owner(method, owner: str):
    """Run one bounded synchronous owner call in a disposable daemon thread."""

    loop = asyncio.get_running_loop()
    completed = loop.create_future()

    def invoke() -> None:
        try:
            outcome = method()
        except BaseException as exc:
            callback = completed.set_exception
            value = exc
        else:
            callback = completed.set_result
            value = outcome
        try:
            loop.call_soon_threadsafe(_settle_cleanup_future, completed, callback, value)
        except RuntimeError:
            return

    threading.Thread(
        target=invoke,
        name=f"affordance-benchmark-{owner}",
        daemon=True,
    ).start()
    return await completed


async def _bounded_report_store_call(method, owner: str):
    return await asyncio.wait_for(
        _call_sync_owner(method, owner),
        timeout=_REPORT_TIMEOUT_S,
    )


def _settle_cleanup_future(future, callback, value) -> None:
    if not future.done():
        callback(value)


async def _run_with_watchdog(
    awaitable,
    timeout_s: float,
    *,
    interruption_requested: asyncio.Event | None = None,
    runtime_finished: asyncio.Event | None = None,
):
    """Own the deadline explicitly so component TimeoutError remains component truth."""
    task = asyncio.create_task(awaitable)
    interruption = asyncio.create_task(interruption_requested.wait()) if interruption_requested is not None else None
    finished = asyncio.create_task(runtime_finished.wait()) if runtime_finished is not None else None
    try:
        pending = {item for item in (task, interruption, finished) if item is not None}
        done, _ = await asyncio.wait(
            pending,
            timeout=timeout_s,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if task in done:
            return task.result()
        if finished is not None and finished in done:
            returned, _ = await asyncio.wait({task}, timeout=_CASE_RETURN_TIMEOUT_S)
            if task in returned:
                return task.result()
            task.cancel()
            await _await_cancel_grace(task)
            raise _CaseReturnTimeout(task_detached=not task.done())
        task.cancel()
        await _await_cancel_grace(task)
        if interruption is not None and interruption in done:
            raise ExternalInterruption
        raise _HarnessWatchdogTimeout(task_detached=not task.done())
    except asyncio.CancelledError:
        task.cancel()
        await _await_cancel_grace(task)
        raise
    finally:
        auxiliaries = tuple(item for item in (interruption, finished) if item is not None)
        for item in auxiliaries:
            item.cancel()
        if auxiliaries:
            await asyncio.gather(*auxiliaries, return_exceptions=True)


async def _await_cancel_grace(task: asyncio.Task) -> None:
    done, _ = await asyncio.wait({task}, timeout=_WATCHDOG_CANCEL_GRACE_S)
    if task in done:
        if not task.cancelled():
            task.exception()
        return

    def consume_result(completed: asyncio.Task) -> None:
        _DETACHED_WATCHDOG_TASKS.discard(completed)
        if not completed.cancelled():
            completed.exception()

    _DETACHED_WATCHDOG_TASKS.add(task)
    task.add_done_callback(consume_result)


def abandon_detached_watchdog_tasks(loop: asyncio.AbstractEventLoop) -> int:
    """Let the foreground harness close after its bounded cancel grace expired."""

    detached = tuple(task for task in _DETACHED_WATCHDOG_TASKS if task.get_loop() is loop and not task.done())
    for task in detached:
        # The task already received cancellation and a bounded grace period. Suppress
        # only asyncio's destruction warning while the foreground process exits.
        task._log_destroy_pending = False  # type: ignore[attr-defined]
        _DETACHED_WATCHDOG_TASKS.discard(task)
    return len(detached)


class _CaseStageError(RuntimeError):
    def __init__(self, stage: str, cause: Exception) -> None:
        self.stage = stage
        self.cause = cause
        super().__init__(stage)


class _HarnessWatchdogTimeout(RuntimeError):
    """Private sentinel raised only by the harness-owned deadline."""

    def __init__(self, *, task_detached: bool = False) -> None:
        self.task_detached = task_detached


class _CaseReturnTimeout(RuntimeError):
    """Runtime emitted its terminal fact but did not return control to the harness."""

    def __init__(self, *, task_detached: bool = False) -> None:
        self.task_detached = task_detached
        super().__init__("case watchdog deadline exceeded")


class ExternalInterruption(RuntimeError):
    """Typed sentinel for a process signal relayed by the benchmark CLI."""


class CleanupTimeoutError(TimeoutError):
    """Typed harness diagnostic for the independent cleanup deadline."""


def _append_failure(current: str, addition: str) -> str:
    return f"{current}; {addition}" if current else addition


def _checkpoint_join(checkpoint) -> tuple[str, str]:
    if checkpoint is None:
        return "", ""
    checkpoint_id = checkpoint.checkpoint_id
    prefix = "checkpoint:"
    if not checkpoint_id.startswith(prefix):
        raise ValueError("official checkpoint identity is malformed")
    return checkpoint_id, checkpoint_id.removeprefix(prefix)


def _cleanup_disposition(status: str, *, acquired: bool) -> CleanupDisposition:
    if not acquired:
        return CleanupDisposition.NOT_ACQUIRED
    return {
        "not_run": CleanupDisposition.NOT_APPLICABLE,
        "running": CleanupDisposition.NOT_APPLICABLE,
        "succeeded": CleanupDisposition.SUCCEEDED,
        "already_closed": CleanupDisposition.ALREADY_CLOSED,
        "timeout": CleanupDisposition.TIMEOUT,
        "failed": CleanupDisposition.FAILED,
    }[status]


def _set_status(callback: Callable[[str], None] | None, phase: str) -> None:
    if callback is not None:
        callback(phase)


def _measured_int(result: BenchmarkCaseResult, name: str) -> int:
    measurement = result.measurements[name]
    if not measurement.measured or not isinstance(measurement.value, int):
        raise ValueError(f"benchmark metric {name} is not a measured integer")
    return measurement.value

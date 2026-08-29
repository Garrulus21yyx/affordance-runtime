import asyncio
import json
import multiprocessing
import queue
import threading
import time
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from affordance_runtime.agent import RunStatus
from affordance_runtime.agent.observability import (
    LangfuseOtelSink,
    LangfuseViewerProcess,
    QueuedViewerRunTraceRecorder,
    RunTraceRecorder,
    _langfuse_event_projection,
    _langfuse_generation_name,
    _langfuse_ipc_projection,
    _public_task_projection,
    trace_recorder_from_environment,
)
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.execution.contracts import ActionResult, DispatchStatus
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.model.policy.contracts import ModelGenerationAttempt
from tests.integration.agent.test_core_loop import (
    CoreActionOutcomeProjector,
    CoreTaskEvaluator,
    _runtime,
    _task,
    _world,
)


def test_langfuse_names_history_compaction_attempt_as_its_own_role() -> None:
    assert (
        _langfuse_generation_name(
            {},
            {"role": "history_compactor"},
        )
        == "history-compaction-generation"
    )
    assert _langfuse_generation_name({}, {"role": "action_policy"}) == "action-policy-generation"


def test_run_finished_is_local_only_and_never_offers_to_queued_viewer(tmp_path) -> None:
    class BlockingViewer:
        calls = 0

        def enqueue(self, _event):
            self.calls += 1
            raise AssertionError("terminal handoff must not enter viewer IPC")

    viewer = BlockingViewer()
    recorder = QueuedViewerRunTraceRecorder(tmp_path, viewer_process=viewer)  # type: ignore[arg-type]

    recorder.run_finished(SimpleNamespace(status=RunStatus.FAILED, step_count=3))

    assert viewer.calls == 0
    assert recorder.events[-1]["event"] == "run_finished"
    assert json.loads(recorder.path.read_text().splitlines()[-1])["event"] == "run_finished"


def test_analysis_identity_is_immutable_trace_join_metadata(tmp_path) -> None:
    identity = {
        "run_id": "suite:profile:configuration",
        "run_attempt_id": "attempt:" + "a" * 32,
        "case_id": "case-1",
    }
    recorder = RunTraceRecorder(tmp_path, analysis_identity=identity)
    identity["case_id"] = "mutated"

    recorder.case_lifecycle_phase("CASE_STARTED")

    persisted = json.loads(recorder.path.read_text().splitlines()[0])
    assert persisted["analysis_identity"] == {
        "run_id": "suite:profile:configuration",
        "run_attempt_id": "attempt:" + "a" * 32,
        "case_id": "case-1",
    }


def test_core_loop_persists_complete_lineage_and_deduplicated_worlds(tmp_path) -> None:
    async def scenario() -> None:
        recorder = RunTraceRecorder(tmp_path)
        runtime = _runtime("first_action")
        object.__setattr__(runtime, "trace_sink", recorder)
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", True),),
            results=(
                ActionResult(
                    "*",
                    DispatchStatus.SENT,
                    "dom",
                    True,
                    adapter_evidence={
                        "browsergym_transition": {
                            "dispatch_started": 0.0,
                            "dispatch_returned": 1.0,
                            "navigation_started": 2.0,
                            "navigation_committed": 3.0,
                            "post_capture_started": 4.0,
                            "post_capture_completed": 5.0,
                            "before_url": "https://example.test/search",
                            "after_url": "https://example.test/result",
                            "before_document_epoch": 7,
                            "after_document_epoch": 8,
                            "stability_status": "stable_navigation",
                        }
                    },
                ),
            ),
        )

        await runtime.run_task(environment, _task())

        persisted = [json.loads(line) for line in recorder.path.read_text().splitlines()]
        assert [item["event"] for item in persisted] == [
            "run_started",
            "observation",
            "goal_compiler_completed",
            "model_turn",
            "native_evaluator_returned",
            "observation",
            "step_completed",
            "run_finished",
        ]
        model_turn = next(item for item in persisted if item["event"] == "model_turn")
        run_started = next(item for item in persisted if item["event"] == "run_started")
        assert run_started["goal_guidance"] == {
            "disposition": "not_required",
            "reason": "atomic_core_loop_test",
        }
        assert model_turn["selected_grounding"]["source"]["target_id"] == "shared-toggle"
        assert model_turn["agent_context"]["projection"] == "lineage_summary"
        assert model_turn["agent_context"]["observation_id"] == "before"
        assert "provider_attempts" not in model_turn
        assert "model_invocation" not in model_turn
        step = next(item for item in persisted if item["event"] == "step_completed")
        assert step["lineage"]["tool_call_id"] == "provider-call:test"
        assert step["lineage"]["request_id"].startswith("request:")
        assert step["lineage"]["before_observation_id"] == "before"
        assert step["lineage"]["after_observation_id"] == "after"
        assert "before_world" not in step["result"]
        assert "after_world" not in step["result"]
        assert "before_public_world" not in step["result"]
        assert "after_public_world" not in step["result"]
        assert "model_delivery" not in step["result"]
        assert "policy_observation" not in step["result"]
        assert "policy_target_refs" not in step["result"]
        assert step["result"]["execution_receipts"] is not None
        transition = step["result"]["execution_receipts"]["receipts"][0]["result"]["adapter_evidence"][
            "browsergym_transition"
        ]
        assert transition["navigation_committed"] < transition["post_capture_started"]
        assert transition["before_url"].endswith("/search")
        assert transition["after_url"].endswith("/result")
        assert transition["stability_status"] == "stable_navigation"
        assert step["result"]["action_outcome"] is not None
        assert "public_world_delta" not in step["result"]["action_outcome"]
        assert step["result"]["public_world_delta"] == {
            "before_observation_id": "before",
            "after_observation_id": "after",
            "before_world_digest": step["lineage"]["before_world_digest"],
            "after_world_digest": step["lineage"]["after_world_digest"],
            "changed": True,
            "semantic_changed": True,
            "changed_target_count": 1,
            "changed_fact_count": 1,
            "changed_region_keys": step["result"]["public_world_delta"]["changed_region_keys"],
            "changed_region_total_count": len(step["result"]["public_world_delta"]["changed_region_keys"]),
            "changed_regions_truncated": False,
        }
        assert step["result"]["task_evaluation"]["status"] == "complete"

    asyncio.run(scenario())


def test_cancelled_policy_turn_projects_already_captured_provider_attempts(tmp_path) -> None:
    from affordance_runtime.agent.context import ModelFailure, ModelFailureKind
    from affordance_runtime.model.policy import ModelInvocationResult

    class CancelledPolicy:
        last_invocation_result = ModelInvocationResult(
            failure=ModelFailure(ModelFailureKind.TIMEOUT, "cancelled", False),
            attempts=(
                ModelGenerationAttempt(
                    1,
                    "initial",
                    "grounded_tools.v2",
                    "failed",
                    exception_class="ModelAPIError",
                    transcript={"error.code": "unavailable"},
                ),
            ),
        )

        async def decide(self, _context):
            raise asyncio.CancelledError

    async def scenario() -> None:
        recorder = RunTraceRecorder(tmp_path)
        runtime = TargetRuntime(
            AgentDecisionPorts(CancelledPolicy()),
            CoreActionOutcomeProjector(),
            CoreTaskEvaluator(),
            goal_compiler=NotRequiredGoalCompiler("cancelled_trace_test"),
            trace_sink=recorder,
        )

        state = await runtime.run_task(
            ScriptedEnvironment(initial_observation=_world("before", False)),
            _task(),
        )

        events = [json.loads(line) for line in recorder.path.read_text().splitlines()]
        turn = next(item for item in events if item["event"] == "model_turn")
        assert turn["exception"] == "CancelledError"
        assert turn["generation_attempts"][0]["transcript"]["error.code"] == "unavailable"
        assert state.status is RunStatus.CANCELLED
        assert state.last_step is not None
        assert state.last_step.feedback == "policy_cancelled:enclosing_deadline"
        assert events[-1]["event"] == "run_finished"

    asyncio.run(scenario())


def test_model_turn_trace_reads_explicit_invocation_result_before_adapter_mirrors(tmp_path) -> None:
    del tmp_path

    from types import SimpleNamespace

    from affordance_runtime.agent import Abort
    from affordance_runtime.agent.observability import model_turn_payload
    from affordance_runtime.model.policy import ModelInvocationResult, ModelMetadata, ResolvedModelDecision

    context = SimpleNamespace(
        context_id="context:trace",
        actions=SimpleNamespace(options=()),
        image_inputs=(),
    )
    attempts = (
        ModelGenerationAttempt(
            1,
            "initial",
            "grounded_tools.v2",
            "accepted",
            envelope_projection={"messages": [{"content": "canonical-input"}]},
            transcript={"llm.output_messages": [{"content": "from-result"}]},
        ),
    )

    class Policy:
        last_invocation_result = ModelInvocationResult(
            output=ResolvedModelDecision(Abort(context.context_id, "done", "policy")),
            metadata=ModelMetadata(provider_id="fixture", model_id="scripted"),
            attempts=attempts,
        )

    payload = model_turn_payload(context, Abort(context.context_id, "done", "policy"), Policy())

    assert payload["generation_attempts"][0]["phase"] == "initial"
    assert payload["generation_attempts"][0]["transcript"]["llm.output_messages"][0]["content"] == "from-result"
    assert "provider_attempts" not in payload
    assert "model_invocation" not in payload
    assert "envelope_projection" not in payload["generation_attempts"][0]
    assert json.dumps(payload).count("from-result") == 1
    assert "canonical-input" not in json.dumps(payload)
    assert "strategy_revision" not in payload


def test_goal_compiler_trace_event_keeps_attempt_transcripts_out_of_run_state(tmp_path) -> None:
    from affordance_runtime.agent.observability import goal_compiler_trace_diagnostic
    from affordance_runtime.goals import Failed
    from affordance_runtime.model.policy import ModelInvocationResult
    from affordance_runtime.model.policy.contracts import ModelGenerationAttempt

    class Compiler:
        last_invocation_result = ModelInvocationResult(
            output=Failed(1, "invalid_goal_proposal"),
            attempts=(
                ModelGenerationAttempt(
                    1,
                    "goal_compile_initial",
                    "GoalCompilerModelResponse",
                    "schema_error",
                    transcript={"llm.output_messages": [{"content": "raw one"}]},
                ),
                ModelGenerationAttempt(
                    2,
                    "goal_compile_schema_repair",
                    "GoalCompilerModelResponse",
                    "accepted",
                    transcript={"llm.output_messages": [{"content": "raw two"}]},
                ),
            ),
            repair_diagnostics=({"kind": "structured_output_repair", "count": 1},),
        )
        port = type("Port", (), {"provider": "fixture", "model": "model"})()
        config = type("Config", (), {"prompt_version": "prompt.v1"})()

    diagnostic = goal_compiler_trace_diagnostic(
        Compiler(),
        Failed(1, "invalid_goal_proposal"),
        task_revision=1,
        trigger="task_start",
        initial_evidence=None,
    )
    recorder = RunTraceRecorder(tmp_path)
    recorder.goal_compiler_completed(diagnostic)
    event = json.loads(recorder.path.read_text())

    assert event["event"] == "goal_compiler_completed"
    assert [
        item["transcript"]["llm.output_messages"][0]["content"] for item in event["diagnostic"]["generation_attempts"]
    ] == [
        "raw one",
        "raw two",
    ]
    assert event["diagnostic"]["schema_repair_count"] == 1
    assert "run_state" not in event["diagnostic"]


def test_binary_payloads_are_content_addressed_and_not_inlined(tmp_path) -> None:
    @dataclass(frozen=True)
    class Payload:
        screenshot: bytes

    recorder = RunTraceRecorder(tmp_path)
    recorder._emit("test", payload={"ok": True})
    from affordance_runtime.agent.observability import _json_value

    projected = _json_value(Payload(b"image-bytes"), tmp_path)
    artifact = projected["screenshot"]["artifact"]
    assert artifact["size_bytes"] == 11
    assert (tmp_path / artifact["path"]).read_bytes() == b"image-bytes"
    assert b"image-bytes" not in recorder.path.read_bytes()


def test_dataclass_projection_skips_explicit_non_serialized_fields(tmp_path) -> None:
    from dataclasses import field

    @dataclass(frozen=True)
    class Payload:
        public: str
        private: str = field(metadata={"serialize": False})

    from affordance_runtime.agent.observability import _json_value

    assert _json_value(Payload("visible", "secret-binding"), tmp_path) == {
        "public": "visible",
    }


def test_transcript_data_urls_are_content_addressed(tmp_path) -> None:
    from affordance_runtime.agent.observability import _json_value

    RunTraceRecorder(tmp_path)
    encoded = "aW1hZ2UtYnl0ZXM="
    projected = _json_value(
        {"llm.input_messages": [{"image_url": f"data:image/png;base64,{encoded}"}]},
        tmp_path,
    )

    artifact = projected["llm.input_messages"][0]["image_url"]["artifact"]
    assert artifact["mime_type"] == "image/png"
    assert (tmp_path / artifact["path"]).read_bytes() == b"image-bytes"


def test_start_failure_preserves_acquisition_diagnostics(tmp_path) -> None:
    recorder = RunTraceRecorder(tmp_path)
    recorder.run_start_failed(
        {"task_id": "t"},
        {"reason_code": "required_source_exhausted", "source_results": [{"source": "dom"}]},
    )
    event = json.loads(recorder.path.read_text().strip())
    assert event["event"] == "run_start_failed"
    assert event["acquisition"]["reason_code"] == "required_source_exhausted"


def test_remote_viewer_failure_never_changes_local_trace(tmp_path) -> None:
    worker = LangfuseViewerProcess(lambda: (_ for _ in ()).throw(RuntimeError("unreachable")))
    recorder = QueuedViewerRunTraceRecorder(tmp_path, viewer_process=worker)
    recorder.case_lifecycle_phase("CASE_BODY_RETURNED")
    recorder.flush_viewer(timeout_s=0.2)

    assert recorder.events[0]["event"] == "case_lifecycle_phase"
    assert recorder.path.exists()
    assert recorder.errors == []
    assert recorder.viewer_disabled
    assert recorder.viewer_errors == ["viewer_init:RuntimeError"]


def test_langfuse_requires_local_trace_authority() -> None:
    with pytest.raises(ValueError, match="local JSONL"):
        trace_recorder_from_environment({"AFFORDANCE_LANGFUSE_ENABLED": "true"})


def test_langfuse_requires_official_sdk_credentials(tmp_path) -> None:
    with pytest.raises(ValueError, match="SDK credentials"):
        trace_recorder_from_environment(
            {"AFFORDANCE_LANGFUSE_ENABLED": "true"},
            directory=tmp_path,
        )


def test_environment_config_constructs_langfuse_client_only_in_viewer_process(
    monkeypatch,
    tmp_path,
) -> None:
    from affordance_runtime.agent import observability

    owners = multiprocessing.Queue()

    @dataclass
    class Observation:
        def update(self, **_event):
            return None

        def end(self):
            return None

    @dataclass
    class Context:
        observation: Observation

        def __enter__(self):
            return self.observation

        def __exit__(self, *_args):
            return None

    class Client:
        def start_as_current_observation(self, **_kwargs):
            return Context(Observation())

        def flush(self):
            return None

    def factory():
        owners.put((multiprocessing.current_process().name, multiprocessing.current_process().daemon))
        return Client()

    monkeypatch.setattr(observability, "_langfuse_client_from_environment", factory)
    recorder = trace_recorder_from_environment(
        {
            "AFFORDANCE_LANGFUSE_ENABLED": "true",
            "LANGFUSE_PUBLIC_KEY": "pk-lf-provider-free",
            "LANGFUSE_SECRET_KEY": "sk-lf-provider-free",
        },
        directory=tmp_path,
        benchmark_managed=True,
    )
    assert isinstance(recorder, QueuedViewerRunTraceRecorder)
    recorder.benchmark_case_started(case_id="case:worker-owner", description="public", timeout_s=1)
    recorder.benchmark_case_finished(case_id="case:worker-owner", status="done")
    recorder.flush_viewer(timeout_s=0.5)

    assert owners.get(timeout=0.5) == ("langfuse-viewer-process", True)


def test_viewer_process_consumes_only_after_local_jsonl_record(tmp_path) -> None:
    observed = multiprocessing.Queue()

    @dataclass
    class Observation:
        def update(self, **_event):
            return None

        def end(self):
            return None

    @dataclass
    class Context:
        observation: Observation

        def __enter__(self):
            return self.observation

        def __exit__(self, *_args):
            return None

    class Client:
        def start_as_current_observation(self, *, name, **_kwargs):
            lines = (tmp_path / "trace.jsonl").read_text().splitlines()
            assert any(json.loads(line)["event"] == "benchmark_case_started" for line in lines)
            observed.put(name)
            return Context(Observation())

        def flush(self):
            return None

    recorder = QueuedViewerRunTraceRecorder(
        tmp_path,
        viewer_process=LangfuseViewerProcess(lambda: Client(), benchmark_managed=True),
    )
    recorder.benchmark_case_started(case_id="case:local-first", description="public", timeout_s=1)
    recorder.benchmark_case_finished(case_id="case:local-first", status="failed")
    recorder.flush_viewer(timeout_s=0.5)

    assert observed.get(timeout=0.5) == "benchmark-gui-agent-case"


def test_viewer_queue_full_drops_without_runtime_latency(tmp_path) -> None:
    release_factory = multiprocessing.Event()

    class Client:
        pass

    def blocked_factory():
        release_factory.wait()
        return Client()

    worker = LangfuseViewerProcess(blocked_factory, queue_capacity=1)
    recorder = QueuedViewerRunTraceRecorder(tmp_path, viewer_process=worker)

    started = time.perf_counter()
    recorder.case_lifecycle_phase("CASE_STARTED")
    recorder.case_lifecycle_phase("CASE_BODY_RETURNED")
    elapsed = time.perf_counter() - started
    release_factory.set()
    worker.close(timeout_s=0.5)

    assert elapsed < 0.1
    assert recorder.viewer_dropped_event_count == 1
    assert recorder.viewer_disabled
    assert "viewer_queue_full" in recorder.viewer_errors


@pytest.mark.parametrize(
    "fault",
    (BrokenPipeError("broken"), EOFError("eof"), OSError("os"), ValueError("closed")),
)
def test_viewer_ipc_fault_matrix_is_a_total_fail_open_drop(fault: Exception) -> None:
    class AliveProcess:
        @staticmethod
        def is_alive():
            return True

    class BrokenQueue:
        @staticmethod
        def put_nowait(_event):
            raise fault

    class EmptyStatusQueue:
        @staticmethod
        def get_nowait():
            raise queue.Empty

    worker = object.__new__(LangfuseViewerProcess)
    worker.errors = []
    worker.dropped_event_count = 0
    worker.disabled = False
    worker.flush_timeout = False
    worker._queue = BrokenQueue()
    worker._status_queue = EmptyStatusQueue()
    worker._process = AliveProcess()
    worker._lock = threading.Lock()
    worker._closed = False

    admitted = worker.enqueue({"event": "step_completed", "sequence": 1})

    assert admitted is False
    assert worker.dropped_event_count == 1
    assert worker.disabled is True
    assert worker.errors == [f"viewer_ipc_unavailable:{type(fault).__name__}"]


def test_viewer_closed_queue_and_repeated_close_are_total_fail_open() -> None:
    class StoppedProcess:
        exitcode = 0

        @staticmethod
        def join(_timeout):
            return None

        @staticmethod
        def is_alive():
            return False

    class ClosedQueue:
        @staticmethod
        def put_nowait(_event):
            raise ValueError("Queue is closed")

        @staticmethod
        def close():
            return None

    class EmptyStatusQueue:
        @staticmethod
        def get_nowait():
            raise ValueError("Queue is closed")

        @staticmethod
        def close():
            return None

    worker = object.__new__(LangfuseViewerProcess)
    worker.errors = []
    worker.dropped_event_count = 0
    worker.disabled = False
    worker.flush_timeout = False
    worker._queue = ClosedQueue()
    worker._status_queue = EmptyStatusQueue()
    worker._process = StoppedProcess()
    worker._lock = threading.Lock()
    worker._closed = False

    assert worker.close(timeout_s=0.01) is False
    assert worker.close(timeout_s=0.01) is False
    assert worker.disabled is True
    assert worker.errors == ["viewer_stop_unavailable:ValueError"]


def test_viewer_record_hang_cannot_block_case_body_or_local_terminal_events(tmp_path) -> None:
    entered = multiprocessing.Event()
    never_release = multiprocessing.Event()

    class Client:
        def start_as_current_observation(self, **_kwargs):
            entered.set()
            never_release.wait()

    recorder = QueuedViewerRunTraceRecorder(
        tmp_path,
        viewer_process=LangfuseViewerProcess(lambda: Client(), benchmark_managed=True),
    )
    recorder.benchmark_case_started(case_id="case:hung-viewer", description="public", timeout_s=1)
    assert entered.wait(0.5)

    started = time.perf_counter()
    recorder.case_lifecycle_phase("CASE_BODY_RETURNED")
    recorder.benchmark_case_finished(case_id="case:hung-viewer", status="failed")
    recorder.flush_viewer(timeout_s=0.05)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2
    assert recorder.viewer_disabled
    assert "viewer_flush_timeout" in recorder.viewer_errors
    persisted = [json.loads(line)["event"] for line in recorder.path.read_text().splitlines()]
    assert "case_lifecycle_phase" in persisted
    assert "benchmark_case_finished" in persisted
    assert "viewer_status" in persisted


def test_viewer_flush_hang_is_bounded_and_keeps_case_status_local(tmp_path) -> None:
    flush_entered = multiprocessing.Event()
    never_release = multiprocessing.Event()

    @dataclass
    class Observation:
        def update(self, **_event):
            return None

        def end(self):
            return None

    @dataclass
    class Context:
        observation: Observation

        def __enter__(self):
            return self.observation

        def __exit__(self, *_args):
            return None

    class Client:
        def start_as_current_observation(self, **_kwargs):
            return Context(Observation())

        def flush(self):
            flush_entered.set()
            never_release.wait()

    recorder = QueuedViewerRunTraceRecorder(
        tmp_path,
        viewer_process=LangfuseViewerProcess(lambda: Client(), benchmark_managed=True),
    )
    recorder.benchmark_case_started(case_id="case:flush-hang", description="public", timeout_s=1)
    recorder.benchmark_case_finished(case_id="case:flush-hang", status="failed")

    started = time.perf_counter()
    recorder.flush_viewer(timeout_s=0.05)
    elapsed = time.perf_counter() - started

    assert flush_entered.is_set()
    assert elapsed < 0.2
    assert recorder.viewer_disabled
    assert "viewer_flush_timeout" in recorder.viewer_errors
    assert any(
        event.get("event") == "benchmark_case_finished" and event.get("status") == "failed" for event in recorder.events
    )


def test_langfuse_projection_is_bounded_and_excludes_private_or_bulk_data() -> None:
    projected = _langfuse_event_projection(
        {
            "event": "step_completed",
            "sequence": 3,
            "lineage": {"request_id": "request:1"},
            "result": {
                "feedback": "ok",
                "decision": {
                    "kind": "select_action",
                    "selector": "#nested-private",
                    "BID": "nested-42",
                    "private_bid": "nested-private-42",
                    "private_element_id": "element-private-42",
                    "browsergym_id": "environment-private-42",
                    "nodeId": "node-private-42",
                    "preview": "data:image/png;base64,nested-large",
                },
                "binding": {"selector": "#private", "bid": "42"},
                "before_world": {"screenshot": "data:image/png;base64,large"},
            },
        }
    )

    assert projected["result"] == {
        "feedback": "ok",
        "decision": {
            "kind": "select_action",
            "preview": "[binary-content-omitted]",
        },
    }
    assert "private" not in json.dumps(projected)
    assert "base64" not in json.dumps(projected)


def test_langfuse_projection_has_a_total_serialized_bound() -> None:
    projected = _langfuse_event_projection(
        {
            "event": "model_turn",
            "sequence": 4,
            "decision": {f"public-{index}": "x" * 1_000 for index in range(100)},
        }
    )

    assert len(json.dumps(projected).encode()) <= 16_384
    assert projected["projection_truncated"] is True


def test_one_megabyte_trace_event_is_projected_before_viewer_ipc(tmp_path) -> None:
    captured = []

    class CapturingViewer:
        errors = []
        dropped_event_count = 0
        disabled = False
        flush_timeout = False

        def enqueue(self, event):
            captured.append(event)
            return True

        def close(self, *, timeout_s):
            del timeout_s
            return True

        def _drain_status(self):
            return None

    recorder = QueuedViewerRunTraceRecorder(
        tmp_path,
        viewer_process=CapturingViewer(),
    )
    recorder._emit(
        "model_turn",
        model_metadata={"provider_id": "fixture", "model_id": "fixture-model"},
        generation_attempts=[
            {
                "attempt": 1,
                "phase": "representation_repair",
                "status": "failed",
                "transcript": {
                    "llm.input_messages": [{"role": "user", "content": "x" * 1_000_000}],
                    "llm.output_messages": [],
                },
            }
        ],
    )

    assert recorder.path.stat().st_size > 1_000_000
    assert len(captured) == 1
    assert len(json.dumps(captured[0], sort_keys=True).encode()) <= 16_384
    assert captured[0]["event"] == "model_turn"
    assert captured[0]["model_metadata"] == {
        "provider_id": "fixture",
        "model_id": "fixture-model",
    }
    assert captured[0]["generation_attempts"][0]["phase"] == "representation_repair"
    assert captured[0]["generation_attempts"][0]["transcript"]["llm.input_messages"][0] == {
        "role": "user",
        "content": "x" * 512,
    }


def test_ipc_projection_of_run13_sized_event_is_bounded_and_ref_free() -> None:
    projected = _langfuse_ipc_projection(
        {
            "event": "step_completed",
            "sequence": 20,
            "result": {
                "feedback": "manager failure persisted",
                "decision": {"kind": "select_action", "selector": "#private"},
                "before_world": {"bulk": "x" * 1_100_000},
            },
        }
    )

    encoded = json.dumps(projected, sort_keys=True)
    assert len(encoded.encode()) <= 16_384
    assert "#private" not in encoded
    assert "x" * 1_000 not in encoded


def test_langfuse_root_task_projection_has_the_same_total_bound() -> None:
    projected = _public_task_projection(
        {
            "task_id": "public-task",
            "goal": {f"branch-{index}": {f"leaf-{leaf}": "x" * 1_000 for leaf in range(40)} for index in range(40)},
        }
    )

    assert len(json.dumps(projected).encode()) <= 16_384
    assert projected["projection_truncated"] is True


def test_langfuse_v4_session_attributes_cover_root_and_children(tmp_path) -> None:
    langfuse_module = pytest.importorskip("langfuse")
    trace_module = pytest.importorskip("opentelemetry.sdk.trace")
    exporter_module = pytest.importorskip("opentelemetry.sdk.trace.export.in_memory_span_exporter")
    exporter = exporter_module.InMemorySpanExporter()
    provider = trace_module.TracerProvider()
    client = langfuse_module.Langfuse(
        public_key="pk-lf-session-contract",
        secret_key="sk-lf-session-contract",
        tracer_provider=provider,
        span_exporter=exporter,
    )
    sink = LangfuseOtelSink(
        client,
        session_id="suite:provider-free",
        benchmark_managed=True,
    )
    sink.record(
        {
            "event": "benchmark_case_started",
            "run_id": "run:provider-free",
            "sequence": 1,
            "case_id": "case:provider-free",
            "description": "public instruction",
        }
    )
    sink.record(
        {
            "event": "benchmark_case_finished",
            "run_id": "run:provider-free",
            "sequence": 2,
            "case_id": "case:provider-free",
            "status": "done",
        }
    )
    sink.flush()

    spans = exporter.get_finished_spans()
    assert {span.attributes.get("session.id") for span in spans} == {"suite:provider-free"}
    client.shutdown()


def test_langfuse_generation_uses_standard_model_usage_real_duration_and_attempt_tags() -> None:
    langfuse_module = pytest.importorskip("langfuse")
    trace_module = pytest.importorskip("opentelemetry.sdk.trace")
    exporter_module = pytest.importorskip("opentelemetry.sdk.trace.export.in_memory_span_exporter")
    exporter = exporter_module.InMemorySpanExporter()
    provider = trace_module.TracerProvider()
    client = langfuse_module.Langfuse(
        public_key="pk-lf-provider-free",
        secret_key="sk-lf-provider-free",
        tracer_provider=provider,
        span_exporter=exporter,
    )
    attempt_id = "attempt:" + "a" * 32
    identity = {
        "run_attempt_id": attempt_id,
        "suite_id": "suite",
        "profile_id": "profile",
        "case_id": "case",
        "environment": "test",
        "release": "target-loop-harness.v6",
    }
    sink = LangfuseOtelSink(client, session_id=attempt_id, benchmark_managed=True)
    sink.record(
        _langfuse_ipc_projection(
            {
                "event": "benchmark_case_started",
                "run_id": "case:local",
                "sequence": 1,
                "case_id": "case",
                "description": "public",
                "analysis_identity": identity,
            }
        )
    )
    sink.record(
        _langfuse_ipc_projection(
            {
                "event": "model_turn",
                "run_id": "case:local",
                "sequence": 2,
                "analysis_identity": identity,
                "model_metadata": {"provider_id": "fixture", "model_id": "fixture-model"},
                "generation_attempts": [
                    {
                        "attempt": 1,
                        "phase": "ordinary",
                        "status": "accepted",
                        "latency_ms": 125.0,
                        "prompt_tokens": 11,
                        "completion_tokens": 3,
                        "total_tokens": 14,
                        "transcript": {
                            "llm.input_messages": [{"role": "user", "content": "safe input"}],
                            "llm.output_messages": [{"role": "assistant", "content": "safe output"}],
                        },
                    }
                ],
            }
        )
    )
    sink.record(
        _langfuse_ipc_projection(
            {
                "event": "benchmark_case_finished",
                "run_id": "case:local",
                "sequence": 3,
                "case_id": "case",
                "status": "done",
                "analysis_identity": identity,
            }
        )
    )
    sink.flush()

    generation = next(span for span in exporter.get_finished_spans() if span.name == "action-policy-generation")
    assert (generation.end_time - generation.start_time) / 1_000_000 == pytest.approx(125.0)
    assert generation.attributes["langfuse.observation.model.name"] == "fixture-model"
    assert generation.attributes["langfuse.observation.usage_details"] == ('{"input": 11, "output": 3, "total": 14}')
    assert generation.attributes["langfuse.observation.input"] == (
        '{"messages": [{"role": "user", "content": "safe input"}]}'
    )
    assert generation.attributes["session.id"] == attempt_id
    assert "run_attempt_id:" + attempt_id in generation.attributes["langfuse.trace.tags"]
    assert "suite_id:suite" in generation.attributes["langfuse.trace.tags"]
    assert "profile_id:profile" in generation.attributes["langfuse.trace.tags"]
    assert generation.attributes["langfuse.observation.metadata.cost_disposition"] == (
        "langfuse_model_definition_required"
    )
    client.shutdown()


def test_benchmark_case_owns_one_queued_root_and_one_action_policy_generation(tmp_path) -> None:
    observed = multiprocessing.Queue()
    flushes = multiprocessing.Value("i", 0)

    @dataclass
    class Observation:
        name: str
        as_type: str

        def update(self, **_event) -> None:
            return None

        def end(self) -> None:
            observed.put(("ended", self.name, self.as_type, None))

    @dataclass
    class ObservationContext:
        observation: Observation

        def __enter__(self):
            return self.observation

        def __exit__(self, *_args):
            return None

    class Client:
        def start_as_current_observation(self, *, name, **kwargs):
            observation = Observation(name, kwargs.get("as_type", "span"))
            observed.put(("started", name, observation.as_type, kwargs.get("input")))
            return ObservationContext(observation)

        def flush(self):
            with flushes.get_lock():
                flushes.value += 1

    recorder = QueuedViewerRunTraceRecorder(
        tmp_path,
        viewer_process=LangfuseViewerProcess(Client, benchmark_managed=True),
    )
    recorder.benchmark_case_started(
        case_id="case:policy-failure",
        description="x" * 100_000,
        timeout_s=10,
    )
    recorder._emit(
        "model_turn",
        model_metadata={"provider_id": "fixture", "model_id": "fixture-model"},
        generation_attempts=[
            {
                "attempt": 1,
                "phase": "ordinary",
                "trigger": "ordinary",
                "status": "accepted",
                "max_output_tokens": 768,
                "prompt_tokens": 11,
                "completion_tokens": 3,
                "total_tokens": 14,
                "transcript": {
                    "llm.input_messages": [{"role": "user", "content": "public world"}],
                    "llm.output_messages": [{"role": "assistant", "content": "tool call"}],
                },
            }
        ],
    )
    recorder._emit(
        "step_completed",
        step=1,
        lineage={},
        result={"feedback": "sent", "decision": {"kind": "select_action"}},
    )
    recorder.benchmark_case_finished(case_id="case:policy-failure", status="failed")
    recorder.flush_viewer(timeout_s=0.5)

    events = []
    while not observed.empty():
        events.append(observed.get())
    started_events = [item for item in events if item[0] == "started"]
    names = {item[1] for item in started_events}
    assert "benchmark-gui-agent-case" in names
    assert sum(item[1] == "action-policy-generation" for item in started_events) == 1
    assert "runtime-step" in names
    assert "run-gui-agent-case" not in names
    assert ("ended", "benchmark-gui-agent-case", "agent", None) in events
    assert flushes.value == 1
    root_input = started_events[0][3]
    assert len(json.dumps(root_input).encode()) <= 16_384
    assert len(root_input["description"]) < 100_000

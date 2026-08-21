import asyncio
import json
import threading
import time
from dataclasses import dataclass

import pytest

from affordance_runtime.agent.observability import (
    LangfuseViewerWorker,
    QueuedViewerRunTraceRecorder,
    RunTraceRecorder,
    _langfuse_event_projection,
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


def test_core_loop_persists_complete_lineage_and_deduplicated_worlds(tmp_path) -> None:
    async def scenario() -> None:
        recorder = RunTraceRecorder(tmp_path)
        runtime = _runtime("first_action")
        object.__setattr__(runtime, "trace_sink", recorder)
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        await runtime.run_task(environment, _task())

        persisted = [json.loads(line) for line in recorder.path.read_text().splitlines()]
        assert [item["event"] for item in persisted] == [
            "run_started",
            "observation",
            "goal_compiler_completed",
            "model_turn",
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
        step = next(item for item in persisted if item["event"] == "step_completed")
        assert step["lineage"]["tool_call_id"] == "provider-call:test"
        assert step["lineage"]["request_id"].startswith("request:")
        assert step["lineage"]["before_observation_id"] == "before"
        assert step["lineage"]["after_observation_id"] == "after"
        assert "before_world" not in step["result"]
        assert "after_world" not in step["result"]
        assert step["result"]["execution"] is not None
        assert step["result"]["action_outcome"] is not None
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

        with pytest.raises(asyncio.CancelledError):
            await runtime.run_task(
                ScriptedEnvironment(initial_observation=_world("before", False)),
                _task(),
            )

        events = [json.loads(line) for line in recorder.path.read_text().splitlines()]
        turn = next(item for item in events if item["event"] == "model_turn")
        assert turn["exception"] == "CancelledError"
        assert turn["generation_attempts"][0]["transcript"]["error.code"] == "unavailable"
        assert events[-1]["event"] == "run_error"

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
                    1, "goal_compile_initial", "GoalCompilerModelResponse",
                    "schema_error", transcript={"llm.output_messages": [{"content": "raw one"}]},
                ),
                ModelGenerationAttempt(
                    2, "goal_compile_schema_repair", "GoalCompilerModelResponse",
                    "accepted", transcript={"llm.output_messages": [{"content": "raw two"}]},
                ),
            ),
            repair_diagnostics=({"kind": "structured_output_repair", "count": 1},),
        )
        port = type("Port", (), {"provider": "fixture", "model": "model"})()
        config = type("Config", (), {"prompt_version": "prompt.v1"})()

    diagnostic = goal_compiler_trace_diagnostic(
        Compiler(), Failed(1, "invalid_goal_proposal"), task_revision=1,
        trigger="task_start", initial_evidence=None,
    )
    recorder = RunTraceRecorder(tmp_path)
    recorder.goal_compiler_completed(diagnostic)
    event = json.loads(recorder.path.read_text())

    assert event["event"] == "goal_compiler_completed"
    assert [item["transcript"]["llm.output_messages"][0]["content"] for item in event["diagnostic"]["generation_attempts"]] == [
        "raw one", "raw two",
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
    worker = LangfuseViewerWorker(
        lambda: (_ for _ in ()).throw(RuntimeError("unreachable"))
    )
    recorder = QueuedViewerRunTraceRecorder(tmp_path, viewer_worker=worker)
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


def test_environment_config_constructs_langfuse_client_only_in_daemon_worker(
    monkeypatch,
    tmp_path,
) -> None:
    from affordance_runtime.agent import observability

    owner_threads = []

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
        owner_threads.append((threading.current_thread().name, threading.current_thread().daemon))
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

    assert owner_threads == [("langfuse-viewer-worker", True)]


def test_viewer_worker_consumes_only_after_local_jsonl_record(tmp_path) -> None:
    observed = []

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
            assert any(
                json.loads(line)["event"] == "benchmark_case_started"
                for line in lines
            )
            observed.append(name)
            return Context(Observation())

        def flush(self):
            return None

    recorder = QueuedViewerRunTraceRecorder(
        tmp_path,
        viewer_worker=LangfuseViewerWorker(lambda: Client(), benchmark_managed=True),
    )
    recorder.benchmark_case_started(case_id="case:local-first", description="public", timeout_s=1)
    recorder.benchmark_case_finished(case_id="case:local-first", status="failed")
    recorder.flush_viewer(timeout_s=0.5)

    assert observed[0] == "benchmark-gui-agent-case"


def test_viewer_queue_full_drops_without_runtime_latency(tmp_path) -> None:
    release_factory = threading.Event()

    class Client:
        pass

    def blocked_factory():
        release_factory.wait()
        return Client()

    worker = LangfuseViewerWorker(blocked_factory, queue_capacity=1)
    recorder = QueuedViewerRunTraceRecorder(tmp_path, viewer_worker=worker)

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


def test_viewer_record_hang_cannot_block_case_body_or_local_terminal_events(tmp_path) -> None:
    entered = threading.Event()
    never_release = threading.Event()

    class Client:
        def start_as_current_observation(self, **_kwargs):
            entered.set()
            never_release.wait()

    recorder = QueuedViewerRunTraceRecorder(
        tmp_path,
        viewer_worker=LangfuseViewerWorker(lambda: Client(), benchmark_managed=True),
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
    flush_entered = threading.Event()
    never_release = threading.Event()

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
        viewer_worker=LangfuseViewerWorker(lambda: Client(), benchmark_managed=True),
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
        event.get("event") == "benchmark_case_finished" and event.get("status") == "failed"
        for event in recorder.events
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


def test_langfuse_root_task_projection_has_the_same_total_bound() -> None:
    projected = _public_task_projection(
        {
            "task_id": "public-task",
            "goal": {
                f"branch-{index}": {f"leaf-{leaf}": "x" * 1_000 for leaf in range(40)}
                for index in range(40)
            },
        }
    )

    assert len(json.dumps(projected).encode()) <= 16_384
    assert projected["projection_truncated"] is True


def test_langfuse_v4_session_attributes_cover_root_and_children(tmp_path) -> None:
    langfuse_module = pytest.importorskip("langfuse")
    trace_module = pytest.importorskip("opentelemetry.sdk.trace")
    exporter_module = pytest.importorskip(
        "opentelemetry.sdk.trace.export.in_memory_span_exporter"
    )
    exporter = exporter_module.InMemorySpanExporter()
    provider = trace_module.TracerProvider()
    clients = []

    def client_factory():
        client = langfuse_module.Langfuse(
            public_key="pk-lf-provider-free",
            secret_key="sk-lf-provider-free",
            tracer_provider=provider,
            span_exporter=exporter,
        )
        clients.append(client)
        return client

    recorder = QueuedViewerRunTraceRecorder(
        tmp_path,
        viewer_worker=LangfuseViewerWorker(
            client_factory,
            session_id="suite:provider-free",
            benchmark_managed=True,
        ),
    )
    recorder.benchmark_case_started(
        case_id="case:provider-free",
        description="public instruction",
        timeout_s=1,
    )
    recorder.benchmark_case_finished(case_id="case:provider-free", status="done")
    recorder.flush_viewer(timeout_s=1)

    spans = exporter.get_finished_spans()
    assert {span.attributes.get("session.id") for span in spans} == {
        "suite:provider-free"
    }
    clients[0].shutdown()


def test_benchmark_case_owns_one_queued_root_and_one_typed_manager_generation(tmp_path) -> None:
    @dataclass
    class Observation:
        name: str
        as_type: str
        ended: bool = False

        def update(self, **_event) -> None:
            return None

        def end(self) -> None:
            self.ended = True

    @dataclass
    class ObservationContext:
        observation: Observation

        def __enter__(self):
            return self.observation

        def __exit__(self, *_args):
            return None

    @dataclass
    class Client:
        observations: list[Observation] = None
        inputs: list[object] = None
        flushes: int = 0

        def __post_init__(self):
            self.observations = []
            self.inputs = []

        def start_as_current_observation(self, *, name, **kwargs):
            observation = Observation(name, kwargs.get("as_type", "span"))
            self.observations.append(observation)
            self.inputs.append(kwargs.get("input"))
            return ObservationContext(observation)

        def flush(self):
            self.flushes += 1

    client = Client()
    recorder = QueuedViewerRunTraceRecorder(
        tmp_path,
        viewer_worker=LangfuseViewerWorker(lambda: client, benchmark_managed=True),
    )
    recorder.benchmark_case_started(
        case_id="case:manager-failure",
        description="x" * 100_000,
        timeout_s=10,
    )
    recorder._emit(
        "mission_role_invocation",
        role="manager",
        result="failure",
        model_invocation={
            "metadata": {"provider_id": "fixture", "model_id": "fixture-model"},
            "attempts": [{
                "attempt": 1,
                "phase": "manager_initial",
                "trigger": "task_start",
                "status": "failed",
                "max_output_tokens": 2048,
                "prompt_tokens": 7,
                "completion_tokens": 0,
                "total_tokens": 7,
                "transcript": {
                    "llm.input_messages": [{"role": "user", "content": "public task"}],
                    "llm.output_messages": [],
                },
            }],
        },
    )
    recorder._emit(
        "model_turn",
        model_metadata={"provider_id": "fixture", "model_id": "fixture-model"},
        generation_attempts=[{
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
        }],
    )
    recorder._emit(
        "step_completed",
        step=1,
        lineage={},
        result={"feedback": "sent", "decision": {"kind": "select_action"}},
    )
    recorder.benchmark_case_finished(case_id="case:manager-failure", status="failed")
    recorder.flush_viewer(timeout_s=0.5)

    names = {observation.name for observation in client.observations}
    assert "benchmark-gui-agent-case" in names
    assert "manager-call" in names
    assert sum(item.name == "manager-generation" for item in client.observations) == 1
    assert next(
        item for item in client.observations if item.name == "manager-generation"
    ).as_type == "generation"
    assert sum(item.name == "action-policy-generation" for item in client.observations) == 1
    assert "runtime-step" in names
    assert "run-gui-agent-case" not in names
    assert client.observations[0].ended is True
    assert client.flushes == 1
    assert len(json.dumps(client.inputs[0]).encode()) <= 16_384
    assert len(client.inputs[0]["description"]) < 100_000


def test_langfuse_projection_keeps_only_execution_relevant_public_subtask() -> None:
    projected = _langfuse_event_projection(
        {
            "event": "model_turn",
            "sequence": 2,
            "agent_context": {
                "task": {
                    "active_subtask": {
                        "objective": "Collect the current result",
                        "done_when": "The result is visible",
                        "outcome_kind": "evidence_packet",
                        "constraints": ["read only"],
                        "required_evidence": [
                            {"key": "result", "description": "Current result", "status": "available"}
                        ],
                        "episode_turn_budget": 8,
                        "relevant_fact_keys": ["private-filter"],
                        "related_audit_ids": ["audit:private"],
                    }
                }
            },
            "decision": {"kind": "yield_subtask"},
        }
    )

    assert projected["active_subtask"]["objective"] == "Collect the current result"
    assert "episode_turn_budget" not in projected["active_subtask"]
    assert "relevant_fact_keys" not in projected["active_subtask"]
    assert "related_audit_ids" not in projected["active_subtask"]

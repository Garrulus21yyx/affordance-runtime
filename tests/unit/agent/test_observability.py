import asyncio
import json
from dataclasses import dataclass

import pytest

from affordance_runtime.agent.observability import (
    LangfuseTraceExporter,
    RunTraceRecorder,
    trace_recorder_from_environment,
)
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.execution.contracts import ActionResult, DispatchStatus
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.model.policy.contracts import ModelGenerationAttempt
from tests.integration.agent.test_core_loop import (
    CoreActionEvaluator,
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
        assert step["result"]["action_evaluation"] is not None
        assert step["result"]["task_evaluation"]["status"] == "complete"

    asyncio.run(scenario())


def test_cancelled_policy_turn_projects_already_captured_provider_attempts(tmp_path) -> None:
    class CancelledPolicy:
        last_catalog_count = 0
        last_generation_attempts = (
            ModelGenerationAttempt(
                1,
                "initial",
                "grounded_tools.v2",
                "failed",
                exception_class="ModelAPIError",
                transcript={"error.code": "unavailable"},
            ),
        )

        async def decide(self, _context):
            raise asyncio.CancelledError

    async def scenario() -> None:
        recorder = RunTraceRecorder(tmp_path)
        runtime = TargetRuntime(
            AgentDecisionPorts(CancelledPolicy()),
            CoreActionEvaluator(),
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



def test_goal_compiler_trace_event_keeps_attempt_transcripts_out_of_run_state(tmp_path) -> None:
    from affordance_runtime.agent.observability import goal_compiler_trace_diagnostic
    from affordance_runtime.goals import Failed
    from affordance_runtime.model.policy.contracts import ModelGenerationAttempt

    class Compiler:
        last_schema_repair_count = 1
        last_generation_attempts = (
            ModelGenerationAttempt(
                1, "goal_compile_initial", "GoalCompilerModelResponse",
                "schema_error", transcript={"llm.output_messages": [{"content": "raw one"}]},
            ),
            ModelGenerationAttempt(
                2, "goal_compile_schema_repair", "GoalCompilerModelResponse",
                "accepted", transcript={"llm.output_messages": [{"content": "raw two"}]},
            ),
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


def test_exporter_failure_never_changes_local_trace(tmp_path) -> None:
    class BrokenExporter:
        def emit(self, event):
            raise RuntimeError(event["event"])

        def flush(self):
            raise RuntimeError("flush")

    recorder = RunTraceRecorder(tmp_path, BrokenExporter())
    recorder.run_resumed("user", {"revision": 2})
    assert recorder.events[0]["event"] == "run_resumed"
    assert recorder.path.exists()
    assert recorder.errors == ["run_resumed:RuntimeError"]


def test_langfuse_requires_local_trace_authority() -> None:
    with pytest.raises(ValueError, match="AFFORDANCE_TRACE_DIR"):
        trace_recorder_from_environment({"AFFORDANCE_LANGFUSE_ENABLED": "true"})


def test_langfuse_projection_uses_one_agent_root_and_child_observations() -> None:
    class Observation:
        def __init__(self):
            self.children = []
            self.ended = False

        def start_observation(self, **kwargs):
            child = Observation()
            child.kwargs = kwargs
            self.children.append(child)
            return child

        def update(self, **kwargs):
            self.output = kwargs

        def end(self):
            self.ended = True

    class Client:
        def __init__(self):
            self.root = None
            self.flushed = False

        def start_observation(self, **kwargs):
            self.root = Observation()
            self.root.kwargs = kwargs
            return self.root

        def flush(self):
            self.flushed = True

    client = Client()
    exporter = LangfuseTraceExporter(client)
    exporter.emit({"event": "run_started", "run_id": "run:1", "task": {"task_id": "t"}})
    exporter.emit(
        {
            "event": "model_turn",
            "run_id": "run:1",
            "agent_context": {"context_id": "context:1"},
            "decision": {"kind": "select_action"},
            "generation_attempts": (
                {
                    "attempt": 1,
                    "phase": "initial",
                    "schema_name": "GroundedToolCommandPayloadEnvelope",
                    "status": "accepted",
                },
            ),
        }
    )
    exporter.emit(
        {
            "event": "step_completed",
            "run_id": "run:1",
            "lineage": {"request_id": "request:1"},
            "result": {"binding": {"selector": "#private"}, "feedback": "ok"},
        }
    )
    exporter.emit({"event": "run_finished", "run_id": "run:1", "status": "done"})
    exporter.flush()

    assert client.root.kwargs["as_type"] == "agent"
    assert [item.kwargs["as_type"] for item in client.root.children] == ["chain", "tool"]
    assert client.root.children[0].children[0].kwargs["as_type"] == "generation"
    assert client.root.children[0].children[0].kwargs["name"] == "initial"
    assert "binding" not in client.root.children[1].kwargs["output"]
    assert client.root.ended
    assert client.flushed

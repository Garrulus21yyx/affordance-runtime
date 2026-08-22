from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from affordance_runtime.benchmarks.console.server import (
    ConsoleRun,
    ConsoleRunManager,
    ConsoleRunSpec,
)
from affordance_runtime.benchmarks.external_breadth.contracts import (
    MiniWobBreadthCase,
    MiniWobBreadthManifest,
)


class _Process:
    def __init__(self, code: int | None = None) -> None:
        self.code = code
        self.stdout = StringIO("")
        self.terminated = False

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.terminated = True
        self.code = -15


@pytest.fixture
def manifest() -> MiniWobBreadthManifest:
    case = MiniWobBreadthCase(
        "miniwob-60-17",
        "browsergym/miniwob.social-media-all",
        "current_primitives",
        ("activate",),
        10,
        180.0,
        7,
    )
    return MiniWobBreadthManifest(
        "test.v1",
        "test-campaign",
        "browsergym-miniwob",
        "0.14.3",
        "source",
        "registry",
        "inventory",
        "selection",
        "model",
        "grounding",
        0.0,
        (case,),
    )


def _manager(tmp_path: Path, manifest: MiniWobBreadthManifest) -> ConsoleRunManager:
    return ConsoleRunManager(
        tmp_path,
        python_executable="/fixed/python",
        environment={
            "LLM_ZHIPU_BASE_URL": "https://provider.invalid",
            "LLM_ZHIPU_API_KEY": "top-secret",
            "LLM_ZHIPU_MODEL": "configured-action",
            "LLM_GOAL_COMPILER_MODEL": "configured-goal",
        },
        manifest=manifest,
    )


def test_run_spec_rejects_unbounded_or_conflicting_inputs() -> None:
    with pytest.raises(ValueError, match="action_model"):
        ConsoleRunSpec("case", "model id with spaces", "disabled")
    with pytest.raises(ValueError, match="cannot select"):
        ConsoleRunSpec("case", "glm-4.6", "disabled", "glm-4.7-flash")
    with pytest.raises(ValueError, match="uppercase"):
        ConsoleRunSpec("case", "glm-4.6", "model", "glm-4.7-flash", profile="shell;run")
    with pytest.raises(ValueError, match="not a valid ActionPolicyWireCapability"):
        ConsoleRunSpec(
            "case",
            "glm-4.6",
            "disabled",
            action_wire_capability="parallel_tools",
        )


def test_configuration_exposes_manifest_choices_without_secrets(
    tmp_path: Path,
    manifest: MiniWobBreadthManifest,
) -> None:
    payload = _manager(tmp_path, manifest).configuration()

    assert payload["provider_ready"] is True
    assert payload["cases"] == [{
        "case_id": "miniwob-60-17",
        "task_id": "social-media-all",
        "seed": 7,
        "max_turns": 10,
        "timeout_s": 180.0,
    }]
    assert "configured-action" in {item["id"] for item in payload["action_models"]}
    assert payload["action_wire_capabilities"] == [
        "native_single_tool",
    ]
    assert "configured-goal" in payload["goal_models"]
    assert "top-secret" not in json.dumps(payload)


def test_role_selection_only_changes_owned_environment(
    tmp_path: Path,
    manifest: MiniWobBreadthManifest,
) -> None:
    manager = _manager(tmp_path, manifest)
    enabled = manager._run_environment(ConsoleRunSpec(
        "miniwob-60-17",
        "glm-4.6",
        "model",
        "glm-4.7-flash",
    ))
    disabled = manager._run_environment(ConsoleRunSpec(
        "miniwob-60-17",
        "glm-4.1v-thinking-flashx",
        "disabled",
        action_wire_capability="native_single_tool",
    ))

    assert enabled["LLM_ZHIPU_MODEL"] == "glm-4.6"
    assert enabled["LLM_ACTION_POLICY_WIRE_CAPABILITY"] == "native_single_tool"
    assert enabled["LLM_GOAL_COMPILER_MODEL"] == "glm-4.7-flash"
    assert disabled["LLM_ACTION_POLICY_WIRE_CAPABILITY"] == "native_single_tool"
    assert disabled["LLM_GOAL_COMPILER_MODE"] == "disabled"
    assert "LLM_GOAL_COMPILER_MODEL" not in disabled


def test_start_invokes_formal_case_runner_with_argv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    manifest: MiniWobBreadthManifest,
) -> None:
    captured: dict[str, object] = {}

    def fake_popen(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        return _Process()

    monkeypatch.setattr("affordance_runtime.benchmarks.console.server.subprocess.Popen", fake_popen)
    manager = _manager(tmp_path, manifest)
    run = manager.start(ConsoleRunSpec(
        "miniwob-60-17",
        "glm-4.6",
        "disabled",
        profile="CONSOLE_TEST",
    ))

    command = captured["command"]
    assert command[:4] == (
        "/fixed/python",
        "-m",
        "affordance_runtime.benchmarks.external_breadth.cli",
        "run-case",
    )
    assert "miniwob-60-17" in command
    assert str(run.evidence_dir) in command
    assert "shell" not in captured["kwargs"]
    with pytest.raises(RuntimeError, match="active"):
        manager.start(ConsoleRunSpec("miniwob-60-17", "glm-4.6", "disabled"))


def test_events_are_read_incrementally_from_append_only_trace(
    tmp_path: Path,
    manifest: MiniWobBreadthManifest,
) -> None:
    manager = _manager(tmp_path, manifest)
    spec = ConsoleRunSpec("miniwob-60-17", "glm-4.6", "disabled")
    evidence_dir = tmp_path / "evidence"
    trace_dir = evidence_dir / "traces" / spec.case_id
    trace_dir.mkdir(parents=True)
    (trace_dir / "trace.jsonl").write_text(
        '{"event":"run_started","sequence":1}\n'
        '{"event":"model_turn","sequence":2}\n'
        '{"event":',
        encoding="utf-8",
    )
    run = ConsoleRun("run-1", spec, evidence_dir, ("formal",), "2026-08-17T00:00:00+00:00", _Process(0))
    manager._runs[run.run_id] = run

    payload = manager.events(run.run_id, after=1)

    assert payload["events"] == [{"event": "model_turn", "sequence": 2}]
    assert payload["next_cursor"] == 2

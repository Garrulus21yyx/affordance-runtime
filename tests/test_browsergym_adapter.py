import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence, TypeVar

import pytest
from pydantic import BaseModel

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.benchmarks.browsergym import (
    BROWSERGYM_MINIWOB_COMMIT,
    BROWSERGYM_VERSION,
    BrowserGymAction,
    BrowserGymEpisodeResult,
    BrowserGymPolicyRequest,
    GeneralistBrowserGymContractBuilder,
    _accessibility_tree_text,
    _browsergym_model_timeout_s,
    _close_quietly,
    _load_browsergym_checkpoints,
    _prepare_browsergym_checkpoint_metadata,
    _write_browsergym_checkpoint,
    browsergym_profile,
    run_browsergym_episode,
    run_browsergym_generalist_episode,
    write_browsergym_report,
)
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation
from affordance_runtime.model_port import ModelCallRecord, ModelConfig, ModelMessage
from affordance_runtime.planning import PlannerActionKind, PlannerProposal
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec

T = TypeVar("T", bound=BaseModel)


class FakeBrowserGymPage:
    url = "http://miniwob/click-button.html"

    def __init__(self) -> None:
        self.done = False

    def content(self) -> str:
        status = "done" if self.done else "pending"
        return f'<html><body><button bid="target">Target</button><p>{status}</p></body></html>'

    def screenshot(self, **kwargs: Any) -> bytes:
        payload = b"fake-png"
        if kwargs.get("path"):
            Path(kwargs["path"]).write_bytes(payload)
        return payload

    def wait_for_load_state(self, state: str = "load", **kwargs: Any) -> None:
        del state, kwargs


class FakeBrowserGymEnvironment:
    def __init__(self) -> None:
        self.page = FakeBrowserGymPage()
        self.closed = False

    @property
    def unwrapped(self) -> "FakeBrowserGymEnvironment":
        return self

    def reset(self, *, seed: int) -> tuple[dict[str, Any], dict[str, Any]]:
        assert seed == 4
        return {"goal": "Click the target", "last_action_error": ""}, {}

    def step(self, action: str) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        assert action == "click('target')"
        self.page.done = True
        return {"goal": "Click the target", "last_action_error": ""}, 1.0, True, False, {
            "task_info": {"RAW_REWARD_GLOBAL": 1}
        }

    def close(self) -> None:
        self.closed = True


class OneClickPolicy:
    def __init__(self) -> None:
        self.closed = False

    def propose(self, request: BrowserGymPolicyRequest) -> BrowserGymAction | None:
        assert request.goal == "Click the target"
        assert request.affordances[0]["locator"]["selector"] == "[bid='target']"
        assert request.affordances[0]["locator"]["bid"] == "target"
        return BrowserGymAction("click", {"bid": "target"})

    def close(self) -> None:
        self.closed = True


@dataclass
class GeneralistClickModel:
    provider: str = "fixed"
    model: str = "fixed-generalist"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None
    calls: int = 0

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del config
        context = json.loads(messages[-1].content)
        if self.calls == 0:
            payload = PlannerProposal(
                proposal_id="generalist-click",
                based_on_task_revision=context["task_revision"],
                based_on_state_version=context["state_version"],
                snapshot_id=context["snapshot_id"],
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=context["affordances"][0]["id"],
                expected_effects=("target clicked",),
            ).model_dump(mode="json")
        else:
            payload = PlannerProposal(
                proposal_id="generalist-finish",
                based_on_task_revision=context["task_revision"],
                based_on_state_version=context["state_version"],
                snapshot_id=context["snapshot_id"],
                action_kind=PlannerActionKind.FINISH,
                done=True,
                result={"official_success": True, "official_reward": 1.0},
            ).model_dump(mode="json")
        self.calls += 1
        return output_schema.model_validate(payload)


class UnsupportedPolicy(OneClickPolicy):
    def propose(self, request: BrowserGymPolicyRequest) -> BrowserGymAction:
        del request
        return BrowserGymAction("page.evaluate", {"code": "danger"})


class UnsupportedSemanticPolicy(OneClickPolicy):
    def propose(self, request: BrowserGymPolicyRequest) -> BrowserGymAction:
        del request
        return BrowserGymAction("scroll", {"delta_x": 0, "delta_y": 10})


def test_typed_browsergym_action_rejects_code_and_unknown_arguments() -> None:
    assert BrowserGymAction("fill", {"bid": "field", "value": "hello"}).render() == "fill('field', 'hello')"
    with pytest.raises(ValueError, match="unsupported BrowserGym action"):
        BrowserGymAction("page.evaluate", {"code": "danger"}).render()
    with pytest.raises(ValueError, match="unsupported arguments"):
        BrowserGymAction("click", {"bid": "target", "code": "danger"}).render()
    with pytest.raises(ValueError, match="expected string"):
        BrowserGymAction("press", {"bid": "target", "key_comb": ["ArrowDown"]}).render()
    with pytest.raises(ValueError, match="expected number"):
        BrowserGymAction("scroll", {"delta_x": "0", "delta_y": 10}).render()


def test_accessibility_tree_fallback_preserves_role_name_and_bid() -> None:
    text = _accessibility_tree_text(
        {
            "axtree_object": {
                "nodes": [
                    {
                        "nodeId": "1",
                        "ignored": False,
                        "role": {"value": "checkbox"},
                        "name": {"value": "Third choice"},
                        "browsergym_id": "23",
                    }
                ]
            }
        }
    )
    assert "checkbox" in text
    assert "Third choice" in text
    assert "23" in text


def test_browsergym_episode_traverses_full_coordinator_and_official_grade(tmp_path: Path) -> None:
    environment = FakeBrowserGymEnvironment()
    policy = OneClickPolicy()
    result = run_browsergym_episode(
        environment,
        policy,
        task_id="click-button",
        seed=4,
        artifact_root=tmp_path,
    )

    assert result.runtime_status == "done"
    assert result.official_success is True
    assert result.official_reward == 1.0
    assert result.action_families == ["click"]
    assert result.unsupported_actions == []
    assert result.policy_stopped is False
    assert environment.closed and policy.closed
    events = [json.loads(line)["event_type"] for line in Path(result.trace_path).read_text().splitlines()]
    assert events == [
        "TaskCreated",
        "ObservationCaptured",
        "PlanProposed",
        "PlannerProposalProduced",
        "ContractBuilt",
        "PreflightObservationCaptured",
        "PreflightPassed",
        "ActionStarted",
        "ActionCompleted",
        "PostActionObservationCaptured",
        "PostconditionPassed",
        "ObservationCaptured",
        "PlanProposed",
        "PlannerProposalProduced",
        "TaskCompleted",
    ]


def test_generalist_planner_port_runs_browsergym_without_external_action_policy(tmp_path: Path) -> None:
    environment = FakeBrowserGymEnvironment()
    model = GeneralistClickModel()

    result = run_browsergym_generalist_episode(
        environment,
        model,
        task_id="click-button",
        seed=4,
        artifact_root=tmp_path,
    )

    assert result.runtime_status == "done"
    assert result.official_success is True
    assert result.action_families == ["click"]
    assert model.calls == 1
    events = [json.loads(line)["event_type"] for line in Path(result.trace_path).read_text().splitlines()]
    assert "PlannerContextBuilt" in events
    assert "PlannerProposalProduced" in events
    assert "ContractBuilt" in events


def test_generalist_browsergym_adapter_binds_native_option_activation_as_select() -> None:
    model = DomAdapter().transduce(
        '<select bid="select-bid"><option bid="option-bid" value="earth">Earth</option></select>',
        environment_revision="rev-1",
        snapshot_id="snap-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "rev-1", snapshot_id="snap-1", page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Choose Earth")
    state.remember_observation(observation)
    task = TaskSpec(
        task_id="task-1", revision=1, objective="Choose Earth", operation_class=OperationClass.READ_ONLY,
        targets=("select",), success_criteria=("Earth is selected",), source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="option", based_on_task_revision=1, based_on_state_version=state.version,
        snapshot_id="snap-1", action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id="dom_option_1",
    )

    contract = GeneralistBrowserGymContractBuilder().build(
        proposal, task, state, BrowserSnapshot(observation, model)
    )

    assert contract.action == "select_option"
    assert contract.parameters["action"] == {
        "name": "select_option", "arguments": {"bid": "select-bid", "options": "earth"}
    }


def test_generalist_browsergym_adapter_binds_semantic_key_press() -> None:
    model = DomAdapter().transduce(
        '<span bid="slider" class="ui-slider-handle" tabindex="0"></span>',
        environment_revision="rev-1",
        snapshot_id="snap-1",
        ttl_ms=60_000,
    )
    observation = Observation(
        "rev-1", snapshot_id="snap-1", page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = StateKernel("task-1", "Increase slider")
    state.remember_observation(observation)
    task = TaskSpec(
        task_id="task-1", revision=1, objective="Increase slider", operation_class=OperationClass.READ_ONLY,
        targets=("slider",), success_criteria=("slider increased",), source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="press", based_on_task_revision=1, based_on_state_version=state.version,
        snapshot_id="snap-1", action_kind=PlannerActionKind.PRESS_KEY,
        target_affordance_id="dom_span_1", parameters={"key": "ArrowRight"},
    )

    contract = GeneralistBrowserGymContractBuilder().build(
        proposal, task, state, BrowserSnapshot(observation, model)
    )

    assert contract.action == "press"
    assert contract.parameters["action"] == {
        "name": "press", "arguments": {"bid": "slider", "key_comb": "ArrowRight"}
    }


def test_browsergym_profiles_and_report_expose_coverage_without_silent_omission(tmp_path: Path) -> None:
    tasks = tuple(f"task-{index:02d}" for index in range(35))
    nightly_tasks, nightly_seeds = browsergym_profile(tasks, "nightly")
    assert len(nightly_tasks) == 30
    assert nightly_seeds == tuple(range(10))
    release_tasks, release_seeds = browsergym_profile(tasks, "release")
    assert release_tasks == tasks
    assert release_seeds == tuple(range(5))

    report = write_browsergym_report(
        tmp_path,
        profile="nightly",
        registered_tasks=tasks,
        selected_tasks=nightly_tasks,
        seeds=(0,),
        episodes=[],
    )
    assert report["browsergym_version"] == BROWSERGYM_VERSION
    assert report["miniwob_commit"] == BROWSERGYM_MINIWOB_COMMIT
    assert report["expected_episode_count"] == 30
    assert report["missing_episode_count"] == 30
    assert len(report["missing_episode_ids"]) == 30
    assert report["acceptance_errors"] == ["missing episodes: 30"]
    assert report["runtime_error_counts"] == {}
    assert report["official_track"] is True
    assert report["fault_injection"] is False
    assert _browsergym_model_timeout_s(120) == 24.0
    assert _browsergym_model_timeout_s(600) == 30.0


def test_browsergym_episode_reports_unsupported_policy_action(tmp_path: Path) -> None:
    result = run_browsergym_episode(
        FakeBrowserGymEnvironment(),
        UnsupportedPolicy(),
        task_id="click-button",
        seed=4,
        artifact_root=tmp_path,
    )
    assert result.runtime_status == "failed"
    assert result.unsupported_actions == ["page.evaluate"]


def test_browsergym_episode_reports_action_outside_semantic_vocabulary(tmp_path: Path) -> None:
    result = run_browsergym_episode(
        FakeBrowserGymEnvironment(),
        UnsupportedSemanticPolicy(),
        task_id="click-button",
        seed=4,
        artifact_root=tmp_path,
    )
    assert result.runtime_status == "failed"
    assert result.unsupported_actions == ["scroll"]


class StoppedPolicy(OneClickPolicy):
    def propose(self, request: BrowserGymPolicyRequest) -> None:
        del request
        return None


def test_browsergym_report_counts_early_policy_stop_as_runtime_failure(tmp_path: Path) -> None:
    result = run_browsergym_episode(
        FakeBrowserGymEnvironment(),
        StoppedPolicy(),
        task_id="click-button",
        seed=4,
        artifact_root=tmp_path / "artifacts",
    )
    report = write_browsergym_report(
        tmp_path / "report",
        profile="pr",
        registered_tasks=("click-button",),
        selected_tasks=("click-button",),
        seeds=(4,),
        episodes=(result,),
    )
    assert result.policy_stopped is True
    assert report["runtime_failure_count"] == 1
    assert report["runtime_error_counts"] == {"done": 1}
    assert report["acceptance_errors"] == ["policy stopped: click-button:seed-4"]


def test_browsergym_generalist_episode_checkpoints_are_atomic_and_resume_only_expected(tmp_path: Path) -> None:
    episode = BrowserGymEpisodeResult(
        task_id="click-button", seed=4, runtime_status="done", official_success=True,
        official_reward=1.0, terminated=True, truncated=False, action_count=1,
        action_families=["click"], unsupported_actions=[], runtime_error="", policy_stopped=False,
        trace_path="artifact/events.jsonl",
    )
    _write_browsergym_checkpoint(tmp_path, episode)
    ignored = BrowserGymEpisodeResult(
        task_id="other", seed=0, runtime_status="done", official_success=True,
        official_reward=1.0, terminated=True, truncated=False, action_count=1,
        action_families=["click"], unsupported_actions=[], runtime_error="", policy_stopped=False,
        trace_path="artifact/ignored.jsonl",
    )
    _write_browsergym_checkpoint(tmp_path, ignored)

    checkpoints = _load_browsergym_checkpoints(tmp_path, {("click-button", 4)})

    assert checkpoints == {("click-button", 4): episode}
    assert not list(tmp_path.glob("*.tmp"))


def test_browsergym_checkpoint_metadata_rejects_mismatched_resume(tmp_path: Path) -> None:
    first = {"schema_version": "v1", "model": "first"}
    _prepare_browsergym_checkpoint_metadata(tmp_path, first, resume=False)
    _prepare_browsergym_checkpoint_metadata(tmp_path, first, resume=True)

    with pytest.raises(ValueError, match="metadata does not match"):
        _prepare_browsergym_checkpoint_metadata(tmp_path, {"schema_version": "v1", "model": "second"}, resume=True)


def test_browsergym_checkpoint_loader_ignores_matrix_metadata(tmp_path: Path) -> None:
    _prepare_browsergym_checkpoint_metadata(tmp_path, {"schema_version": "v1"}, resume=False)

    assert _load_browsergym_checkpoints(tmp_path, {("click-button", 0)}) == {}


def test_browsergym_cleanup_does_not_replace_a_prior_failure() -> None:
    class BrokenClose:
        def close(self) -> None:
            raise RuntimeError("already disposed")

    _close_quietly(BrokenClose())

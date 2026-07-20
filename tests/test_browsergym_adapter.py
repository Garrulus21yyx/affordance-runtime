import json
from pathlib import Path
from typing import Any

import pytest

from affordance_runtime.benchmarks.browsergym import (
    BROWSERGYM_MINIWOB_COMMIT,
    BROWSERGYM_VERSION,
    BrowserGymAction,
    BrowserGymPolicyRequest,
    _accessibility_tree_text,
    browsergym_profile,
    run_browsergym_episode,
    write_browsergym_report,
)


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


class UnsupportedPolicy(OneClickPolicy):
    def propose(self, request: BrowserGymPolicyRequest) -> BrowserGymAction:
        del request
        return BrowserGymAction("page.evaluate", {"code": "danger"})


class UnsupportedSemanticPolicy(OneClickPolicy):
    def propose(self, request: BrowserGymPolicyRequest) -> BrowserGymAction:
        del request
        return BrowserGymAction("press", {"bid": "target", "key_comb": "Enter"})


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
    assert len(report["acceptance_errors"]) == 30
    assert report["official_track"] is True
    assert report["fault_injection"] is False


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
    assert result.unsupported_actions == ["press"]


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
    assert report["acceptance_errors"] == ["policy stopped: click-button:seed-4"]

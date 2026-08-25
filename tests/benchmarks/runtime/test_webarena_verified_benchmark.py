import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from affordance_runtime.actions import ActionSpaceBuilder
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.agent.decisions import FinalResponse
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.agent.run_state import RunStatus
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.webarena_verified import (
    WA_HARD_SUBSET_SHA256,
    WA_W1_SMOKE_CASES,
    WA_W2_COHORT_CASES,
    WebArenaVerifiedFinalResponseCodec,
    _capability_census,
    _private_leak_markers,
    _private_runtime_strings,
    _transition_delivery_diagnostic,
    _w1b_cost_errors,
    evaluate_webarena_verified_manifest,
    inspect_webarena_verified_w0_readiness,
    load_webarena_verified_tasks,
    open_webarena_verified_case,
    select_stratified_webarena_subset,
    webarena_gym_task_id,
    write_webarena_verified_subset,
    write_webarena_verified_w0_manifest,
)
from affordance_runtime.goals import NotRequiredGoalCompiler
from tests.support.agent.core_loop_support import (
    SharedActionOutcomeProjector,
    SharedTaskEvaluator,
    shared_task,
    shared_world,
)
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    FakeBrowserGym,
    ax_node,
    raw_observation,
)


@dataclass
class _FinalResponsePolicy:
    content: str

    async def decide(self, context):
        return FinalResponse(context.context_id, self.content)


def _dataset(path: Path, *, count: int = 36) -> Path:
    sites = ("shopping", "reddit", "gitlab")
    payload = [
        {
            "task_id": index,
            "sites": [sites[index % len(sites)]],
            "intent_template_id": 100 + index,
            "revision": 1,
        }
        for index in range(count)
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_w1b_world_capability_census_reports_t1_browsergym_support() -> None:
    context = SimpleNamespace(
        actions=SimpleNamespace(
            options=(
                SimpleNamespace(semantic_action="scroll"),
                SimpleNamespace(semantic_action="press_key"),
            ),
            has_more=False,
        )
    )
    catalog = SimpleNamespace(
        specs=(
            SimpleNamespace(name="scroll"),
            SimpleNamespace(name="press_key"),
        )
    )

    census = {item["semantic_action"]: item for item in _capability_census(context, catalog)}

    assert census["scroll"]["registry_defined"] is True
    assert census["scroll"]["adapter_supported"] is True
    assert census["scroll"]["currently_eligible"] == 1
    assert census["scroll"]["model_exposed"] is True
    assert census["press_key"]["adapter_supported"] is True
    assert census["press_key"]["currently_eligible"] == 1
    assert census["press_key"]["model_exposed"] is True
    assert census["hover"]["registry_defined"] is True
    assert census["hover"]["adapter_supported"] is False
    assert census["hover"]["absence_reason"] == "adapter_not_supported"


def test_w1b_cost_gate_treats_component_breakdowns_as_diagnostics_only() -> None:
    within_target = _w1b_cost_errors(
        {
            "estimated_input_tokens": 12_000,
            "output_reserve_tokens": 4_096,
            "complete_request_tokens": 16_096,
            # Component breakdowns remain observable but are not independent
            # readiness budgets after the complete Envelope is admitted.
            "history_tokens": 1_501,
            "tool_schema_tokens": 2_103,
            # Removed ghost fields cannot restore a cross-coordinate comparison.
            "full_candidate_tokens": 1,
            "lens_candidate_tokens": 99_999,
            "prefit_estimated_total_tokens": 99_999,
        }
    )
    over_target = _w1b_cost_errors(
        {
            "estimated_input_tokens": 12_001,
            "output_reserve_tokens": 4_096,
            "complete_request_tokens": 16_097,
            "history_tokens": 0,
            "tool_schema_tokens": 0,
        }
    )

    assert within_target == ()
    assert over_target == ("cost:new_page_over_12k",)


def test_webarena_final_response_codec_delegates_to_pinned_upstream_model() -> None:
    pytest.importorskip("webarena_verified")
    codec = WebArenaVerifiedFinalResponseCodec()

    canonical = codec.normalize(
        json.dumps(
            {
                "task_type": "retrieve",
                "status": "success",
                "retrieved_data": [{"airport": "PIT"}],
                "error_details": None,
            }
        )
    )

    assert json.loads(canonical) == {
        "task_type": "RETRIEVE",
        "status": "SUCCESS",
        "retrieved_data": [{"airport": "PIT"}],
        "error_details": None,
    }


def test_webarena_final_response_codec_rejects_non_upstream_response() -> None:
    pytest.importorskip("webarena_verified")

    with pytest.raises(ValueError):
        WebArenaVerifiedFinalResponseCodec().normalize('{"status":"SUCCESS"}')


def test_webarena_final_response_is_stop_payload_not_a_world_requested_output() -> None:
    pytest.importorskip("webarena_verified")
    final_response = json.dumps(
        {
            "task_type": "RETRIEVE",
            "status": "SUCCESS",
            "retrieved_data": ["Dibbins", "Catso", "Anglebert Dinkherhump", "Michelle Davis"],
            "error_details": None,
        }
    )
    raw = raw_observation(
        ax_node("button", "button", "Reviews"),
        goal="Return the requested names using the official FinalAgentResponse format.",
    )
    browsergym = FakeBrowserGym(raw)
    environment, task, evaluator = open_webarena_verified_case(
        WA_W1_SMOKE_CASES[0],
        gym_factory=lambda *_args, **_kwargs: browsergym,
    )
    runtime = TargetRuntime(
        AgentDecisionPorts(_FinalResponsePolicy(final_response)),
        SharedActionOutcomeProjector(),
        evaluator,
        goal_compiler=NotRequiredGoalCompiler("webarena_final_response_test"),
    )

    try:
        state = asyncio.run(runtime.run_task(environment, task))
    finally:
        asyncio.run(environment.close())

    assert task.requested_outputs == ()
    assert state.status is RunStatus.DONE
    assert state.current_task_evaluation is not None
    assert state.current_task_evaluation.outputs == ()
    assert browsergym.final_messages == [WebArenaVerifiedFinalResponseCodec().normalize(final_response)]
    assert state.finalization is not None
    assert state.finalization.stop_send_count == 1
    assert state.finalization.post_stop_capture_count == 1
    assert state.finalization.native_evaluator_count == 1


def test_w1b_world_transition_diagnostic_matches_independent_snapshot_diff() -> None:
    task = shared_task()
    world = shared_world("w1b-transition", False)
    context = ContextBuilder().build(
        task,
        world,
        ActionSpaceBuilder().build(task, world),
        asyncio.run(SharedTaskEvaluator().evaluate(task, world)),
    )

    diagnostic = _transition_delivery_diagnostic(task, world, context)

    assert diagnostic["provider_attempts"] == 0
    assert diagnostic["agent_loop_profile"] == {
        "max_consecutive_observation_only": 8,
        "max_recovery_retries": 1,
    }
    assert diagnostic["serialized_snapshot_matches_delta"] is True
    assert diagnostic["fresh_world_is_current"] is True
    assert diagnostic["single_current_world_projection"] is True
    assert diagnostic["changed_value_in_authoritative_world"] is True
    assert diagnostic["gui_action_did_not_create_delivery_state"] is True
    assert diagnostic["local_delivery_does_not_reproject_gui_effect"] is True
    assert diagnostic["step_delta_shared"] is True
    assert diagnostic["workspace_reduced"] is True
    assert diagnostic["monitor_recommendation"] == "continue"
    assert diagnostic["local_operation"] == "search_page_content"
    assert diagnostic["local_monitor_recommendation"] == "continue"
    assert diagnostic["post_transition_request_admitted"] is True
    assert diagnostic["post_local_request_admitted"] is True
    assert diagnostic["post_transition_privacy_checked"] is True
    assert diagnostic["post_local_privacy_checked"] is True
    assert diagnostic["acceptance_errors"] == ()


@pytest.mark.parametrize(
    "leak",
    (
        '"private_cursor":"cursor:17"',
        '"observation_id":"private"',
        '"capture_epoch":"private"',
        '"omitted_count":84',
        '"raw_delta_lineage":"private"',
    ),
)
def test_w1b_privacy_gate_rejects_prohibited_serialization_fields(leak: str) -> None:
    catalog = SimpleNamespace(specs=())
    admitted = SimpleNamespace(
        envelope=SimpleNamespace(physical_content=lambda: {"messages": (leak,)}),
    )

    assert _private_leak_markers(leak, catalog, admitted, ())


def test_w1b_privacy_gate_rejects_exact_runtime_lineage_values() -> None:
    world = shared_world("private-lineage-sentinel", False)
    private_values = _private_runtime_strings(world)
    leaked = next(value for value in private_values if len(value) >= 4)
    catalog = SimpleNamespace(specs=())
    admitted = SimpleNamespace(
        envelope=SimpleNamespace(physical_content=lambda: {"messages": (leaked,)}),
    )

    assert _private_leak_markers(leaked, catalog, admitted, private_values) == (
        "private_binding_value",
    )


def test_w0_manifest_freezes_public_smoke_and_proof_identity_without_oracles(tmp_path: Path) -> None:
    env = {
        "WA_SHOPPING_URL": "https://user:pass@example.test/shopping?token=secret",
        "WA_SHOPPING_ADMIN_URL": "https://admin.example.test",
        "WA_REDDIT_URL": "https://reddit.example.test",
        "WA_GITLAB_URL": "https://gitlab.example.test",
        "WA_MAP_URL": "https://map.example.test",
        "WA_WIKIPEDIA_URL": "https://wiki.example.test",
        "WA_DEPLOYMENT_IMAGE_DIGEST": "sha256:" + "a" * 64,
        "WA_AUTH_TOKEN": "must-not-leak",
    }

    manifest = write_webarena_verified_w0_manifest(tmp_path / "w0.json", timeout_s=180.0, environment=env)

    assert manifest["schema_version"] == "webarena-verified-target-loop-manifest.v1"
    assert manifest["hard_subset_sha256"] == f"sha256:{WA_HARD_SUBSET_SHA256}"
    assert [case["task_id"] for case in manifest["smoke_cases"]] == [0, 7, 21, 27, 44, 266]
    assert [case["task_id"] for case in manifest["proof_cohort_cases"]] == [
        267, 97, 265, 268, 740, 759, 424, 426, 681, 672, 556, 554,
    ]
    assert manifest["timeout_frozen"] is True
    assert manifest["site_environment_frozen"] is True
    assert "final_output_id" not in manifest
    serialized = json.dumps(manifest)
    assert "must-not-leak" not in serialized
    assert "user:pass" not in serialized
    assert "token=secret" not in serialized
    assert "expected_answer" not in serialized
    assert "evaluator" not in serialized


def test_w0_readiness_reports_environment_blockers_without_agent_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Completed:
        returncode = 0
        stderr = ""
        stdout = json.dumps(
            {
                "packages": {
                    "playwright": {"installed": True, "version": "1.44.0"},
                    "browsergym-webarena": {"installed": True, "version": "0.14.3"},
                    "browsergym-webarena-verified": {"installed": False},
                    "nltk": {"installed": True, "version": "3.10.3"},
                    "webarena-verified": {"installed": False},
                },
                "registration": {"imported": False, "missing_task_ids": [WA_W1_SMOKE_CASES[0].gym_id]},
                "sites": [],
                "exercise": {"attempted": True, "reset": "not_attempted", "evaluator": "not_attempted"},
            }
        )

    calls: list[dict[str, object]] = []

    def fake_run(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return Completed()

    monkeypatch.setattr("affordance_runtime.benchmarks.webarena_verified.subprocess.run", fake_run)

    report = inspect_webarena_verified_w0_readiness(runtime_python=tmp_path / "python", output_path=tmp_path / "r.json")

    assert report["ready"] is False
    assert report["failure_origin"] == "environment"
    assert "environment:browsergym-webarena-verified_missing" in report["acceptance_errors"]
    assert "environment:webarena-verified_missing" in report["acceptance_errors"]
    assert any(error.startswith("environment:wa_sites_missing:") for error in report["acceptance_errors"])
    assert calls[0]["command"][:2] == [str(tmp_path / "python"), "-c"]
    assert json.loads(calls[0]["input"])["probe_task_id"] == WA_W1_SMOKE_CASES[0].gym_id
    assert (tmp_path / "r.json").exists()


def test_w0_readiness_accepts_registered_sites_reset_and_evaluator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sites = [
        {"env": f"WA_{name}_URL", "redacted_url": f"https://{name}.example.test/", "health": {"status": "ok"}}
        for name in ("SHOPPING", "SHOPPING_ADMIN", "REDDIT", "GITLAB", "MAP", "WIKIPEDIA")
    ]

    class Completed:
        returncode = 0
        stderr = ""
        stdout = json.dumps(
            {
                "packages": {
                    "playwright": {"installed": True, "version": "1.44.0"},
                    "browsergym-webarena": {"installed": True, "version": "0+pin"},
                    "browsergym-webarena-verified": {"installed": True, "version": "0+pin"},
                    "nltk": {"installed": True, "version": "3.10.3"},
                    "webarena-verified": {"installed": True, "version": "0+pin"},
                },
                "registration": {
                    "imported": True,
                    "missing_task_ids": [],
                    "registered_task_ids": [case.gym_id for case in (*WA_W1_SMOKE_CASES, *WA_W2_COHORT_CASES)],
                },
                "sites": sites,
                "exercise": {
                    "attempted": True,
                    "reset": {"status": "ok", "goal_present": True},
                    "evaluator": {"status": "ok", "terminated": True, "reward_type": "float"},
                },
            }
        )

    monkeypatch.setattr(
        "affordance_runtime.benchmarks.webarena_verified.subprocess.run",
        lambda *_args, **_kwargs: Completed(),
    )

    report = inspect_webarena_verified_w0_readiness(runtime_python=tmp_path / "python")

    assert report["ready"] is True
    assert report["acceptance_errors"] == []
    assert report["failure_origin"] == "none"


def test_webarena_gym_task_id_uses_official_browsergym_registration_shape() -> None:
    assert webarena_gym_task_id(WA_W1_SMOKE_CASES[0]) == "browsergym/webarena_verified.279.0.2"
    assert WA_W2_COHORT_CASES[0].gym_id == "browsergym/webarena_verified.85.267.4"


def test_webarena_manifest_is_stratified_and_digest_bound(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "dataset.json")

    manifest = write_webarena_verified_subset(dataset, tmp_path / "subset.json", count=30)

    assert manifest["selected_task_count"] == 30
    assert manifest["site_distribution"] == {"gitlab": 10, "reddit": 10, "shopping": 10}
    assert manifest["task_ids"][:6] == [2, 1, 0, 5, 4, 3]
    assert manifest["source_dataset_sha256"].startswith("sha256:")
    assert manifest["official_score_claimed"] is False


def test_webarena_subset_requires_planned_range_and_enough_tasks(tmp_path: Path) -> None:
    tasks = load_webarena_verified_tasks(_dataset(tmp_path / "dataset.json", count=30))

    with pytest.raises(ValueError, match="between 30 and 50"):
        select_stratified_webarena_subset(tasks, count=29)
    with pytest.raises(ValueError, match="fewer than 31"):
        select_stratified_webarena_subset(tasks, count=31)


def test_webarena_dataset_rejects_duplicate_task_ids(tmp_path: Path) -> None:
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps(
            [
                {"task_id": 1, "sites": ["shopping"], "intent_template_id": 1, "revision": 1},
                {"task_id": 1, "sites": ["reddit"], "intent_template_id": 2, "revision": 1},
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate WebArena-Verified task id"):
        load_webarena_verified_tasks(path)


def test_webarena_evaluation_delegates_to_upstream_and_preserves_results(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "webarena-verified-subset-v1",
                "source_dataset_sha256": f"sha256:{'a' * 64}",
                "selected_task_count": 2,
                "task_ids": [1, 2],
            }
        ),
        encoding="utf-8",
    )
    logs = tmp_path / "logs"
    for task_id, score in ((1, 1.0), (2, 0.0)):
        task_dir = logs / str(task_id)
        task_dir.mkdir(parents=True)
        (task_dir / "eval_result.json").write_text(
            json.dumps({"task_id": task_id, "score": score, "status": "success"}), encoding="utf-8"
        )
    commands: list[list[str]] = []

    class Completed:
        returncode = 0

    def runner(command: list[str], **kwargs: object) -> Completed:
        commands.append(command)
        assert kwargs == {"check": False, "capture_output": True, "text": True}
        return Completed()

    report = evaluate_webarena_verified_manifest(
        manifest, logs, config_path=tmp_path / "config.json", runner=runner
    )

    assert commands == [
        [
            "webarena-verified", "eval-tasks", "--task-ids", "1,2", "--output-dir", str(logs),
            "--config", str(tmp_path / "config.json"),
        ]
    ]
    assert report["mean_official_score"] == 0.5
    assert report["upstream_results"]["1"]["score"] == 1.0
    assert report["upstream_result_sha256"]["1"].startswith("sha256:")
    assert report["manifest_sha256"].startswith("sha256:")
    assert report["official_score_claimed"] is False
    assert report["acceptance_errors"] == []


def test_webarena_evaluation_fails_closed_when_upstream_results_are_missing(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "webarena-verified-subset-v1",
                "source_dataset_sha256": f"sha256:{'b' * 64}",
                "task_ids": [1],
            }
        )
    )

    class Completed:
        returncode = 0

    report = evaluate_webarena_verified_manifest(
        manifest, tmp_path / "logs", runner=lambda *_args, **_kwargs: Completed()
    )

    assert report["missing_result_ids"] == [1]
    assert report["mean_official_score"] is None
    assert report["acceptance_errors"] == ["missing official results: 1"]


def test_webarena_evaluation_rejects_duplicate_or_count_mismatched_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    common = {
        "schema_version": "webarena-verified-subset-v1",
        "source_dataset_sha256": f"sha256:{'c' * 64}",
    }
    manifest.write_text(json.dumps({**common, "task_ids": [1, 1]}), encoding="utf-8")
    with pytest.raises(ValueError, match="must be unique"):
        evaluate_webarena_verified_manifest(manifest, tmp_path / "logs")

    manifest.write_text(
        json.dumps({**common, "selected_task_count": 3, "task_ids": [1, 2]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not match"):
        evaluate_webarena_verified_manifest(manifest, tmp_path / "logs")


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"task_id": 99, "score": 1.0}, "task_id_mismatch"),
        ({"task_id": 1, "score": True}, "score_not_numeric"),
        ({"task_id": 1, "score": 1.5}, "score_out_of_range"),
    ],
)
def test_webarena_evaluation_fails_closed_for_invalid_upstream_result(
    tmp_path: Path, payload: dict[str, object], reason: str
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "webarena-verified-subset-v1",
                "source_dataset_sha256": f"sha256:{'d' * 64}",
                "task_ids": [1],
            }
        ),
        encoding="utf-8",
    )
    result_dir = tmp_path / "logs" / "1"
    result_dir.mkdir(parents=True)
    (result_dir / "eval_result.json").write_text(json.dumps(payload), encoding="utf-8")

    class Completed:
        returncode = 0

    report = evaluate_webarena_verified_manifest(
        manifest,
        tmp_path / "logs",
        runner=lambda *_args, **_kwargs: Completed(),
    )

    assert report["evaluated_task_count"] == 0
    assert report["invalid_results"] == {"1": reason}
    assert report["mean_official_score"] is None
    assert report["acceptance_errors"] == ["invalid official results: 1"]


def test_webarena_evaluation_rejects_result_symlink_outside_log_root(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "webarena-verified-subset-v1",
                "source_dataset_sha256": f"sha256:{'e' * 64}",
                "task_ids": [1],
            }
        ),
        encoding="utf-8",
    )
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"task_id": 1, "score": 1.0}), encoding="utf-8")
    result_dir = tmp_path / "logs" / "1"
    result_dir.mkdir(parents=True)
    (result_dir / "eval_result.json").symlink_to(outside)

    class Completed:
        returncode = 0

    report = evaluate_webarena_verified_manifest(
        manifest,
        tmp_path / "logs",
        runner=lambda *_args, **_kwargs: Completed(),
    )

    assert report["invalid_results"] == {"1": "result_path_escape"}
    assert report["acceptance_errors"] == ["invalid official results: 1"]

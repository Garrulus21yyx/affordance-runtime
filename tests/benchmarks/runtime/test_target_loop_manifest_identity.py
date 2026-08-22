from dataclasses import replace
from types import SimpleNamespace

import pytest

import affordance_runtime.benchmarks.target_loop.cases as target_cases
from affordance_runtime.agent import RunStatus
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkManifest,
    MetricExpectation,
    MetricExpectationOperator,
)
from affordance_runtime.benchmarks.target_loop.manifest import get_manifest, manifest_digest
from affordance_runtime.benchmarks.webarena_verified import WA_W1_SMOKE_CASES


def test_manifest_digest_covers_profile_seed_and_expectations() -> None:
    manifest = get_manifest("internal-core", "deterministic", 7)
    expectations = tuple(
        MetricExpectation("executions", MetricExpectationOperator.MAX, 2)
        if item.metric == "executions" else item
        for item in manifest.cases[0].metric_expectations
    )
    changed_case = replace(manifest.cases[0], metric_expectations=expectations)
    changed = replace(manifest, cases=(changed_case, *manifest.cases[1:]))

    assert manifest_digest(manifest) != manifest_digest(changed)
    assert manifest_digest(manifest) != manifest_digest(replace(manifest, profile_id="other"))
    reseeded = replace(
        manifest, seed=8, cases=tuple(replace(item, seed=8) for item in manifest.cases)
    )
    assert manifest_digest(manifest) != manifest_digest(reseeded)


def test_manifest_rejects_duplicate_or_mismatched_cases() -> None:
    manifest = get_manifest("internal-core", "deterministic", 7)
    with pytest.raises(ValueError):
        BenchmarkManifest(
            manifest.schema_version, manifest.suite_id, manifest.profile_id,
            manifest.seed, (manifest.cases[0], manifest.cases[0]),
        )
    with pytest.raises(ValueError):
        replace(manifest, cases=(replace(manifest.cases[0], suite_id="wrong"),))


def test_webarena_verified_w1b_manifest_uses_one_action_policy_and_goal_compiler(monkeypatch) -> None:
    manifest = get_manifest("webarena-verified-w1b", "model-long-horizon", 20260818)

    assert manifest.suite_id == "webarena-verified-w1b"
    assert manifest.profile_id == "model-long-horizon"
    assert [case.case_id for case in manifest.cases] == [
        f"webarena-verified-w1b-task-{case.task_id}" for case in WA_W1_SMOKE_CASES
    ]
    assert all(case.expected_terminal_statuses == (RunStatus.DONE,) for case in manifest.cases)
    assert all(case.timeout_s == 900.0 for case in manifest.cases)
    assert all("planner_calls" not in case.required_measurements for case in manifest.cases)
    assert all("auditor_calls" not in case.required_measurements for case in manifest.cases)
    policy = object()
    compiler = object()
    monkeypatch.setattr(
        target_cases,
        "model_roles_from_environment",
        lambda *_args, **_kwargs: SimpleNamespace(action_policy=policy, goal_compiler=compiler),
    )
    for case in manifest.cases:
        holder = next(
            cell.cell_contents
            for cell in case.composition_factory.__closure__ or ()
            if isinstance(cell.cell_contents, dict)
        )
        holder["evaluator"] = object()
        composition = case.composition_factory(None)
        assert composition.policy is policy
        assert composition.goal_compiler is compiler
        assert not hasattr(composition, "mission_planner")

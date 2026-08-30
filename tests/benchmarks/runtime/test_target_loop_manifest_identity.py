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
from affordance_runtime.benchmarks.webarena_verified import (
    WA_W1_HELD_OUT_CASES,
    WA_W1_SMOKE_CASES,
    WA_W2_COHORT_CASES,
    WebArenaVerifiedCaseAdmission,
    WebArenaVerifiedCaseRef,
)


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
        f"webarena-verified-w1b-task-{case.task_id}"
        for case in (*WA_W1_SMOKE_CASES, *WA_W1_HELD_OUT_CASES)
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


def test_webarena_verified_w2_manifest_is_the_complete_frozen_cohort() -> None:
    manifest = get_manifest("webarena-verified-w2", "model-long-horizon", 20260818)

    assert manifest.suite_id == "webarena-verified-w2"
    assert manifest.profile_id == "model-long-horizon"
    assert [case.case_id for case in manifest.cases] == [
        f"webarena-verified-w2-task-{case.task_id}"
        for case in WA_W2_COHORT_CASES
    ]
    assert all(case.expected_terminal_statuses == (RunStatus.DONE,) for case in manifest.cases)
    assert all(case.timeout_s == 900.0 for case in manifest.cases)
    assert all(case.required_measurements == (
        "observations",
        "policy_calls",
        "provider_attempts",
        "stop_send_count",
        "post_stop_capture_count",
        "native_evaluator_count",
    ) for case in manifest.cases)
    assert manifest_digest(manifest) == "e5646d8b5ef39d06d0364dab30f1f02b6528d4b90d14a7f77b15440d54af3b2d"


def test_webarena_target_case_threads_the_manifest_owners_admission(monkeypatch) -> None:
    case_ref = WebArenaVerifiedCaseRef(545, 251, 2, ("shopping_admin",), "mutate", "diagnostic")
    admission = WebArenaVerifiedCaseAdmission("diagnostic-sample", (case_ref,))
    captured = {}

    def open_case(observed_ref, **kwargs):
        captured["case_ref"] = observed_ref
        captured["admission"] = kwargs["admission"]
        raise RuntimeError("stop after admission capture")

    monkeypatch.setattr(target_cases, "open_webarena_verified_case", open_case)
    case = target_cases._webarena_verified_case(
        case_ref,
        7,
        suite_id="webarena-diagnostic",
        description="generic admitted case",
        admission=admission,
    )

    with pytest.raises(RuntimeError, match="admission capture"):
        case.environment_factory(None)
    assert captured == {"case_ref": case_ref, "admission": admission}


def test_webarena_target_case_composes_configured_visual_roles(monkeypatch) -> None:
    case_ref = WebArenaVerifiedCaseRef(545, 251, 2, ("shopping_admin",), "mutate", "diagnostic")
    admission = WebArenaVerifiedCaseAdmission("diagnostic-sample", (case_ref,))
    visual_roles = object()
    captured = {}

    monkeypatch.setenv("LLM_VISUAL_PROFILE", "configured-visual-provider")
    monkeypatch.setattr(
        target_cases,
        "pydantic_ai_visual_roles_from_environment",
        lambda environment, *, timeout_s: (
            captured.update({"profile": environment["LLM_VISUAL_PROFILE"], "timeout_s": timeout_s})
            or visual_roles
        ),
    )

    def open_case(observed_ref, **kwargs):
        captured["case_ref"] = observed_ref
        captured["visual_roles"] = kwargs["visual_roles"]
        raise RuntimeError("stop after visual composition capture")

    monkeypatch.setattr(target_cases, "open_webarena_verified_case", open_case)
    case = target_cases._webarena_verified_case(
        case_ref,
        7,
        suite_id="webarena-diagnostic",
        description="generic configured visual case",
        admission=admission,
    )

    with pytest.raises(RuntimeError, match="visual composition capture"):
        case.environment_factory(None)

    assert captured == {
        "profile": "configured-visual-provider",
        "timeout_s": target_cases.WA_W1B_MODEL_CALL_TIMEOUT_S,
        "case_ref": case_ref,
        "visual_roles": visual_roles,
    }

from __future__ import annotations

import json
from pathlib import Path

import pytest

from affordance_runtime.benchmarks import browsergym_matrix as matrix
from affordance_runtime.benchmarks import browsergym_report as report_adapter
from affordance_runtime.benchmarks.browsergym_types import BrowserGymEpisodeResult
from affordance_runtime.evaluation_audit import EvaluationRunIdentity


def _failed_episode(*, task_id: str, actions: list[str]) -> BrowserGymEpisodeResult:
    return BrowserGymEpisodeResult(
        task_id=task_id,
        seed=0,
        runtime_status="done",
        official_success=False,
        official_reward=0.0,
        terminated=True,
        truncated=False,
        action_count=len(actions),
        action_families=actions,
        unsupported_actions=[],
        runtime_error="",
        policy_stopped=False,
        trace_path="trace.jsonl",
    )


def test_matrix_preserves_report_adapter_exports() -> None:
    assert matrix.browsergym_failure_envelope is report_adapter.browsergym_failure_envelope
    assert matrix.cluster_browsergym_failure_envelopes is report_adapter.cluster_browsergym_failure_envelopes
    assert matrix.write_browsergym_report is report_adapter.write_browsergym_report


def test_failure_family_uses_observed_capability_without_task_name_dispatch() -> None:
    envelope = report_adapter.browsergym_failure_envelope(
        _failed_episode(task_id="outside-fixed-manifest", actions=["click", "fill"])
    )

    assert envelope is not None
    assert envelope["family"] == "observed:text_entry"
    assert envelope["action_kind"] == "fill"


def test_failure_family_retains_evidence_gap_when_no_action_was_observed() -> None:
    envelope = report_adapter.browsergym_failure_envelope(
        _failed_episode(task_id="outside-fixed-manifest", actions=[])
    )

    assert envelope is not None
    assert envelope["family"] == "unresolved:no_action_evidence"


def test_declared_protocol_family_precedes_observed_action() -> None:
    envelope = report_adapter.browsergym_failure_envelope(
        _failed_episode(task_id="declared", actions=["fill"]),
        task_family_map={"declared": "controlled-family"},
    )

    assert envelope is not None
    assert envelope["family"] == "controlled-family"


def test_runtime_owner_cluster_crosses_task_families_without_erasing_family_evidence() -> None:
    first = report_adapter.browsergym_failure_envelope(
        _failed_episode(task_id="case-a", actions=["click"]),
        task_family_map={"case-a": "activate"},
    )
    second = report_adapter.browsergym_failure_envelope(
        _failed_episode(task_id="case-b", actions=["fill"]),
        task_family_map={"case-b": "text_entry"},
    )
    assert first is not None and second is not None

    assert report_adapter.cluster_browsergym_failures_by_runtime_owner((first, second)) == [
        {
            "root_layer": "EXECUTION",
            "failure_signature": "official_reward_zero",
            "families": ["activate", "text_entry"],
            "task_count": 2,
            "episode_count": 2,
            "episode_ids": ["case-a:seed-0", "case-b:seed-0"],
        }
    ]


def test_complete_report_is_repair_ready_despite_ordinary_failures(tmp_path: Path) -> None:
    runtime_failure = BrowserGymEpisodeResult(
        task_id="case-a",
        seed=0,
        runtime_status="failed",
        official_success=False,
        official_reward=0.0,
        terminated=False,
        truncated=False,
        action_count=0,
        action_families=[],
        unsupported_actions=[],
        runtime_error="execution_failed",
        policy_stopped=False,
        trace_path="trace-a.jsonl",
    )
    external_failure = _failed_episode(task_id="case-b", actions=["click"])

    report = report_adapter.write_browsergym_report(
        tmp_path,
        profile="diagnostic",
        registered_tasks=("case-a", "case-b"),
        selected_tasks=("case-a", "case-b"),
        seeds=(0,),
        episodes=(runtime_failure, external_failure),
    )

    assert report["batch_status"] == "complete"
    assert report["run_complete"] is True
    assert report["repair_selection_ready"] is True
    assert report["observed_episode_count"] == 2
    assert report["task_manifest_version"] == matrix.NIGHTLY_TASK_MANIFEST_VERSION
    assert report["task_action_families"] == {
        family: list(tasks) for family, tasks in matrix.NIGHTLY_ACTION_FAMILY_MANIFEST.items()
    }
    assert report["failed_episode_count"] == 2
    assert report["runtime_verification_outcomes"] == {"passed": 1, "failed": 1}
    assert report["external_evaluator_outcomes"] == {"passed": 0, "failed": 2}
    assert report["failure_clusters"]
    assert report["runtime_owner_failure_clusters"]
    assert report["unclustered_failure_envelope_count"] == 0


def test_partial_report_accounts_unrun_cases_and_withholds_formal_clusters(tmp_path: Path) -> None:
    episode = _failed_episode(task_id="case-a", actions=["click"])

    report = report_adapter.write_browsergym_report(
        tmp_path,
        profile="diagnostic",
        registered_tasks=("case-a", "case-b"),
        selected_tasks=("case-a", "case-b"),
        seeds=(0,),
        episodes=(episode,),
        interrupted=True,
    )

    assert report["batch_status"] == "incomplete_resumable"
    assert report["run_complete"] is False
    assert report["observed_episode_count"] == 1
    assert report["unrun_episode_count"] == 1
    assert report["invalidated_episode_count"] == 0
    assert report["repair_selection_ready"] is False
    assert report["failure_clusters"] == []
    assert report["runtime_owner_failure_clusters"] == []
    assert report["unclustered_failure_envelope_count"] == 1
    assert [item["disposition"] for item in report["evaluation_audit"]["cases"]] == [
        "observed_failed",
        "unobserved",
    ]


def test_integrity_stop_marks_partial_evidence_invalid_and_nonresumable(tmp_path: Path) -> None:
    episode = BrowserGymEpisodeResult(
        task_id="case-a",
        seed=0,
        runtime_status="failed",
        official_success=False,
        official_reward=0.0,
        terminated=False,
        truncated=False,
        action_count=0,
        action_families=[],
        unsupported_actions=[],
        runtime_error="schema validation failed",
        policy_stopped=False,
        trace_path="trace-a.jsonl",
    )
    envelope = report_adapter.browsergym_failure_envelope(episode)
    assert envelope is not None
    stop = matrix.browsergym_batch_stop("schema_incompatible")
    assert stop is not None

    report = report_adapter.write_browsergym_report(
        tmp_path,
        profile="nightly",
        registered_tasks=("case-a", "case-b"),
        selected_tasks=("case-a", "case-b"),
        seeds=(0,),
        episodes=(episode,),
        batch_stop=stop,
    )

    assert report["batch_status"] == "invalidated"
    assert report["invalidated_episode_count"] == 2
    assert report["evaluation_audit"]["resume_allowed"] is False
    assert report["failure_clusters"] == []


def test_report_publication_rejects_tampered_aggregate_or_premature_cluster(
    tmp_path: Path,
) -> None:
    report = report_adapter.write_browsergym_report(
        tmp_path / "valid",
        profile="diagnostic",
        registered_tasks=("case-a", "case-b"),
        selected_tasks=("case-a", "case-b"),
        seeds=(0,),
        episodes=(_failed_episode(task_id="case-a", actions=["click"]),),
        interrupted=True,
    )
    with pytest.raises(ValueError, match="observed_episode_count"):
        report_adapter.publish_browsergym_report(
            tmp_path / "tampered-count",
            {**report, "observed_episode_count": 2},
        )
    with pytest.raises(ValueError, match="cannot publish formal failure clusters"):
        report_adapter.publish_browsergym_report(
            tmp_path / "tampered-cluster",
            {**report, "failure_clusters": [{"root_layer": "EXECUTION"}]},
        )
    tampered_episodes = [dict(item) for item in report["episodes"]]
    tampered_episodes[0]["official_reward"] = 0.5
    with pytest.raises(ValueError, match="reward aggregate"):
        report_adapter.publish_browsergym_report(
            tmp_path / "tampered-episode",
            {**report, "episodes": tampered_episodes},
        )
    assert not (tmp_path / "tampered-count" / "browsergym-report.json").exists()
    assert not (tmp_path / "tampered-cluster" / "browsergym-report.json").exists()
    assert not (tmp_path / "tampered-episode" / "browsergym-report.json").exists()


@pytest.mark.parametrize("reward", [float("nan"), float("inf"), float("-inf")])
def test_report_rejects_nonfinite_external_result_before_publication(
    tmp_path: Path,
    reward: float,
) -> None:
    corrupt = BrowserGymEpisodeResult(
        **{
            **_failed_episode(task_id="case-a", actions=["click"]).__dict__,
            "official_reward": reward,
        }
    )

    with pytest.raises(ValueError, match="must be finite"):
        report_adapter.write_browsergym_report(
            tmp_path,
            profile="diagnostic",
            registered_tasks=("case-a",),
            selected_tasks=("case-a",),
            seeds=(0,),
            episodes=(corrupt,),
        )
    assert not (tmp_path / "browsergym-report.json").exists()


def test_episode_result_must_match_scheduled_case_before_checkpoint() -> None:
    episode = _failed_episode(task_id="case-a", actions=["click"])
    with pytest.raises(ValueError, match="scheduled case"):
        report_adapter.validate_browsergym_episode_result(
            episode,
            expected_case=("case-b", 0),
        )


def test_mixed_browser_versions_require_explicit_version_drift_invalidation(
    tmp_path: Path,
) -> None:
    first = BrowserGymEpisodeResult(
        **{
            **_failed_episode(task_id="case-a", actions=["click"]).__dict__,
            "browser_version": "chromium-1",
        }
    )
    second = BrowserGymEpisodeResult(
        **{
            **_failed_episode(task_id="case-b", actions=["click"]).__dict__,
            "browser_version": "chromium-2",
        }
    )
    with pytest.raises(ValueError, match="mixes browser versions"):
        report_adapter.write_browsergym_report(
            tmp_path / "unmarked",
            profile="nightly",
            registered_tasks=("case-a", "case-b"),
            selected_tasks=("case-a", "case-b"),
            seeds=(0,),
            episodes=(first, second),
        )

    stop = matrix.browsergym_batch_stop("version_drift")
    assert stop is not None
    report = report_adapter.write_browsergym_report(
        tmp_path / "invalidated",
        profile="nightly",
        registered_tasks=("case-a", "case-b"),
        selected_tasks=("case-a", "case-b"),
        seeds=(0,),
        episodes=(first, second),
        batch_stop=stop,
    )
    assert report["batch_status"] == "invalidated"
    assert report["observed_browser_versions"] == ["chromium-1", "chromium-2"]


@pytest.mark.parametrize(
    ("reason", "category", "invalidates", "resumable"),
    [
        ("safety_violation", "safety_authority", False, False),
        ("version_drift", "comparability", True, False),
        (
            "provider_unavailable_or_continuous_rate_limit",
            "provider_infrastructure",
            False,
            True,
        ),
        ("source_or_oracle_unavailable", "result_integrity", True, False),
        ("artifact_checkpoint_failure", "result_integrity", True, False),
        ("schema_incompatible", "result_integrity", True, False),
        ("result_accounting_failure", "result_integrity", True, False),
    ],
)
def test_adapter_batch_stop_allowlist_has_explicit_validity_and_resume_semantics(
    reason: str,
    category: str,
    invalidates: bool,
    resumable: bool,
) -> None:
    stop = matrix.browsergym_batch_stop(reason)

    assert stop is not None
    assert stop.category.value == category
    assert stop.invalidates_observed_results is invalidates
    assert stop.resume_allowed is resumable


def test_adapter_batch_stop_rejects_unreviewed_reason() -> None:
    with pytest.raises(ValueError, match="unsupported BrowserGym batch stop reason"):
        matrix.browsergym_batch_stop("ordinary_task_failure")


@pytest.mark.parametrize(
    "episode",
    [
        _failed_episode(task_id="reward-zero", actions=["click"]),
        BrowserGymEpisodeResult(
            "verification",
            0,
            "failed",
            False,
            0.0,
            True,
            False,
            1,
            ["click"],
            [],
            "verification_failed",
            False,
            "",
        ),
        BrowserGymEpisodeResult(
            "execution",
            0,
            "failed",
            False,
            0.0,
            False,
            False,
            1,
            ["click"],
            [],
            "execution_failed",
            False,
            "",
        ),
        BrowserGymEpisodeResult(
            "observation",
            0,
            "waiting_clarification",
            False,
            0.0,
            False,
            False,
            0,
            [],
            [],
            "",
            False,
            "",
            planner_affordance_count=0,
        ),
        BrowserGymEpisodeResult(
            "planning-budget",
            0,
            "failed",
            False,
            0.0,
            False,
            False,
            0,
            [],
            [],
            "model call budget exhausted",
            False,
            "",
        ),
    ],
)
def test_repeated_ordinary_case_failure_never_becomes_batch_stop(
    episode: BrowserGymEpisodeResult,
) -> None:
    envelope = report_adapter.browsergym_failure_envelope(episode)
    assert envelope is not None
    assert matrix.browsergym_batch_circuit_breaker((envelope, envelope, envelope)) == ""


def test_complete_thirty_case_conformance_matrix_reconciles_before_clustering(
    tmp_path: Path,
) -> None:
    tasks = tuple(f"opaque-case-{index:02d}" for index in range(30))
    episodes: list[BrowserGymEpisodeResult] = []
    for index, task_id in enumerate(tasks):
        if index % 5 == 0:
            episodes.append(
                BrowserGymEpisodeResult(
                    task_id,
                    0,
                    "failed",
                    False,
                    0.0,
                    False,
                    False,
                    1,
                    ["fill"],
                    [],
                    "verification_failed",
                    False,
                    f"trace-{index}.jsonl",
                )
            )
        else:
            episodes.append(
                BrowserGymEpisodeResult(
                    task_id,
                    0,
                    "done",
                    index % 3 != 0,
                    1.0 if index % 3 != 0 else 0.0,
                    True,
                    False,
                    1,
                    ["click" if index % 2 else "fill"],
                    [],
                    "",
                    False,
                    f"trace-{index}.jsonl",
                )
            )

    report = report_adapter.write_browsergym_report(
        tmp_path,
        profile="diagnostic",
        registered_tasks=tasks,
        selected_tasks=tasks,
        seeds=(0,),
        episodes=episodes,
        evaluation_identity=EvaluationRunIdentity.from_dimensions(
            {
                "revision": "synthetic-g4-conformance",
                "profile": "strict",
                "registry": "disabled",
                "prompt": "prompt-v1",
                "schema": "schema-v1",
                "model": "deterministic-fixture",
                "budget": {"cases": 30},
            }
        ),
    )

    assert report["expected_episode_count"] == 30
    assert report["observed_episode_count"] == 30
    assert report["unrun_episode_count"] == 0
    assert report["invalidated_episode_count"] == 0
    assert report["batch_status"] == "complete"
    assert report["repair_selection_ready"] is True
    assert report["failure_clusters"]
    assert report["runtime_owner_failure_clusters"]
    assert sum(item["episode_count"] for item in report["runtime_owner_failure_clusters"]) == len(
        report["failure_envelopes"]
    )
    assert report["official_score_claimed"] is False
    assert report["score_promotion_gate"] == "m8.2b-new-strict-frozen-evaluation-required"


def test_resume_validator_uses_published_audit_and_only_returns_unobserved_cases(
    tmp_path: Path,
) -> None:
    identity = EvaluationRunIdentity.from_dimensions({"revision": "abc", "profile": "strict"})
    observed = _failed_episode(task_id="case-a", actions=["click"])
    report = report_adapter.write_browsergym_report(
        tmp_path,
        profile="diagnostic",
        registered_tasks=("case-a", "case-b"),
        selected_tasks=("case-a", "case-b"),
        seeds=(0,),
        episodes=(observed,),
        evaluation_identity=identity,
        interrupted=True,
    )
    report_path = tmp_path / "browsergym-report.json"
    assert json.loads(report_path.read_text(encoding="utf-8"))["evaluation_audit"] == report["evaluation_audit"]

    assert matrix.validate_browsergym_resume(
        report_path,
        identity=identity,
        expected_schedule=(("case-a", 0), ("case-b", 0)),
        checkpoints={("case-a", 0): observed},
    ) == {("case-b", 0)}
    with pytest.raises(ValueError, match="exact immutable identity"):
        matrix.validate_browsergym_resume(
            report_path,
            identity=EvaluationRunIdentity.from_dimensions({"revision": "changed", "profile": "strict"}),
            expected_schedule=(("case-a", 0), ("case-b", 0)),
            checkpoints={("case-a", 0): observed},
        )


def test_resume_validator_rejects_published_nonresumable_audit(tmp_path: Path) -> None:
    identity = EvaluationRunIdentity.from_dimensions({"revision": "abc"})
    observed = _failed_episode(task_id="case-a", actions=["click"])
    stop = matrix.browsergym_batch_stop("version_drift")
    assert stop is not None
    report_adapter.write_browsergym_report(
        tmp_path,
        profile="nightly",
        registered_tasks=("case-a", "case-b"),
        selected_tasks=("case-a", "case-b"),
        seeds=(0,),
        episodes=(observed,),
        evaluation_identity=identity,
        batch_stop=stop,
    )

    with pytest.raises(ValueError, match="not eligible"):
        matrix.validate_browsergym_resume(
            tmp_path / "browsergym-report.json",
            identity=identity,
            expected_schedule=(("case-a", 0), ("case-b", 0)),
            checkpoints={("case-a", 0): observed},
        )


def test_resume_without_report_restores_checkpoint_circuit_and_requires_prefix(
    tmp_path: Path,
) -> None:
    identity = EvaluationRunIdentity.from_dimensions({"revision": "abc"})
    provider_a = BrowserGymEpisodeResult(
        "case-a",
        0,
        "failed",
        False,
        0.0,
        False,
        False,
        0,
        [],
        [],
        "provider failure: 429",
        False,
        "",
        provider_failures=["rate_limit"],
    )
    provider_b = BrowserGymEpisodeResult(
        **{**provider_a.__dict__, "task_id": "case-b"}
    )
    schedule = (("case-a", 0), ("case-b", 0), ("case-c", 0))

    assert matrix.validate_browsergym_resume(
        tmp_path / "missing-report.json",
        identity=identity,
        expected_schedule=schedule,
        checkpoints={("case-a", 0): provider_a, ("case-b", 0): provider_b},
    ) == {("case-c", 0)}
    with pytest.raises(ValueError, match="observed prefix"):
        matrix.validate_browsergym_resume(
            tmp_path / "missing-report.json",
            identity=identity,
            expected_schedule=schedule,
            checkpoints={("case-b", 0): provider_b},
        )


def test_resume_without_report_rejects_nonresumable_checkpoint_stop(tmp_path: Path) -> None:
    source_failure = BrowserGymEpisodeResult(
        "case-a",
        0,
        "failed",
        False,
        0.0,
        False,
        False,
        0,
        [],
        [],
        "NamespaceNotFound",
        False,
        "",
    )

    with pytest.raises(ValueError, match="nonresumable batch stop"):
        matrix.validate_browsergym_resume(
            tmp_path / "missing-report.json",
            identity=EvaluationRunIdentity.from_dimensions({"revision": "abc"}),
            expected_schedule=(("case-a", 0), ("case-b", 0)),
            checkpoints={("case-a", 0): source_failure},
        )

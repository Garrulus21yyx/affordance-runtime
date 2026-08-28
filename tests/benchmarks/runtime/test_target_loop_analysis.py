from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage, RuntimeFailure
from affordance_runtime.benchmarks.target_loop.analysis import (
    BadCaseCategory,
    DetourAssessment,
    TrajectoryComparison,
    assess_suspected_detour,
    derive_trajectory_facts,
    project_bad_case,
    project_case_analysis,
)
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    FailureFacts,
    MetricMeasurement,
    TerminalReasonCode,
)
from affordance_runtime.evaluation import TaskOutcomeKind


def _case_result(**updates: object) -> BenchmarkCaseResult:
    measurements = {
        "prompt_tokens": MetricMeasurement(100, True),
        "completion_tokens": MetricMeasurement(20, True),
        "total_tokens": MetricMeasurement(120, True),
        "model_latency_ms": MetricMeasurement(55.0, True),
        "history_tokens": MetricMeasurement(40, True),
        "output_reserve_tokens": MetricMeasurement(512, True),
        "turns": MetricMeasurement(3, True),
        "effectful_dispatches": MetricMeasurement(2, True),
        "control_stall_count": MetricMeasurement(1, True),
        "state_oscillation_count": MetricMeasurement(0, True),
    }
    values: dict[str, object] = {
        "case_id": "case-1",
        "status": "done",
        "execution_completed": True,
        "failure_reason": "",
        "latency_ms": 100.0,
        "measurements": measurements,
        "latest_task_status": "complete",
        "suite_id": "suite",
        "profile_id": "profile",
        "seed": 7,
        "manifest_digest": "digest",
        "run_id": "suite:profile:config",
        "run_attempt_id": "attempt:" + "a" * 32,
    }
    values.update(updates)
    return BenchmarkCaseResult(**values)  # type: ignore[arg-type]


def test_case_analysis_keeps_provider_usage_and_admission_estimates_disjoint() -> None:
    analysis = project_case_analysis(_case_result())

    assert analysis["provider_usage"] == {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
    }
    assert analysis["model_timing"] == {"model_latency_ms": 55.0}
    estimates = analysis["request_admission_estimate"]
    assert estimates["history_tokens"] == 40
    assert estimates["output_reserve_tokens"] == 512
    assert estimates["semantics"] == "capacity_estimate_not_provider_usage_or_cost"
    assert "output_reserve_tokens" not in analysis["provider_usage"]
    assert analysis["runtime_mechanical"]["control_stall_count"] == 1
    assert analysis["evaluator_truth"]["status"] == "done"
    assert analysis["bad_case"]["category"] == "not_applicable"


def test_invalid_model_output_uses_typed_policy_failure_not_text() -> None:
    failure = RuntimeFailure(FailureStage.POLICY, FailureKind.INVALID_OUTPUT, "schema_error")
    result = _case_result(
        status="failed",
        execution_completed=False,
        latest_task_status="",
        failure_reason="arbitrary prose without JSON keywords",
        failure_facts=FailureFacts(
            policy_failure_code="schema_error",
            runtime_failure=failure,
        ),
    )

    presentation = project_bad_case(result)

    assert presentation.category is BadCaseCategory.STRUCTURED_OUTPUT_INVALID
    assert presentation.stage == "policy"
    assert presentation.code == "schema_error"
    assert presentation.termination_source == "action_policy"


def test_monitor_control_stall_preserves_owner_and_oscillation_evidence() -> None:
    measurements = dict(_case_result().measurements)
    measurements["state_oscillation_count"] = MetricMeasurement(2, True)
    result = _case_result(
        status="blocked",
        latest_task_status="incomplete",
        terminal_reason_code=TerminalReasonCode.CONTROL_STALLED,
        control_termination_owner="episode_monitor",
        measurements=measurements,
        failure_facts=FailureFacts(runtime_reason_code="control_stalled"),
    )

    presentation = project_bad_case(result)

    assert presentation.category is BadCaseCategory.CONTROL_STALL
    assert presentation.termination_source == "episode_monitor"
    assert "oscillation" in presentation.summary.casefold()


def test_native_verifier_failure_remains_the_termination_authority() -> None:
    result = _case_result(
        status="blocked",
        latest_task_status="blocked",
        failure_facts=FailureFacts(
            task_outcome_kind=TaskOutcomeKind.TERMINAL_FAILURE.value,
            task_outcome_code="verified_terminal_task_failure",
        ),
    )

    presentation = project_bad_case(result)

    assert presentation.category is BadCaseCategory.NATIVE_TASK_FAILURE
    assert presentation.termination_source == "native_verifier"
    assert presentation.code == "verified_terminal_task_failure"


def _trajectory(attempt: str, **updates: object) -> TrajectoryComparison:
    values: dict[str, object] = {
        "run_attempt_id": attempt,
        "case_id": "case-1",
        "task_contract_id": "task-contract",
        "environment_id": "env-v1",
        "profile_id": "profile",
        "successful": True,
        "turns": 3,
        "prompt_tokens": 500,
        "effectful_dispatches": 2,
        "recovery_count": 0,
        "evidence_refs": (f"trace:{attempt}",),
    }
    values.update(updates)
    return TrajectoryComparison(**values)  # type: ignore[arg-type]


def test_detour_is_not_assessed_without_a_compatible_successful_cohort() -> None:
    candidate = _trajectory("attempt:candidate", successful=False, turns=8)
    incompatible = _trajectory("attempt:other", environment_id="env-v2")

    assert assess_suspected_detour(candidate, ()) == DetourAssessment("not_assessed")
    assert assess_suspected_detour(candidate, (incompatible,)) == DetourAssessment("not_assessed")


def test_detour_is_relative_evidence_with_comparison_identity_and_deltas() -> None:
    candidate = _trajectory(
        "attempt:candidate",
        successful=False,
        turns=8,
        prompt_tokens=1_200,
        effectful_dispatches=5,
        recovery_count=2,
        longest_no_progress_span=4,
    )
    baseline = _trajectory("attempt:baseline")

    assessment = assess_suspected_detour(candidate, (baseline,))

    assert assessment.disposition == "suspected_detour"
    assert assessment.comparison_run_attempt_ids == ("attempt:baseline",)
    assert assessment.measured_deltas == {
        "turns": 5,
        "prompt_tokens": 700,
        "effectful_dispatches": 3,
        "recovery_count": 2,
        "semantic_page_revisits": 0,
        "semantic_action_revisits": 0,
        "longest_no_progress_span": 4,
    }


def test_trace_mechanics_are_derived_only_from_typed_fields() -> None:
    events = (
        {
            "schema_version": "gui-agent-trace.v1",
            "sequence": 1,
            "event": "step_completed",
            "step": 1,
            "lineage": {"action_id": "click", "after_world_digest": "world-a"},
            "result": {
                "public_world_delta": {"changed": False},
                "recovery_signal": {"kind": "control_stall"},
            },
        },
        {
            "schema_version": "gui-agent-trace.v1",
            "sequence": 2,
            "event": "step_completed",
            "step": 2,
            "lineage": {"action_id": "click", "after_world_digest": "world-a"},
            "result": {"public_world_delta": {"changed": True}, "recovery_signal": None},
        },
        {
            "schema_version": "gui-agent-trace.v1",
            "sequence": 3,
            "event": "native_evaluator_returned",
            "evaluation_status": "complete",
        },
        {
            "schema_version": "gui-agent-trace.v1",
            "sequence": 4,
            "event": "model_turn",
        },
    )

    facts = derive_trajectory_facts(events)

    assert facts.first_abnormal_step == 1
    assert facts.last_progress_step == 2
    assert facts.longest_no_progress_span == 1
    assert facts.semantic_action_revisits == 1
    assert facts.public_world_revisits == 1
    assert facts.post_terminal_model_calls == 1
    assert facts.recovery_to_progress_count == 1

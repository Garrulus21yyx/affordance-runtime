import asyncio

from affordance_runtime.benchmarks.model_conformance.decision_matrix import DECISION_VARIANTS
from affordance_runtime.benchmarks.model_conformance.runtime_decision_matrix import (
    run_scripted_runtime_decision_matrix,
    runtime_outcome_matches,
)


def test_all_seven_decisions_enter_production_runtime_control_owner() -> None:
    outcomes = asyncio.run(run_scripted_runtime_decision_matrix())
    assert tuple(item.decision_variant for item in outcomes) == DECISION_VARIANTS
    assert all(runtime_outcome_matches(item) for item in outcomes)


def test_runtime_matrix_records_variant_specific_control_results() -> None:
    outcomes = {
        item.decision_variant: item
        for item in asyncio.run(run_scripted_runtime_decision_matrix())
    }
    assert outcomes["select_action"].execution_count == 1
    assert outcomes["request_observation"].observation_count == 2
    assert outcomes["request_action_page"].page_changed
    assert outcomes["ask_user"].pending_question
    assert outcomes["propose_done"].task_evaluation_calls >= 3
    assert outcomes["wait"].wait_budget_decreased
    assert outcomes["abort"].status == "failed" and not outcomes["abort"].policy_failure

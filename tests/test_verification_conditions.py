from affordance_runtime.contracts import ActionContract, Condition, Observation, RuntimeErrorCode
from affordance_runtime.verification import evaluate_condition, evaluate_conditions, preflight


def test_condition_evaluator_supports_paths_comparisons_and_params() -> None:
    facts = {"page": {"saved": True, "count": 3}, "params": {"expected": 3}}
    conditions = [Condition("page.saved"), Condition("page.count == params.expected")]

    assert evaluate_conditions(conditions, facts)
    assert evaluate_condition(Condition("page.count >= 2"), facts).observed == 3


def test_condition_evaluator_fails_closed_for_missing_paths() -> None:
    result = evaluate_condition(Condition("page.missing == true"), {"page": {}})
    assert not result.passed
    assert "missing condition path" in result.reason


def test_preflight_uses_observation_and_contract_facts() -> None:
    contract = ActionContract(
        id="contract_1",
        intent="save",
        affordance_id="save",
        action="click",
        backend="dom",
        environment_revision="rev-1",
        locator={"selector": "#save", "enabled": True},
        parameters={"expected_role": "admin"},
        preconditions=[Condition("page.ready and target.enabled and params.expected_role == 'admin'")],
    )
    observation = Observation(environment_revision="rev-1", metadata={"page": {"ready": True}})

    assert preflight(contract, observation) is None
    assert preflight(contract, Observation(environment_revision="rev-1", metadata={"page": {"ready": False}})) == RuntimeErrorCode.PRECONDITION_FAILED

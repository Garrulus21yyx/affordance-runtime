from threading import Thread
from urllib.request import urlopen

from affordance_runtime.contracts import (
    ActionContract,
    Condition,
    ExecutionReceipt,
    Observation,
    RuntimeErrorCode,
    VerifierSpec,
)
from affordance_runtime.fixtures import EXPORT_SHA256, create_fixture_server
from affordance_runtime.verification.mechanical import (
    VerifierLadder,
    evaluate_condition,
    evaluate_conditions,
    preflight,
)


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
    assert (
        preflight(contract, Observation(environment_revision="rev-1", metadata={"page": {"ready": False}}))
        == RuntimeErrorCode.PRECONDITION_FAILED
    )


def test_registered_api_final_recheck_is_authoritative_but_http_json_is_only_strong() -> None:
    server = create_fixture_server(port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(f"{base_url}/api/export", timeout=2.0) as response:  # noqa: S310 - local fixture
            response.read()
        receipt = ExecutionReceipt("contract:export", "dom", True, "env:1", "env:2", 1.0)
        observation = Observation("env:2", snapshot_id="snapshot:export")
        expected = {
            "path": "audit_log",
            "contains": {"effect": "report.export", "sha256": EXPORT_SHA256},
        }
        report = VerifierLadder().verify_report(
            [
                VerifierSpec(
                    "api_final_recheck",
                    f"{base_url}/api/state",
                    expected,
                    criterion_ids=("criterion:export-final",),
                ),
            ],
            receipt,
            observation,
        )
        strong = VerifierLadder().verify_report(
            [VerifierSpec("http_json", f"{base_url}/api/state", {"path": "seed", "value": 0})],
            receipt,
            observation,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)

    assert report.passed
    assert report.evidence[0].source == "api_state"
    assert report.evidence[0].strength == "authoritative"
    assert strong.passed
    assert strong.evidence[0].strength == "strong"

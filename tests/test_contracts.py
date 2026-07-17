from affordance_runtime.contracts import ActionContract, Affordance, AffordanceLease, Condition, Observation, Surface
from affordance_runtime.verification import preflight


def test_action_contract_carries_environment_revision() -> None:
    lease = AffordanceLease.issue(environment_revision="rev-1")
    affordance = Affordance(
        id="dom_button_1",
        surface=Surface.DOM,
        role="button",
        label="Save",
        action="click",
        locator={"selector": "#save"},
        lease=lease,
    )

    contract = ActionContract.from_affordance(
        affordance,
        intent="save form",
        backend="playwright_dom",
        expected_effects=[Condition("saved_banner_visible")],
    )

    assert contract.environment_revision == "rev-1"
    assert preflight(contract, Observation(environment_revision="rev-1")) is None
    assert preflight(contract, Observation(environment_revision="rev-2")).value == "stale_observation"


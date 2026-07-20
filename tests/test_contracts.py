from dataclasses import replace
from time import time

from affordance_runtime.contracts import (
    ActionContract,
    Affordance,
    AffordanceLease,
    Condition,
    Observation,
    RuntimeErrorCode,
    Surface,
)
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


def test_contract_binds_snapshot_target_and_canonical_hash() -> None:
    lease = AffordanceLease.issue(
        environment_revision="legacy-rev",
        snapshot_id="snap-1",
        page_revision="page-rev-1",
        target_fingerprint="target-1",
    )
    affordance = Affordance("save", Surface.DOM, "button", "Save", "click", {"selector": "#save"}, lease)
    contract = ActionContract.from_affordance(affordance, intent="save", backend="dom")
    observation = Observation(
        environment_revision="legacy-rev",
        snapshot_id="snap-1",
        page_revision="page-rev-1",
        target_fingerprints={"save": "target-1"},
    )

    assert contract.contract_hash.startswith("sha256:")
    assert contract.contract_hash == replace(contract, contract_hash="").contract_hash
    assert preflight(contract, observation) is None
    assert preflight(contract, replace(observation, snapshot_id="snap-2")) == RuntimeErrorCode.SNAPSHOT_MISMATCH
    assert (
        preflight(contract, replace(observation, target_fingerprints={"save": "target-2"}))
        == RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH
    )
    assert preflight(replace(contract, expires_at_s=time() - 1), observation) == RuntimeErrorCode.LEASE_EXPIRED

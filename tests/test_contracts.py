from dataclasses import replace
from time import time

import pytest

from affordance_runtime.contracts import (
    ActionContract,
    Affordance,
    AffordanceLease,
    Condition,
    GestureBinding,
    GestureBindingError,
    GestureContractBinder,
    GestureTargetBinding,
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


def test_gesture_contract_binds_and_preflights_both_endpoints() -> None:
    source_lease = AffordanceLease.issue(
        environment_revision="rev-1", snapshot_id="snap-1", page_revision="page-1", target_fingerprint="source-1"
    )
    destination_lease = AffordanceLease.issue(
        environment_revision="rev-1", snapshot_id="snap-1", page_revision="page-1", target_fingerprint="destination-1"
    )
    source = Affordance("source", Surface.DOM, "listitem", "Source", "drag", {"bid": "source"}, source_lease)
    destination = Affordance(
        "destination", Surface.DOM, "listitem", "Destination", "drag", {"bid": "destination"}, destination_lease
    )
    binding = GestureBinding(
        source=GestureTargetBinding.from_affordance(source),
        destination=GestureTargetBinding.from_affordance(destination),
        selected_route="dom",
    )
    contract = replace(
        ActionContract.from_affordance(source, intent="reorder", backend="dom"),
        gesture_binding=binding,
        contract_hash="",
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprints={"source": "source-1", "destination": "destination-1"},
    )

    assert preflight(contract, observation) is None
    assert contract.contract_hash != replace(contract, gesture_binding=None, contract_hash="").contract_hash
    assert preflight(
        contract,
        replace(observation, target_fingerprints={"source": "source-1", "destination": "new-destination"}),
    ) == RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH


def test_core_gesture_binder_rejects_same_or_semantically_incompatible_endpoints() -> None:
    source_lease = AffordanceLease.issue(
        environment_revision="rev-1",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprint="source-1",
    )
    destination_lease = AffordanceLease.issue(
        environment_revision="rev-1",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprint="destination-1",
    )
    source = Affordance(
        "source",
        Surface.DOM,
        "item",
        "Source",
        "drag",
        {},
        source_lease,
        backend_candidates=["dom"],
    )
    destination = Affordance(
        "destination",
        Surface.DOM,
        "region",
        "Destination",
        "drop",
        {},
        destination_lease,
        backend_candidates=["dom"],
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprints={"source": "source-1", "destination": "destination-1"},
    )

    for invalid_source, invalid_destination in (
        (source, source),
        (replace(source, action="activate"), destination),
        (source, replace(destination, action="activate")),
    ):
        with pytest.raises(GestureBindingError) as caught:
            GestureContractBinder().bind(
                invalid_source,
                invalid_destination,
                selected_route="dom",
                observation=observation,
            )
        assert caught.value.code == RuntimeErrorCode.PRECONDITION_FAILED


def test_gesture_preflight_rechecks_blocking_overlays_for_both_endpoints() -> None:
    source_lease = AffordanceLease.issue(
        environment_revision="rev-1",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprint="source-1",
    )
    destination_lease = AffordanceLease.issue(
        environment_revision="rev-1",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprint="destination-1",
    )
    source = Affordance(
        "source", Surface.VISUAL, "item", "Source", "drag", {"bbox": [10, 10, 20, 20]}, source_lease
    )
    destination = Affordance(
        "destination",
        Surface.VISUAL,
        "region",
        "Destination",
        "drop",
        {"bbox": [100, 100, 40, 40]},
        destination_lease,
    )
    binding = GestureBinding(
        source=GestureTargetBinding.from_affordance(source),
        destination=GestureTargetBinding.from_affordance(destination),
        selected_route="visual",
    )
    contract = replace(
        ActionContract.from_affordance(source, intent="move source", backend="visual"),
        gesture_binding=binding,
        contract_hash="",
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprints={"source": "source-1", "destination": "destination-1"},
        metadata={"blocking_overlays": [{"bbox": [95, 95, 50, 50]}]},
    )

    assert preflight(contract, observation) == RuntimeErrorCode.PRECONDITION_FAILED


def test_core_gesture_binder_requires_compatible_endpoints_and_one_shared_route() -> None:
    source_lease = AffordanceLease.issue(
        environment_revision="rev-1",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprint="source-1",
    )
    destination_lease = AffordanceLease.issue(
        environment_revision="rev-1",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprint="destination-1",
    )
    source = Affordance(
        "source",
        Surface.DOM,
        "listitem",
        "Source",
        "drag",
        {"bid": "source"},
        source_lease,
        backend_candidates=["dom", "visual"],
    )
    destination = Affordance(
        "destination",
        Surface.DOM,
        "listitem",
        "Destination",
        "drop",
        {"bid": "destination"},
        destination_lease,
        backend_candidates=["visual"],
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprints={"source": "source-1", "destination": "destination-1"},
    )

    with pytest.raises(GestureBindingError) as caught:
        GestureContractBinder().bind(source, destination, selected_route="dom", observation=observation)
    assert caught.value.code == RuntimeErrorCode.BACKEND_UNAVAILABLE

    binding = GestureContractBinder().bind(
        source,
        destination,
        selected_route="visual",
        observation=observation,
    )
    assert binding.selected_route == "visual"
    assert binding.source.semantic_target_id == "source"
    assert binding.destination.semantic_target_id == "destination"

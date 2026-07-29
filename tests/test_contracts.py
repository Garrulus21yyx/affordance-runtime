from dataclasses import replace
from time import time

import pytest

from affordance_runtime.contracts import (
    ActionContract,
    Affordance,
    AffordanceLease,
    Condition,
    ExecutionReceipt,
    GestureBinding,
    GestureBindingError,
    GestureContractBinder,
    GestureTargetBinding,
    Observation,
    RuntimeErrorCode,
    Surface,
)
from affordance_runtime.planning_contracts import PlannerDecision
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


def test_action_contract_payloads_are_deeply_immutable_and_hash_stable() -> None:
    lease = AffordanceLease.issue(
        environment_revision="legacy-rev",
        snapshot_id="snap-1",
        page_revision="page-rev-1",
        target_fingerprint="target-1",
    )
    raw_parameters = {"text": "Alice", "modifiers": ["shift"]}
    raw_locator = {"selector": "#name", "bbox": [1, 2, 3, 4]}
    affordance = Affordance(
        "name",
        Surface.DOM,
        "textbox",
        "Name",
        "type",
        raw_locator,
        lease,
    )

    contract = ActionContract.from_affordance(
        affordance,
        intent="enter name",
        backend="dom",
        parameters=raw_parameters,
    )
    original_hash = contract.contract_hash

    raw_parameters["modifiers"].append("ctrl")
    raw_locator["bbox"].append(5)

    assert contract.contract_hash == original_hash
    assert contract.compute_hash() == original_hash
    assert contract.parameters["modifiers"] == ("shift",)
    assert contract.locator["bbox"] == (1, 2, 3, 4)

    with pytest.raises(TypeError):
        contract.parameters["text"] = "Bob"
    with pytest.raises(TypeError):
        contract.locator["bbox"][0] = 9


def test_execution_receipt_evidence_is_deeply_immutable_from_source_payload() -> None:
    raw_evidence = {
        "actual_value": {"text": "Alice", "tokens": ["first"]},
        "artifact_refs": ["artifact:1"],
    }

    receipt = ExecutionReceipt(
        contract_id="contract-1",
        backend="dom",
        success=True,
        started_revision="page-1",
        ended_revision="page-2",
        latency_ms=10.0,
        evidence=raw_evidence,
    )

    raw_evidence["actual_value"]["tokens"].append("mutated")
    raw_evidence["artifact_refs"].append("artifact:2")

    assert receipt.evidence["actual_value"]["tokens"] == ("first",)
    assert receipt.evidence["artifact_refs"] == ("artifact:1",)
    with pytest.raises(TypeError):
        receipt.evidence["actual_value"]["text"] = "Bob"
    with pytest.raises(TypeError):
        receipt.evidence["artifact_refs"][0] = "artifact:changed"


def test_planner_decision_diagnostic_dicts_are_deeply_immutable_from_source_payload() -> None:
    raw_result = {"status": "done", "nested": {"artifact_refs": ["artifact:1"]}}
    raw_context = {"model": {"messages": ["bounded"]}}

    decision = PlannerDecision(
        done=True,
        result=raw_result,
        planner_context=raw_context,
    )

    raw_result["nested"]["artifact_refs"].append("artifact:2")
    raw_context["model"]["messages"].append("mutated")

    assert decision.result["nested"]["artifact_refs"] == ("artifact:1",)
    assert decision.planner_context["model"]["messages"] == ("bounded",)
    with pytest.raises(TypeError):
        decision.result["status"] = "changed"
    with pytest.raises(TypeError):
        decision.planner_context["model"]["messages"][0] = "changed"


def test_observation_payloads_are_deeply_immutable_from_source_payload() -> None:
    raw_metadata = {"browsergym": {"goal": "inspect", "candidates": ["button"]}}
    raw_fingerprints = {"target": "fingerprint-1"}
    raw_artifacts = ["artifact:observation"]

    observation = Observation(
        "rev-1",
        metadata=raw_metadata,
        target_fingerprints=raw_fingerprints,
        artifact_refs=raw_artifacts,
    )

    raw_metadata["browsergym"]["candidates"].append("textbox")
    raw_fingerprints["target"] = "fingerprint-2"
    raw_artifacts.append("artifact:mutated")

    assert observation.metadata["browsergym"]["candidates"] == ("button",)
    assert observation.target_fingerprints["target"] == "fingerprint-1"
    assert observation.artifact_refs == ("artifact:observation",)
    with pytest.raises(TypeError):
        observation.metadata["browsergym"]["goal"] = "mutated"
    with pytest.raises(TypeError):
        observation.target_fingerprints["target"] = "fingerprint-3"
    with pytest.raises(TypeError):
        observation.artifact_refs[0] = "artifact:changed"


def test_affordance_payloads_are_deeply_immutable_from_source_payload() -> None:
    lease_provenance = ["dom"]
    lease = AffordanceLease.issue(
        environment_revision="rev-1",
        provenance=lease_provenance,
    )
    raw_locator = {"selector": "#name", "bbox": [1, 2, 3, 4]}
    raw_state = {"enabled": True, "selected_options": ["Alice"]}
    raw_payload = {"options": [{"label": "Alice"}]}
    raw_backends = ["dom"]
    raw_evidence = ["evidence:dom"]

    affordance = Affordance(
        "name",
        Surface.DOM,
        "textbox",
        "Name",
        "type",
        raw_locator,
        lease,
        backend_candidates=raw_backends,
        state=raw_state,
        evidence=raw_evidence,
        payload=raw_payload,
    )

    raw_locator["bbox"].append(5)
    raw_state["selected_options"].append("Bob")
    raw_payload["options"][0]["label"] = "Bob"
    raw_backends.append("visual")
    raw_evidence.append("evidence:visual")
    lease_provenance.append("visual")

    assert affordance.locator["bbox"] == (1, 2, 3, 4)
    assert affordance.state["selected_options"] == ("Alice",)
    assert affordance.payload["options"][0]["label"] == "Alice"
    assert affordance.backend_candidates == ("dom",)
    assert affordance.evidence == ("evidence:dom",)
    assert affordance.lease.provenance == ("dom",)
    with pytest.raises(TypeError):
        affordance.locator["selector"] = "#other"
    with pytest.raises(TypeError):
        affordance.state["selected_options"][0] = "changed"
    with pytest.raises(TypeError):
        affordance.payload["options"][0]["label"] = "changed"


def test_gesture_target_binding_locator_is_deeply_immutable_from_source_payload() -> None:
    lease = AffordanceLease.issue(
        environment_revision="rev-1",
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprint="target-1",
    )
    locator = {"bbox": [1, 2, 3, 4], "metadata": {"route": "visual"}}
    binding = GestureTargetBinding(
        semantic_target_id="target",
        candidate_id="candidate",
        locator=locator,
        snapshot_id="snap-1",
        page_revision="page-1",
        target_fingerprint="target-1",
        target_fingerprint_key="target",
        lease=lease,
    )

    locator["bbox"][0] = 9
    locator["metadata"]["route"] = "mutated"

    assert binding.locator["bbox"] == (1, 2, 3, 4)
    assert binding.locator["metadata"] == {"route": "visual"}
    with pytest.raises(TypeError):
        binding.locator["metadata"]["route"] = "mutated"


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

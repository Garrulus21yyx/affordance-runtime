import json

from affordance_runtime.agent.context.failures import ModelFailure, ModelFailureKind
from affordance_runtime.benchmarks.model_conformance.contracts import ModelConformanceStage
from affordance_runtime.benchmarks.model_conformance.stages import attribute_decision_payload


def _payload(**changes):
    value = {
        "type": "select_action",
        "context_id": "context:current",
        "action_id": "action:visible",
        "parameters": {},
        "destination_id": "",
    }
    value.update(changes)
    return json.dumps(value)


def test_failure_stage_transport_and_strict_json_and_schema() -> None:
    assert attribute_decision_payload(
        ModelFailure(ModelFailureKind.PROVIDER_UNAVAILABLE, "safe", False),
        "context:current", ("action:visible",), {"action:visible": ("",)},
    ).stage == ModelConformanceStage.TRANSPORT
    assert attribute_decision_payload(
        "{", "context:current", ("action:visible",), {"action:visible": ("",)},
    ).stage == ModelConformanceStage.STRICT_JSON
    assert attribute_decision_payload(
        json.dumps({"type": "select_action"}), "context:current",
        ("action:visible",), {"action:visible": ("",)},
    ).stage == ModelConformanceStage.PAYLOAD_SCHEMA


def test_failure_stage_context_action_destination_and_runtime_admission() -> None:
    common = (("action:visible",), {"action:visible": ("",)})
    assert attribute_decision_payload(
        _payload(context_id="context:stale"), "context:current", *common,
    ).stage == ModelConformanceStage.CONTEXT_ID
    assert attribute_decision_payload(
        _payload(action_id="action:hidden"), "context:current", *common,
    ).stage == ModelConformanceStage.ACTION_ID
    assert attribute_decision_payload(
        _payload(destination_id="target:hidden"), "context:current", *common,
    ).stage == ModelConformanceStage.DESTINATION_ID
    assert attribute_decision_payload(
        _payload(), "context:current", *common, runtime_admission_error="rejected",
    ).stage == ModelConformanceStage.RUNTIME_ADMISSION
    assert attribute_decision_payload(
        _payload(), "context:current", *common,
    ).stage == ModelConformanceStage.SUCCESS


def test_hidden_destination_has_secret_free_grounding_shape() -> None:
    actions = ("action:visible", "action:other")
    destinations = {
        "action:visible": ("destination:visible",),
        "action:other": ("destination:other",),
    }
    targets = {"action:visible": "target:visible", "action:other": "target:other"}
    cases = (
        ("", "empty_when_required"),
        ("target:visible", "equals_target_id"),
        ("action:visible", "equals_action_id"),
        ("destination:other", "belongs_to_other_action"),
        ("public:unknown", "unknown_public_id"),
    )
    for destination_id, expected in cases:
        attributed = attribute_decision_payload(
            _payload(destination_id=destination_id),
            "context:current",
            actions,
            destinations,
            visible_targets=targets,
        )
        assert attributed.destination_failure_shape == expected

    forbidden = attribute_decision_payload(
        _payload(destination_id="public:unknown"),
        "context:current",
        ("action:visible",),
        {"action:visible": ("",)},
        visible_targets={"action:visible": "target:visible"},
    )
    assert forbidden.destination_failure_shape == "nonempty_when_forbidden"

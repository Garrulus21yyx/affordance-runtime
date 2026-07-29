import json

from affordance_runtime.contracts import ExecutionReceipt, Observation, VerifierSpec
from affordance_runtime.verification import (
    ControlStateVerifier,
    DomAttributeVerifier,
    EvidenceVerifier,
    HttpJsonVerifier,
    ObservationMetadataVerifier,
    StateDeltaOrTerminalVerifier,
    VerifierLadder,
)


def _receipt(**evidence: object) -> ExecutionReceipt:
    return ExecutionReceipt(
        "contract",
        "portable-web",
        True,
        "rev-1",
        "rev-2",
        1.0,
        evidence=dict(evidence),
    )


def test_verifier_evaluate_preserves_verify_result_and_observed_value() -> None:
    evidence_spec = VerifierSpec("evidence", "saved", True)
    metadata_spec = VerifierSpec("observation_metadata", "saved", True)
    dom_spec = VerifierSpec(
        "dom_attribute",
        "field",
        {"target_attribute": "data-runtime-handle", "attribute": "value", "value": "Alice"},
    )
    control_spec = VerifierSpec(
        "control_state",
        "checkbox",
        {"field": "checked", "value": True},
    )
    delta_spec = VerifierSpec(
        "state_delta_or_terminal",
        "slider",
        {"field": "value", "changed_from": "5"},
    )
    observation = Observation(
        "rev-2",
        snapshot_id="snapshot-post",
        metadata={
            "saved": True,
            "html": '<input data-runtime-handle="field" value="Alice">',
            "control_states": {
                "checkbox": {"checked": True},
                "slider": {"value": "7"},
            },
        },
    )

    cases = (
        (EvidenceVerifier(), evidence_spec, _receipt(saved=True), observation, True),
        (ObservationMetadataVerifier(), metadata_spec, _receipt(), observation, True),
        (DomAttributeVerifier(), dom_spec, _receipt(), observation, "Alice"),
        (ControlStateVerifier(), control_spec, _receipt(), observation, True),
        (StateDeltaOrTerminalVerifier(), delta_spec, _receipt(), observation, True),
    )

    for verifier, spec, receipt, obs, expected_observed in cases:
        evaluation = verifier.evaluate(spec, receipt, obs)

        assert evaluation.passed == verifier.verify(spec, receipt, obs)
        assert evaluation.observed == expected_observed


def test_http_json_verifier_reports_actual_projected_value(monkeypatch) -> None:
    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"form": {"status": "submitted"}}).encode()

    def _fake_urlopen(url: str, timeout: float):  # noqa: ARG001
        return _Response()

    monkeypatch.setattr("affordance_runtime.verification.urlopen", _fake_urlopen)
    spec = VerifierSpec(
        "http_json",
        "https://example.invalid/state",
        {"path": "form.status", "value": "submitted"},
    )

    evaluation = HttpJsonVerifier().evaluate(spec, _receipt(), Observation("rev-2"))

    assert evaluation.passed
    assert evaluation.observed == "submitted"
    assert evaluation.passed == HttpJsonVerifier().verify(spec, _receipt(), Observation("rev-2"))


def test_verifier_ladder_report_uses_real_observed_values_and_semantic_key() -> None:
    spec = VerifierSpec(
        "control_state",
        "slider",
        {"field": "value", "value": "7"},
        evidence_key="spec:slider-value",
        criterion_ids=("criterion:slider",),
        requirement_ids=("requirement:slider",),
    )
    report = VerifierLadder().verify_report(
        [spec],
        _receipt(),
        Observation(
            "rev-2",
            snapshot_id="snapshot-post",
            metadata={"control_states": {"slider": {"value": "7"}}},
        ),
    )

    assert report.passed
    assert report.evidence[0].observed == "7"
    assert report.evidence[0].expected == {"field": "value", "value": "7"}
    assert report.evidence[0].semantic_evidence_key == "spec:slider-value"
    assert report.evidence[0].evidence_id == "verification:snapshot-post:0:spec:slider-value"


def test_state_delta_or_terminal_remains_weak_generic_evidence() -> None:
    spec = VerifierSpec(
        "state_delta_or_terminal",
        "slider",
        {"field": "value", "changed_from": "5"},
        evidence_key="spec:slider-delta",
    )
    report = VerifierLadder().verify_report(
        [spec],
        _receipt(),
        Observation(
            "rev-2",
            snapshot_id="snapshot-post",
            metadata={"control_states": {"slider": {"value": "7"}}},
        ),
    )

    assert report.passed
    assert report.evidence[0].observed is True
    assert report.evidence[0].strength == "weak"
    assert report.evidence[0].semantic_evidence_key == "spec:slider-delta"

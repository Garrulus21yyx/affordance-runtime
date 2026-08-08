import asyncio
import json
from dataclasses import fields
from types import SimpleNamespace

from affordance_runtime.benchmarks.target_loop.contracts import MetricMeasurement
from affordance_runtime.benchmarks.target_loop.live_policy import (
    LIVE_ATTESTATION_SCHEMA_VERSION,
    LiveModelPolicyAttestation,
    LiveModelPolicyStatus,
    evaluate_live_policy_suite,
    run_live_model_policy_attestation,
)
from affordance_runtime.model_policy import ModelMetadata


def test_live_policy_attestation_is_unavailable_without_opt_in(tmp_path) -> None:
    called = False

    def forbidden_factory(_environment):
        nonlocal called
        called = True
        raise AssertionError("disabled live attestation must not build a provider")

    output = tmp_path / "live.json"
    result = asyncio.run(run_live_model_policy_attestation(
        output, environment={}, policy_factory=forbidden_factory,
    ))

    assert not called
    assert result.status == LiveModelPolicyStatus.UNAVAILABLE
    assert not result.accepted
    assert json.loads(output.read_text())["attestation_schema_version"] == LIVE_ATTESTATION_SCHEMA_VERSION


def test_live_policy_attestation_rejects_dirty_tree_before_provider_call(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "affordance_runtime.benchmarks.target_loop.live_policy._git",
        lambda *args: "a" * 40 if args[:2] == ("rev-parse", "HEAD") else " M dirty",
    )
    called = False

    def forbidden_factory(_environment):
        nonlocal called
        called = True
        raise AssertionError

    result = asyncio.run(run_live_model_policy_attestation(
        tmp_path / "live.json",
        environment={"RUN_LIVE_MODEL_POLICY_ATTESTATION": "1"},
        policy_factory=forbidden_factory,
    ))

    assert not called
    assert result.status == LiveModelPolicyStatus.FAILED
    assert any("clean" in item for item in result.acceptance_errors)


def test_live_policy_contract_contains_only_secret_free_metadata_fields() -> None:
    names = {item.name for item in fields(LiveModelPolicyAttestation)}
    forbidden = {"api_key", "endpoint_url", "raw_response", "prompt", "selector", "href"}
    assert not names & forbidden


def test_injected_policy_result_cannot_satisfy_live_attestation() -> None:
    metric_names = {
        "observations": 2, "executions": 1, "policy_calls": 1, "provider_attempts": 1,
        "forbidden_effect_attempts": 0, "duplicate_unknown_attempts": 0,
        "stale_zero_call_violations": 0,
    }
    case = SimpleNamespace(
        status="done",
        measurements={name: MetricMeasurement(value, True) for name, value in metric_names.items()},
    )
    suite = SimpleNamespace(cases=(case,), acceptance=SimpleNamespace(acceptance_errors=()))
    instrumentation = SimpleNamespace(model_metadata=ModelMetadata("fixture", "scripted"))

    result = evaluate_live_policy_suite(
        "a" * 40, suite, instrumentation, live_origin=False,
    )

    assert not result.accepted
    assert result.status == LiveModelPolicyStatus.FAILED
    assert any("test-only" in item for item in result.acceptance_errors)

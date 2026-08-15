import json

from affordance_runtime.benchmarks.model_conformance.contracts import ConformanceAttempt


def test_conformance_attempt_cannot_store_prompt_or_response_content() -> None:
    names = set(ConformanceAttempt.__annotations__)
    assert "raw_response" not in names
    assert "system_prompt" not in names
    assert "user_message" not in names
    assert {"output_bytes", "output_sha256"}.issubset(names)
    assert "destination_failure_shape" in names
    assert "salience_metrics" in names
    assert "credential" not in json.dumps(sorted(names))

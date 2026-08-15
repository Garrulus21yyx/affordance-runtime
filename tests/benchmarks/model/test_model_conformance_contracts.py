import json

import pytest

from affordance_runtime.benchmarks.model_conformance.contracts import (
    ConformanceAttempt,
    ModelConformanceStage,
    ModelProfileIdentity,
)
from affordance_runtime.benchmarks.model_conformance.reporting import public_attempt_payload


def test_exact_profile_contract_is_frozen_and_has_no_raw_response_field() -> None:
    identity = ModelProfileIdentity(
        "ollama", "qwen2.5:7b", "local", "ollama", "0.32.0", "digest",
        "qwen2", "7.6B", "Q4_K_M", "p5-m1.1", "agent-decision.v1", "default-64k",
    )
    with pytest.raises(Exception):
        identity.model_id = "changed"  # type: ignore[misc]
    assert "raw" not in json.dumps(identity.__dict__).casefold()
    assert "endpoint_url" not in identity.__dict__


def test_attempt_report_retains_only_output_size_and_digest() -> None:
    attempt = ConformanceAttempt(
        "attempt:1", "0", "format-only", ModelConformanceStage.STRICT_JSON,
        False, "invalid_response", "", 10, 20, 10, 30, 60, 1, 1, 1, 0,
        4, 2, 6, 19, "sha256:abc", 2.5,
    )
    payload = public_attempt_payload(attempt)
    assert payload["output_bytes"] == 19
    assert payload["output_sha256"] == "sha256:abc"
    assert payload["destination_failure_shape"] == ""
    assert all("raw" not in key for key in payload)

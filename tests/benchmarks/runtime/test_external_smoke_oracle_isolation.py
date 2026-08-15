import json

from affordance_runtime.benchmarks.external_smoke.manifest import EXTERNAL_SMOKE_MANIFEST


def test_external_manifest_contains_no_policy_oracle_material() -> None:
    payload = json.dumps(EXTERNAL_SMOKE_MANIFEST, default=lambda value: value.__dict__).lower()
    forbidden = (
        "expected_answer", "target_answer", "reference_action", "reference_trajectory",
        "success_script", "hidden_state", "benchmark_oracle", "selector", "coordinate",
    )
    assert not any(item in payload for item in forbidden)

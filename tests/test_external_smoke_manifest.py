from dataclasses import fields, replace

from affordance_runtime.benchmarks.external_smoke.contracts import ExternalSmokeCase
from affordance_runtime.benchmarks.external_smoke.manifest import (
    EXTERNAL_SMOKE_MANIFEST,
    external_manifest_digest,
)


def test_external_smoke_manifest_is_fixed_reviewed_and_mechanical_only() -> None:
    manifest = EXTERNAL_SMOKE_MANIFEST
    assert manifest.schema_version == "external-smoke-manifest.v1"
    assert manifest.benchmark_family == "browsergym-miniwob"
    assert manifest.package_name == "browsergym-miniwob"
    assert manifest.package_version == "0.14.3"
    assert manifest.reviewed and manifest.mechanical_only
    assert [item.benchmark_task_id for item in manifest.cases] == [
        "browsergym/miniwob.click-button",
        "browsergym/miniwob.enter-text",
        "browsergym/miniwob.choose-list",
    ]


def test_external_case_contract_has_no_oracle_or_private_route_fields() -> None:
    names = {item.name for item in fields(ExternalSmokeCase)}
    forbidden = {
        "expected_answer", "target_selector", "coordinate", "reference_trajectory",
        "success_script", "hidden_state", "benchmark_oracle",
    }
    assert not names & forbidden


def test_external_manifest_digest_covers_declarative_behavior() -> None:
    manifest = EXTERNAL_SMOKE_MANIFEST
    changed = replace(
        manifest,
        cases=(replace(manifest.cases[0], max_turns=manifest.cases[0].max_turns - 1), *manifest.cases[1:]),
    )
    assert external_manifest_digest(manifest) != external_manifest_digest(changed)

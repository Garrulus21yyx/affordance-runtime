from dataclasses import replace

import pytest

from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkManifest,
    MetricExpectation,
    MetricExpectationOperator,
)
from affordance_runtime.benchmarks.target_loop.manifest import get_manifest, manifest_digest


def test_manifest_digest_covers_profile_seed_and_expectations() -> None:
    manifest = get_manifest("internal-core", "deterministic", 7)
    expectations = tuple(
        MetricExpectation("executions", MetricExpectationOperator.MAX, 2)
        if item.metric == "executions" else item
        for item in manifest.cases[0].metric_expectations
    )
    changed_case = replace(manifest.cases[0], metric_expectations=expectations)
    changed = replace(manifest, cases=(changed_case, *manifest.cases[1:]))

    assert manifest_digest(manifest) != manifest_digest(changed)
    assert manifest_digest(manifest) != manifest_digest(replace(manifest, profile_id="other"))
    reseeded = replace(
        manifest, seed=8, cases=tuple(replace(item, seed=8) for item in manifest.cases)
    )
    assert manifest_digest(manifest) != manifest_digest(reseeded)


def test_manifest_rejects_duplicate_or_mismatched_cases() -> None:
    manifest = get_manifest("internal-core", "deterministic", 7)
    with pytest.raises(ValueError):
        BenchmarkManifest(
            manifest.schema_version, manifest.suite_id, manifest.profile_id,
            manifest.seed, (manifest.cases[0], manifest.cases[0]),
        )
    with pytest.raises(ValueError):
        replace(manifest, cases=(replace(manifest.cases[0], suite_id="wrong"),))

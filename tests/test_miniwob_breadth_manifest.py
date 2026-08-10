from __future__ import annotations

from dataclasses import replace

import pytest

from affordance_runtime.benchmarks.external_breadth.capability_inventory import (
    PRIMITIVE_VOCABULARY,
    build_capability_inventory,
    capability_inventory_digest,
    supported_candidates,
)
from affordance_runtime.benchmarks.external_breadth.manifest import (
    SEED,
    breadth_manifest_digest,
    build_breadth_manifest,
)
from affordance_runtime.benchmarks.external_breadth.registry import load_registry_census, registry_digest
from affordance_runtime.benchmarks.external_breadth.selection import select_tasks, selection_key


def _census():
    try:
        return load_registry_census()
    except RuntimeError as exc:
        pytest.skip(str(exc))


def test_actual_pinned_registry_and_inventory_are_deterministic() -> None:
    census = _census()
    assert census.package_version == census.core_version == "0.14.3"
    assert len(census.task_ids) == 125
    assert census.registry_digest == registry_digest(tuple(reversed(census.task_ids)))
    first = build_capability_inventory(census)
    second = build_capability_inventory(census)
    assert first == second
    assert capability_inventory_digest(first) == capability_inventory_digest(second)
    assert all(set(item.required_primitives) <= PRIMITIVE_VOCABULARY for item in first)
    serialized = repr(first).casefold()
    assert "expected_answer" not in serialized
    assert "reference_trajectory" not in serialized


def test_selection_is_hash_ordered_unique_and_independent_of_environment_seed() -> None:
    census = _census()
    candidates = supported_candidates(build_capability_inventory(census))
    assert len(candidates) >= 60
    selected = select_tasks(tuple(reversed(candidates)))
    assert len(selected) == len({item.task_id for item in selected}) == 60
    assert tuple(item.task_id for item in selected) == tuple(
        item.task_id for item in select_tasks(candidates)
    )
    assert tuple(selection_key(item.task_id) for item in selected) == tuple(
        sorted(selection_key(item.task_id) for item in candidates)[:60]
    )
    manifest = build_breadth_manifest(census)
    assert {item.seed for item in manifest.cases} == {SEED}


def test_manifest_digest_binds_cases_seed_model_and_pacing() -> None:
    manifest = build_breadth_manifest(_census())
    assert len(manifest.cases) == 60
    digest = breadth_manifest_digest(manifest)
    changed_case = replace(manifest.cases[0], task_id="browsergym/miniwob.changed")
    assert breadth_manifest_digest(replace(manifest, cases=(changed_case, *manifest.cases[1:]))) != digest
    assert breadth_manifest_digest(replace(manifest, minimum_policy_call_interval_s=8.0)) != digest
    assert breadth_manifest_digest(replace(manifest, model_profile="different-model")) != digest
    assert breadth_manifest_digest(
        replace(manifest, cases=tuple(replace(item, seed=8) for item in manifest.cases))
    ) != digest

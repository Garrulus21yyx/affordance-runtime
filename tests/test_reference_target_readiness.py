from __future__ import annotations

import pytest

from affordance_runtime.benchmarks.target_loop.reference_readiness import (
    REFERENCE_TARGET_READINESS,
    ReferenceTargetBlocker,
    ReferenceTargetCutoverBlockedError,
    ReferenceTargetReadiness,
    require_reference_target_cutover_ready,
)


def test_every_root_reference_scenario_has_explicit_typed_readiness() -> None:
    assert tuple(item.scenario for item in REFERENCE_TARGET_READINESS) == (
        "pricing",
        "settings",
        "export",
    )
    assert [item.scenario for item in REFERENCE_TARGET_READINESS if item.ready] == [
        "pricing",
        "settings",
    ]
    assert all(item.blockers for item in REFERENCE_TARGET_READINESS if not item.ready)
    assert all(
        isinstance(blocker, ReferenceTargetBlocker)
        for item in REFERENCE_TARGET_READINESS
        for blocker in item.blockers
    )


def test_current_reference_default_cutover_fails_with_deterministic_evidence() -> None:
    with pytest.raises(ReferenceTargetCutoverBlockedError) as caught:
        require_reference_target_cutover_ready()

    assert tuple(item.scenario for item in caught.value.readiness) == (
        "export",
    )
    assert str(caught.value) == (
        "target reference cutover is blocked: "
        "export=[materialized_download_required,output_integrity_evidence_required]"
    )


def test_cutover_gate_requires_all_scenarios_and_executable_acceptance() -> None:
    ready = tuple(
        ReferenceTargetReadiness(item.scenario, frozenset(), f"test:{item.scenario}")
        for item in REFERENCE_TARGET_READINESS
    )

    require_reference_target_cutover_ready(ready)

    with pytest.raises(ValueError, match="exactly all root scenarios"):
        require_reference_target_cutover_ready(ready[:2])
    with pytest.raises(ValueError, match="requires one executable"):
        ReferenceTargetReadiness("settings", frozenset())


def test_settings_readiness_names_the_executable_target_acceptance() -> None:
    settings = next(item for item in REFERENCE_TARGET_READINESS if item.scenario == "settings")

    assert settings.ready
    assert settings.blockers == frozenset()
    assert settings.target_acceptance_test == (
        "tests/test_reference_target_settings.py::"
        "test_target_settings_confirms_action_then_completes_from_unified_authoritative_world"
    )


def test_pricing_readiness_names_the_executable_target_acceptance() -> None:
    pricing = next(item for item in REFERENCE_TARGET_READINESS if item.scenario == "pricing")

    assert pricing.ready
    assert pricing.blockers == frozenset()
    assert pricing.target_acceptance_test == (
        "tests/test_reference_target_pricing.py::"
        "test_target_pricing_reveals_records_and_returns_current_structured_dom_output"
    )

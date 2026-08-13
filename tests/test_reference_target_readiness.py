from __future__ import annotations

import pytest

from affordance_runtime.reference_target_readiness import (
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
    assert all(not item.ready for item in REFERENCE_TARGET_READINESS)
    assert all(item.blockers for item in REFERENCE_TARGET_READINESS)
    assert all(
        isinstance(blocker, ReferenceTargetBlocker)
        for item in REFERENCE_TARGET_READINESS
        for blocker in item.blockers
    )


def test_current_reference_default_cutover_fails_with_deterministic_evidence() -> None:
    with pytest.raises(ReferenceTargetCutoverBlockedError) as caught:
        require_reference_target_cutover_ready()

    assert tuple(item.scenario for item in caught.value.readiness) == (
        "pricing",
        "settings",
        "export",
    )
    assert str(caught.value) == (
        "target reference cutover is blocked: "
        "pricing=[interaction_effect_boundary_required,structural_document_content_required,"
        "structured_output_projection_required], "
        "settings=[authoritative_http_state_source_required], "
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


def test_confirmation_does_not_erase_settings_completion_evidence_blocker() -> None:
    settings = next(item for item in REFERENCE_TARGET_READINESS if item.scenario == "settings")

    assert settings.blockers == frozenset({ReferenceTargetBlocker.AUTHORITATIVE_HTTP_STATE})

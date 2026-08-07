from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from affordance_runtime.benchmarks import generalization as legacy_generalization
from affordance_runtime.benchmarks.generalization_evidence import (
    GeneralizationControl,
    GeneralizationEvidenceCase,
    GeneralizationEvidenceReport,
    GeneralizationEvidenceSource,
    GeneralizationExpectedOutcome,
    GeneralizationProfileIdentity,
    GeneralizationProfileKind,
    write_generalization_evidence_report,
)
from affordance_runtime.generalist_planner import (
    historical_compatibility_semantic_compiler_registry,
)
from affordance_runtime.semantic_compilers import SemanticCompilerRegistry
from scripts.check_evidence import validate_generalization_evidence


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _profiles() -> tuple[GeneralizationProfileIdentity, ...]:
    strict_registry = _digest("1")
    return (
        GeneralizationProfileIdentity.create(
            kind=GeneralizationProfileKind.STRICT_GENERALIST,
            revision="revision-g5",
            planner_profile="strict-generalist",
            registry_digest=strict_registry,
        ),
        GeneralizationProfileIdentity.create(
            kind=GeneralizationProfileKind.STRICT_PLUS_ACCEPTED_SKILLS,
            revision="revision-g5",
            planner_profile="strict-generalist",
            registry_digest=strict_registry,
            accepted_profile_digest=_digest("2"),
            accepted_artifact_ids=("accepted-profile-save",),
        ),
        GeneralizationProfileIdentity.create(
            kind=GeneralizationProfileKind.HISTORICAL_COMPATIBILITY,
            revision="revision-g5",
            planner_profile="historical-compatibility",
            registry_digest=_digest("3"),
        ),
        GeneralizationProfileIdentity.create(
            kind=GeneralizationProfileKind.DECLARED_ABLATIONS,
            revision="revision-g5",
            planner_profile="declared-ablation",
            registry_digest=strict_registry,
            ablation_dimensions=("dom-only", "visual-only"),
        ),
    )


def _case(
    profile: GeneralizationProfileIdentity,
    case_id: str,
    comparison_key: str,
    *,
    source: GeneralizationEvidenceSource,
    controls: tuple[GeneralizationControl, ...],
    task_success: bool,
    expected: GeneralizationExpectedOutcome = GeneralizationExpectedOutcome.TASK_SUCCESS,
    planner_calls: int = 1,
    model_calls: int = 1,
    **updates: object,
) -> GeneralizationEvidenceCase:
    values: dict[str, object] = {
        "case_id": case_id,
        "comparison_key": comparison_key,
        "profile_identity_digest": profile.identity_digest,
        "source": source,
        "controls": controls,
        "expected_outcome": expected,
        "task_success": task_success,
        "safe_outcome": True,
        "planner_calls": planner_calls,
        "model_calls": model_calls,
        "effect_count": 1 if task_success else 0,
        "unauthorized_effect_count": 0,
        "unapproved_high_risk_effect_count": 0,
        "scope_expansion_count": 0,
        "duplicate_effect_count": 0,
        "verifier_false_accept_count": 0,
        "evidence_refs": (f"pytest:{case_id}",),
    }
    values.update(updates)
    return GeneralizationEvidenceCase.model_validate(values)


def _portfolio() -> tuple[
    tuple[GeneralizationProfileIdentity, ...],
    tuple[GeneralizationEvidenceCase, ...],
]:
    profiles = _profiles()
    strict, skilled, compatibility, ablation = profiles
    cases = (
        _case(
            strict,
            "strict-unseen-save",
            "skill-save",
            source=GeneralizationEvidenceSource.LOCAL_UNSEEN,
            controls=(
                GeneralizationControl.UNSEEN_LAYOUT,
                GeneralizationControl.UNSEEN_VOCABULARY,
                GeneralizationControl.DOM,
                GeneralizationControl.ACCESSIBILITY,
            ),
            task_success=True,
            planner_calls=2,
            model_calls=2,
        ),
        _case(
            strict,
            "strict-governance-controls",
            "governance-negative",
            source=GeneralizationEvidenceSource.SYNTHETIC_CONTROL,
            controls=(
                GeneralizationControl.PARAPHRASE,
                GeneralizationControl.DISTRACTOR,
                GeneralizationControl.AMBIGUITY,
                GeneralizationControl.EXTRA_CONTROLS,
                GeneralizationControl.SAFETY_SCOPE,
            ),
            task_success=False,
            expected=GeneralizationExpectedOutcome.SAFE_LIMIT,
        ),
        _case(
            strict,
            "strict-cross-surface",
            "route-ablation",
            source=GeneralizationEvidenceSource.CROSS_SURFACE,
            controls=(
                GeneralizationControl.SVG,
                GeneralizationControl.VISUAL,
                GeneralizationControl.WOT,
            ),
            task_success=True,
            planner_calls=2,
            model_calls=1,
        ),
        _case(
            strict,
            "strict-provider-recovery",
            "fault-recovery",
            source=GeneralizationEvidenceSource.FAULT_INJECTION,
            controls=(
                GeneralizationControl.PROVIDER_CONTEXT,
                GeneralizationControl.RECOVERY_INJECTION,
            ),
            task_success=True,
        ),
        _case(
            strict,
            "strict-compatibility-boundary",
            "compat-form",
            source=GeneralizationEvidenceSource.SYNTHETIC_CONTROL,
            controls=(GeneralizationControl.SAFETY_SCOPE,),
            task_success=False,
            expected=GeneralizationExpectedOutcome.SAFE_LIMIT,
            planner_calls=1,
            model_calls=1,
        ),
        _case(
            skilled,
            "skilled-unseen-save",
            "skill-save",
            source=GeneralizationEvidenceSource.LOCAL_UNSEEN,
            controls=(GeneralizationControl.UNSEEN_LAYOUT, GeneralizationControl.DOM),
            task_success=True,
            planner_calls=0,
            model_calls=0,
        ),
        _case(
            compatibility,
            "compatibility-form",
            "compat-form",
            source=GeneralizationEvidenceSource.SYNTHETIC_CONTROL,
            controls=(GeneralizationControl.SAFETY_SCOPE,),
            task_success=True,
            planner_calls=0,
            model_calls=0,
        ),
        _case(
            ablation,
            "ablation-dom-only-visual-limit",
            "route-ablation",
            source=GeneralizationEvidenceSource.CROSS_SURFACE,
            controls=(GeneralizationControl.VISUAL,),
            task_success=False,
            expected=GeneralizationExpectedOutcome.SAFE_LIMIT,
            planner_calls=0,
            model_calls=0,
        ),
    )
    return profiles, cases


def test_four_profile_report_passes_with_local_controls_and_visible_uplifts() -> None:
    profiles, cases = _portfolio()

    report = GeneralizationEvidenceReport.build(
        profiles=profiles,
        cases=cases,
        external_evidence_gaps=("public-suite-assets-not-independently-provisioned",),
    )

    assert report.acceptance == "passed"
    assert report.acceptance_errors == ()
    assert report.external_confirmation_status == "unprovisioned"
    assert report.official_score_claimed is False
    assert report.benchmark_score_used_as_sole_evidence is False
    assert set(report.metrics) == {item.value for item in GeneralizationProfileKind}
    comparisons = {item.candidate: item for item in report.comparisons}
    assert comparisons[GeneralizationProfileKind.STRICT_PLUS_ACCEPTED_SKILLS].planner_call_reduction > 0
    assert comparisons[GeneralizationProfileKind.HISTORICAL_COMPATIBILITY].task_success_delta > 0
    assert comparisons[GeneralizationProfileKind.DECLARED_ABLATIONS].task_success_delta < 0
    assert GeneralizationEvidenceReport.model_validate_json(report.model_dump_json()) == report


def test_missing_strict_control_and_source_fails_claim_without_hiding_cases() -> None:
    profiles, cases = _portfolio()
    reduced = tuple(
        item
        for item in cases
        if item.case_id not in {"strict-cross-surface", "ablation-dom-only-visual-limit"}
    )

    report = GeneralizationEvidenceReport.build(profiles=profiles, cases=reduced)

    assert report.acceptance == "failed"
    assert any("missing controls" in item for item in report.acceptance_errors)
    assert any("cross_surface" in item for item in report.acceptance_errors)


def test_safety_regression_and_no_skill_uplift_fail_profile_comparison() -> None:
    profiles, cases = _portfolio()
    changed: list[GeneralizationEvidenceCase] = []
    for item in cases:
        if item.case_id == "skilled-unseen-save":
            changed.append(
                item.model_copy(
                    update={
                        "planner_calls": 2,
                        "model_calls": 2,
                        "unauthorized_effect_count": 1,
                    }
                )
            )
        else:
            changed.append(item)

    report = GeneralizationEvidenceReport.build(profiles=profiles, cases=changed)

    assert report.acceptance == "failed"
    assert any("safety regression" in item for item in report.acceptance_errors)
    assert any("show no success or efficiency uplift" in item for item in report.acceptance_errors)


def test_profile_identity_rejects_hidden_compatibility_or_unaccepted_skill() -> None:
    strict = _profiles()[0]
    with pytest.raises(ValidationError, match="strict-generalist planner profile"):
        GeneralizationProfileIdentity.create(
            kind=GeneralizationProfileKind.STRICT_GENERALIST,
            revision="revision-g5",
            planner_profile="historical-compatibility",
            registry_digest=strict.registry_digest,
        )


def test_profile_identities_bind_real_strict_and_compatibility_registry_digests() -> None:
    strict_registry = SemanticCompilerRegistry.disabled().digest
    compatibility_registry = historical_compatibility_semantic_compiler_registry().digest

    strict = GeneralizationProfileIdentity.create(
        kind=GeneralizationProfileKind.STRICT_GENERALIST,
        revision="revision-g5",
        planner_profile="strict-generalist",
        registry_digest=strict_registry,
    )
    compatibility = GeneralizationProfileIdentity.create(
        kind=GeneralizationProfileKind.HISTORICAL_COMPATIBILITY,
        revision="revision-g5",
        planner_profile="historical-compatibility",
        registry_digest=compatibility_registry,
    )

    assert strict.registry_digest == strict_registry
    assert compatibility.registry_digest == compatibility_registry
    assert strict.registry_digest != compatibility.registry_digest
    with pytest.raises(ValidationError, match="explicit artifact ids"):
        GeneralizationProfileIdentity.create(
            kind=GeneralizationProfileKind.STRICT_PLUS_ACCEPTED_SKILLS,
            revision="revision-g5",
            planner_profile="strict-generalist",
            registry_digest=strict.registry_digest,
        )


def test_external_case_requires_independent_environment_and_asset_digests() -> None:
    strict = _profiles()[0]
    with pytest.raises(ValidationError, match="environment_digest"):
        _case(
            strict,
            "external-unbound",
            "external",
            source=GeneralizationEvidenceSource.EXTERNAL_PROVISIONED,
            controls=(GeneralizationControl.DOM,),
            task_success=True,
        )


def test_tampered_aggregate_or_score_claim_is_rejected() -> None:
    profiles, cases = _portfolio()
    report = GeneralizationEvidenceReport.build(profiles=profiles, cases=cases)
    strict_metrics = report.metrics[GeneralizationProfileKind.STRICT_GENERALIST.value]
    tampered_metrics = {
        **report.metrics,
        GeneralizationProfileKind.STRICT_GENERALIST.value: strict_metrics.model_copy(
            update={"task_success_rate": 1.0}
        ),
    }
    with pytest.raises(ValidationError, match="aggregates disagree"):
        GeneralizationEvidenceReport.model_validate(
            {**report.model_dump(), "metrics": tampered_metrics}
        )
    with pytest.raises(ValidationError, match="cannot use or promote"):
        GeneralizationEvidenceReport.model_validate(
            {**report.model_dump(), "official_score_claimed": True}
        )


def test_legacy_generalization_aggregate_is_diagnostic_only(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    training_path = tmp_path / "training.json"
    training_path.write_text(
        json.dumps(
            {
                "metrics_by_variant": {"full_runtime": {"task_success_rate": 1.0}},
                "runs": [
                    {"seed": seed, "fixture_variant": f"variant-{seed}", "variant": "full_runtime"}
                    for seed in range(3)
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        legacy_generalization,
        "run_heldout_local_suite",
        lambda _path: SimpleNamespace(
            runs=(SimpleNamespace(success=True),), acceptance_errors=[]
        ),
    )
    monkeypatch.setattr(
        legacy_generalization,
        "run_visual_grounding_suite",
        lambda _path: {"runs": [{}], "success_rate": 1.0, "acceptance_errors": []},
    )

    summary = legacy_generalization.write_generalization_summary(
        tmp_path / "output",
        training_report_path=training_path,
        miniwob_report={"episodes": [{}], "success_rate": 1.0, "acceptance_errors": []},
    )

    assert summary["diagnostic_errors"] == []
    assert summary["acceptance"] == "incomplete"
    assert summary["governance_status"] == "legacy_unsegregated_diagnostic"
    assert summary["g5_evidence_eligible"] is False
    assert summary["official_score_claimed"] is False
    assert any("four-profile" in item for item in summary["acceptance_errors"])
    validate_generalization_evidence(summary)
    with pytest.raises(RuntimeError, match="invalid G5 or score claim"):
        validate_generalization_evidence({**summary, "official_score_claimed": True})


def test_validated_report_publication_round_trips_without_score_claim(tmp_path) -> None:
    profiles, cases = _portfolio()
    report = GeneralizationEvidenceReport.build(
        profiles=profiles,
        cases=cases,
        external_evidence_gaps=("workarena-instance-not-independently-provisioned",),
    )

    json_path, markdown_path = write_generalization_evidence_report(tmp_path, report)

    assert GeneralizationEvidenceReport.model_validate_json(json_path.read_text()) == report
    markdown = markdown_path.read_text()
    assert "Official score claimed: `false`" in markdown
    assert "External confirmation: `unprovisioned`" in markdown
    assert not list(tmp_path.glob(".*.tmp"))
    validate_generalization_evidence(report.model_dump(mode="json"))

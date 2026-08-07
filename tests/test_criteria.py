from dataclasses import replace

from affordance_runtime.contracts import (
    ExecutionReceipt,
    Observation,
    ProgressEvidenceScope,
    VerifierSpec,
)
from affordance_runtime.criteria import criterion_id, evidence_requirement_id
from affordance_runtime.legacy_criteria_evidence import (
    CriteriaEvidenceMatcher,
    criteria_from_descriptions,
    evidence_requirements_from_descriptions,
)
from affordance_runtime.verification.mechanical import (
    VerificationEvidence,
    VerificationReport,
    VerificationStatus,
    VerifierLadder,
)


def _observation(*, revision: str = "revision-2", snapshot: str = "snapshot-2") -> Observation:
    return Observation(revision, snapshot_id=snapshot)


def _evidence(
    *,
    criterion_ids: tuple[str, ...],
    requirement_ids: tuple[str, ...],
    revision: str = "revision-2",
    snapshot: str = "snapshot-2",
    strength: str = "strong",
) -> VerificationEvidence:
    return VerificationEvidence(
        "observation_metadata",
        "profile",
        True,
        "post_action_observation",
        evidence_id="profile-state-v1",
        criterion_ids=criterion_ids,
        requirement_ids=requirement_ids,
        environment_revision=revision,
        snapshot_id=snapshot,
        strength=strength,
    )


def _match(
    evidence: VerificationEvidence,
    *,
    criterion_count: int = 1,
    requirement_count: int = 1,
):  # type: ignore[no-untyped-def]
    criteria = criteria_from_descriptions(
        "subgoal",
        "profile",
        tuple(f"criterion {index}" for index in range(criterion_count)),
    )
    requirements = evidence_requirements_from_descriptions(
        "subgoal",
        "profile",
        tuple(f"evidence requirement {index}" for index in range(requirement_count)),
    )
    return CriteriaEvidenceMatcher().match(
        criteria=criteria,
        requirements=requirements,
        verification=VerificationReport(VerificationStatus.PASSED, [evidence]),
        observation=_observation(),
    )


def test_unrelated_passed_evidence_cannot_advance_progress() -> None:
    report = _match(
        _evidence(
            criterion_ids=(criterion_id("subgoal", "another", 0),),
            requirement_ids=(evidence_requirement_id("subgoal", "another", 0),),
        )
    )

    assert not report.passed
    assert report.matched_criterion_ids == ()
    assert report.rejected_evidence[0].reason.startswith("evidence has no explicit link")


def test_partial_criteria_remain_pending() -> None:
    report = _match(
        _evidence(
            criterion_ids=(criterion_id("subgoal", "profile", 0),),
            requirement_ids=(evidence_requirement_id("subgoal", "profile", 0),),
        ),
        criterion_count=2,
    )

    assert not report.passed
    assert report.matched_criterion_ids == (criterion_id("subgoal", "profile", 0),)
    assert report.unmatched_criterion_ids == (criterion_id("subgoal", "profile", 1),)


def test_stale_evidence_is_rejected() -> None:
    report = _match(
        _evidence(
            criterion_ids=(criterion_id("subgoal", "profile", 0),),
            requirement_ids=(evidence_requirement_id("subgoal", "profile", 0),),
            revision="revision-1",
            snapshot="snapshot-1",
        )
    )

    assert not report.passed
    assert report.rejected_evidence[0].reason == "evidence environment revision is stale"


def test_evidence_from_an_old_snapshot_in_the_same_revision_is_rejected() -> None:
    report = _match(
        _evidence(
            criterion_ids=(criterion_id("subgoal", "profile", 0),),
            requirement_ids=(evidence_requirement_id("subgoal", "profile", 0),),
            snapshot="snapshot-1",
        )
    )

    assert not report.passed
    assert report.rejected_evidence[0].reason == "evidence observation snapshot is stale"


def test_weak_execution_evidence_is_rejected() -> None:
    report = _match(
        _evidence(
            criterion_ids=(criterion_id("subgoal", "profile", 0),),
            requirement_ids=(evidence_requirement_id("subgoal", "profile", 0),),
            strength="weak",
        )
    )

    assert not report.passed
    assert report.rejected_evidence[0].reason == "evidence is weak and not independent of execution"


def test_execution_receipt_cannot_self_declare_strong_evidence() -> None:
    evidence = _evidence(
        criterion_ids=(criterion_id("subgoal", "profile", 0),),
        requirement_ids=(evidence_requirement_id("subgoal", "profile", 0),),
        strength="strong",
    )
    evidence = replace(evidence, source="execution_receipt")

    report = _match(evidence)

    assert not report.passed
    assert report.rejected_evidence[0].reason == "evidence is weak and not independent of execution"


def test_one_evidence_item_may_cover_multiple_criteria_only_via_explicit_links() -> None:
    criterion_ids = tuple(criterion_id("subgoal", "profile", index) for index in range(2))
    report = _match(
        _evidence(
            criterion_ids=criterion_ids,
            requirement_ids=(evidence_requirement_id("subgoal", "profile", 0),),
        ),
        criterion_count=2,
    )

    assert report.passed
    assert report.matched_criterion_ids == criterion_ids
    assert {link.evidence_id for link in report.links} == {"profile-state-v1"}


def test_all_mandatory_evidence_requirements_must_be_covered() -> None:
    report = _match(
        _evidence(
            criterion_ids=(criterion_id("subgoal", "profile", 0),),
            requirement_ids=(evidence_requirement_id("subgoal", "profile", 0),),
        ),
        requirement_count=2,
    )

    assert not report.passed
    assert report.unmatched_requirement_ids == (evidence_requirement_id("subgoal", "profile", 1),)


def test_verifier_ladder_preserves_explicit_identity_and_current_epoch() -> None:
    observation = _observation()
    criterion = criterion_id("subgoal", "profile", 0)
    requirement = evidence_requirement_id("subgoal", "profile", 0)
    report = VerifierLadder().verify_report(
        [
            VerifierSpec(
                "observation_metadata",
                "saved",
                True,
                evidence_key="saved-state",
                criterion_ids=(criterion,),
                requirement_ids=(requirement,),
            )
        ],
        ExecutionReceipt(
            "contract-1",
            "synthetic",
            True,
            "revision-1",
            "revision-2",
            1.0,
        ),
        Observation(
            observation.environment_revision,
            snapshot_id=observation.snapshot_id,
            metadata={"saved": True},
        ),
    )

    assert report.passed
    assert report.evidence[0].evidence_id == "verification:snapshot-2:0:saved-state"
    assert report.evidence[0].criterion_ids == (criterion,)
    assert report.evidence[0].requirement_ids == (requirement,)
    assert report.evidence[0].environment_revision == "revision-2"
    assert report.evidence[0].snapshot_id == "snapshot-2"
    assert report.evidence[0].strength == "strong"


def test_state_delta_or_terminal_is_weak_progress_evidence() -> None:
    observation = _observation()
    report = VerifierLadder().verify_report(
        [VerifierSpec("state_delta_or_terminal", "save")],
        ExecutionReceipt(
            "contract-1",
            "synthetic",
            True,
            "revision-1",
            "revision-2",
            1.0,
        ),
        observation,
    )

    assert report.passed
    assert report.evidence[0].strength == "weak"


def test_task_terminal_scope_releases_links_only_with_independent_terminal_evidence() -> None:
    observation = Observation("revision-2", snapshot_id="snapshot-2", metadata={"saved": True})
    criterion = criterion_id("subgoal", "profile", 0)
    requirement = evidence_requirement_id("subgoal", "profile", 0)
    spec = VerifierSpec(
        "observation_metadata",
        "saved",
        True,
        criterion_ids=(criterion,),
        requirement_ids=(requirement,),
        progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
    )
    ordinary = VerifierLadder().verify_report(
        [spec],
        ExecutionReceipt("contract", "test", True, "revision-1", "revision-2", 1.0),
        observation,
    )
    terminal = VerifierLadder().verify_report(
        [spec],
        ExecutionReceipt(
            "contract",
            "test",
            True,
            "revision-1",
            "revision-2",
            1.0,
            evidence={"terminal_success": True},
        ),
        observation,
    )
    failed_terminal = VerifierLadder().verify_report(
        [spec],
        ExecutionReceipt(
            "contract",
            "test",
            True,
            "revision-1",
            "revision-2",
            1.0,
            evidence={"terminal_failure": True},
        ),
        observation,
    )

    assert ordinary.passed
    assert ordinary.evidence[0].criterion_ids == ()
    assert ordinary.evidence[0].requirement_ids == ()
    assert terminal.passed
    assert terminal.evidence[0].criterion_ids == (criterion,)
    assert terminal.evidence[0].requirement_ids == (requirement,)
    assert terminal.evidence[0].source == "post_action_observation"
    assert terminal.evidence[0].strength == "strong"
    assert failed_terminal.passed
    assert failed_terminal.evidence[0].criterion_ids == ()
    assert failed_terminal.evidence[0].requirement_ids == ()


def test_terminal_success_does_not_outrank_receipt_verifier_provenance() -> None:
    criterion = criterion_id("subgoal", "profile", 0)
    requirement = evidence_requirement_id("subgoal", "profile", 0)
    report = VerifierLadder().verify_report(
        [
            VerifierSpec(
                "evidence",
                "last_action_error",
                "",
                criterion_ids=(criterion,),
                requirement_ids=(requirement,),
                progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
            )
        ],
        ExecutionReceipt(
            "contract",
            "browsergym",
            True,
            "revision-1",
            "revision-2",
            1.0,
            evidence={"last_action_error": "", "terminal_success": True},
        ),
        Observation("revision-2", snapshot_id="snapshot-2"),
    )

    assert report.passed
    assert report.evidence[0].source == "execution_receipt"
    assert report.evidence[0].strength == "weak"
    assert report.evidence[0].criterion_ids == (criterion,)
    assert report.evidence[0].requirement_ids == (requirement,)

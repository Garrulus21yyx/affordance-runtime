from types import SimpleNamespace

from affordance_runtime.evaluation import (
    ActionOutcome,
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
)
from affordance_runtime.evaluation.action_applicability import apply_action_evidence_profile
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution import ActionIntent
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
    WorldObservation,
)
from tests.support.world import fused_world


def _world(identity: str, value: bool, profile: ObservationSourceProfile, *, unrelated: bool = False) -> WorldObservation:
    subject = "other:1" if unrelated else "target:1"
    fact = StateFact(f"fact:{identity}", subject, "enabled", value, f"source:{identity}")
    source = SurfaceObservation(
        f"source:{identity}", profile.debug_source, f"revision:{identity}", profile,
        targets=(SemanticTarget(subject, "state", subject, {"enabled": value}),),
        facts=(fact,),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def _request(*, expected_outcome: str = ""):
    return SimpleNamespace(intent=ActionIntent("activate", "target:1", expected_outcome=expected_outcome))


def _task():
    return TaskGoal(
        "effect", "Enable target",
        success_criteria=({"id": "enabled", "subject_id": "target:1", "predicate": "enabled", "value": True},),
    )


def _apply(proposal, request, before, after):
    return apply_action_evidence_profile(
        proposal, request, before, after, WorldEvidenceIndex.from_observation(after),
    )


def test_changed_relevant_fact_supports_effect_but_unrelated_fact_does_not() -> None:
    before = _world("before", False, ObservationSourceProfile.dom())
    after = _world("after", True, ObservationSourceProfile.dom())
    unrelated = _world("unrelated", True, ObservationSourceProfile.dom(), unrelated=True)
    proposal = ActionOutcome(
        "request:1", before.observation_id, after.observation_id,
        ObservedChange.CHANGED,
        LocalPostconditionStatus.UNKNOWN,
        EvidenceMethod.STRUCTURAL,
        "changed", ("fact:after",)
    )

    accepted = _apply(proposal, _request(), before, after)
    rejected = _apply(
        ActionOutcome(
            "request:1", before.observation_id, unrelated.observation_id,
            ObservedChange.CHANGED,
            LocalPostconditionStatus.UNKNOWN,
            EvidenceMethod.STRUCTURAL,
            "changed", ("fact:unrelated",),
        ),
        _request(), before, unrelated,
    )
    assert accepted.observed_change == ObservedChange.CHANGED
    assert rejected.observed_change == ObservedChange.CHANGED


def test_after_only_fact_without_matching_before_predicate_cannot_support_effect() -> None:
    before = fused_world("before", surface="dom")
    after = _world("after", True, ObservationSourceProfile.dom())
    proposal = ActionOutcome(
        "request:1", "before", "after",
        ObservedChange.CHANGED,
        LocalPostconditionStatus.UNKNOWN,
        EvidenceMethod.STRUCTURAL,
        "appeared", ("fact:after",),
    )

    result = _apply(proposal, _request(), before, after)

    assert result.observed_change == ObservedChange.CHANGED


def test_weak_visual_unchanged_cannot_prove_no_effect_but_strong_sources_can() -> None:
    for profile, expected in (
        (ObservationSourceProfile.visual(), ObservedChange.UNKNOWN),
        (ObservationSourceProfile.dom(), ObservedChange.UNCHANGED),
        (ObservationSourceProfile.wot(), ObservedChange.UNCHANGED),
    ):
        before = _world(f"before-{profile.debug_source}", False, profile)
        after = _world(f"after-{profile.debug_source}", False, profile)
        proposal = ActionOutcome(
            "request:1", before.observation_id, after.observation_id,
            ObservedChange.UNCHANGED,
            LocalPostconditionStatus.UNKNOWN,
            EvidenceMethod.STRUCTURAL,
            "unchanged", (f"fact:after-{profile.debug_source}",)
        )
        result = _apply(proposal, _request(), before, after)
        assert result.observed_change == expected


def test_current_after_only_scoped_artifact_supports_creation_effect() -> None:
    before = _world("before", False, ObservationSourceProfile.dom())
    source = SurfaceObservation(
        "source:after", "dom", "revision:after", ObservationSourceProfile.dom(),
        artifacts={"report": {"public_summary": "report created"}},
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    after = fused.observation
    evidence_ref = "artifact:source:after:report"
    proposal = ActionOutcome(
        "request:1", "before", "after",
        ObservedChange.CHANGED,
        LocalPostconditionStatus.UNKNOWN,
        EvidenceMethod.STRUCTURAL,
        "created", (evidence_ref,),
    )

    request = _request(expected_outcome="report artifact is created")
    result = apply_action_evidence_profile(
        proposal, request, before, after, WorldEvidenceIndex.from_observation(after),
    )

    assert result.observed_change == ObservedChange.UNKNOWN

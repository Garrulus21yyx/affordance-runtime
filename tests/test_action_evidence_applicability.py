from types import SimpleNamespace

from affordance_runtime.evaluation import ActionEvaluation, ActionEvaluationStatus
from affordance_runtime.evaluation.action_applicability import apply_action_evidence_profile
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution import ActionIntent
from affordance_runtime.world import (
    CoverageState,
    ObservationSourceProfile,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)


def _world(identity: str, value: bool, profile: ObservationSourceProfile, *, unrelated: bool = False) -> WorldObservation:
    subject = "other:1" if unrelated else "target:1"
    fact = StateFact(f"fact:{identity}", subject, "enabled", value, f"source:{identity}")
    source = SurfaceObservation(
        f"source:{identity}", profile.debug_source, f"revision:{identity}", profile, facts=(fact,)
    )
    return WorldObservation(identity, (), (fact,), (), {source.surface: CoverageState.COMPLETE}, sources=(source,))


def _request(*, expected_outcome=None):
    return SimpleNamespace(intent=ActionIntent("activate", "target:1", expected_outcome=expected_outcome or {}))


def test_changed_relevant_fact_supports_effect_but_unrelated_fact_does_not() -> None:
    before = _world("before", False, ObservationSourceProfile.dom())
    after = _world("after", True, ObservationSourceProfile.dom())
    unrelated = _world("unrelated", True, ObservationSourceProfile.dom(), unrelated=True)
    proposal = ActionEvaluation(
        "request:1", before.observation_id, after.observation_id,
        ActionEvaluationStatus.EFFECT_CONFIRMED, "changed", ("fact:after",)
    )

    accepted = apply_action_evidence_profile(proposal, _request(), before, after, WorldEvidenceIndex.from_observation(after))
    rejected = apply_action_evidence_profile(
        ActionEvaluation("request:1", before.observation_id, unrelated.observation_id, ActionEvaluationStatus.EFFECT_CONFIRMED, "changed", ("fact:unrelated",)),
        _request(), before, unrelated, WorldEvidenceIndex.from_observation(unrelated)
    )
    assert accepted.status == ActionEvaluationStatus.EFFECT_CONFIRMED
    assert rejected.status == ActionEvaluationStatus.UNKNOWN


def test_after_only_fact_without_matching_before_predicate_cannot_support_effect() -> None:
    before = WorldObservation("before", (), (), (), {"dom": CoverageState.COMPLETE})
    after = _world("after", True, ObservationSourceProfile.dom())
    proposal = ActionEvaluation(
        "request:1", "before", "after", ActionEvaluationStatus.EFFECT_CONFIRMED,
        "appeared", ("fact:after",),
    )

    result = apply_action_evidence_profile(
        proposal, _request(), before, after, WorldEvidenceIndex.from_observation(after)
    )

    assert result.status == ActionEvaluationStatus.UNKNOWN


def test_weak_visual_unchanged_cannot_prove_no_effect_but_strong_sources_can() -> None:
    for profile, expected in (
        (ObservationSourceProfile.visual(), ActionEvaluationStatus.UNKNOWN),
        (ObservationSourceProfile.dom(), ActionEvaluationStatus.NO_EFFECT_CONFIRMED),
        (ObservationSourceProfile.wot(), ActionEvaluationStatus.NO_EFFECT_CONFIRMED),
    ):
        before = _world(f"before-{profile.debug_source}", False, profile)
        after = _world(f"after-{profile.debug_source}", False, profile)
        proposal = ActionEvaluation(
            "request:1", before.observation_id, after.observation_id,
            ActionEvaluationStatus.NO_EFFECT_CONFIRMED, "unchanged", (f"fact:after-{profile.debug_source}",)
        )
        result = apply_action_evidence_profile(
            proposal, _request(), before, after, WorldEvidenceIndex.from_observation(after)
        )
        assert result.status == expected


def test_current_after_only_scoped_artifact_supports_creation_effect() -> None:
    before = _world("before", False, ObservationSourceProfile.dom())
    source = SurfaceObservation(
        "source:after", "dom", "revision:after", ObservationSourceProfile.dom(),
        artifacts={"report": {"public_summary": "report created"}},
    )
    after = WorldObservation(
        "after", (), (), (), {"dom": CoverageState.COMPLETE}, sources=(source,),
    )
    evidence_ref = "artifact:source:after:report"
    proposal = ActionEvaluation(
        "request:1", "before", "after", ActionEvaluationStatus.EFFECT_CONFIRMED,
        "created", (evidence_ref,),
    )

    result = apply_action_evidence_profile(
        proposal, _request(expected_outcome={"output_id": "report"}), before, after,
        WorldEvidenceIndex.from_observation(after),
    )

    assert result.status == ActionEvaluationStatus.EFFECT_CONFIRMED

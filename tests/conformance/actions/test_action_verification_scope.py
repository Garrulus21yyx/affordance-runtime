from types import SimpleNamespace

from affordance_runtime.evaluation import ActionEvaluation, ActionEvaluationStatus
from affordance_runtime.evaluation.action_applicability import apply_action_evidence_profile
from affordance_runtime.evaluation.action_verification import (
    VerificationObligationKind,
    derive_action_verification_obligations,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution import ActionIntent
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    CoverageState,
    ObservationSourceProfile,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)


def _world(identity: str, facts: tuple[tuple[str, str, object], ...], *, profile=None, artifacts=None):
    chosen = profile or ObservationSourceProfile.dom()
    records = tuple(
        StateFact(f"fact:{identity}:{subject}:{predicate}", subject, predicate, value, f"source:{identity}")
        for subject, predicate, value in facts
    )
    source = SurfaceObservation(
        f"source:{identity}", chosen.debug_source, f"revision:{identity}", chosen,
        facts=records, artifacts=artifacts or {},
    )
    return WorldObservation(
        identity, (), records, (), {source.surface: CoverageState.COMPLETE}, sources=(source,),
    )


def _request(*, expected_outcome=None, target="target:1"):
    return SimpleNamespace(intent=ActionIntent("activate", target, expected_outcome=expected_outcome or {}))


def _task(*criteria) -> TaskGoal:
    return TaskGoal("task:verify", "Verify effect", success_criteria=tuple(criteria))


def _proposal(before, after, status, refs):
    return ActionEvaluation("request:1", before.observation_id, after.observation_id, status, "proposal", refs)


def _apply(task, request, before, after, status, refs):
    obligations = derive_action_verification_obligations(task, request, before)
    return apply_action_evidence_profile(
        _proposal(before, after, status, refs), task, request, before, after,
        WorldEvidenceIndex.from_observation(after), obligations,
    )


def test_unrelated_same_target_delta_cannot_prove_declared_enabled_effect() -> None:
    task = _task({"id": "enabled", "subject_id": "target:1", "predicate": "enabled", "value": True})
    before = _world("before", (("target:1", "enabled", False), ("target:1", "focused", False)))
    after = _world("after", (("target:1", "enabled", False), ("target:1", "focused", True)))

    result = _apply(task, _request(), before, after, ActionEvaluationStatus.EFFECT_CONFIRMED, ("fact:after:target:1:focused",))

    assert result.status == ActionEvaluationStatus.UNKNOWN


def test_exact_criterion_progress_supports_effect_only_when_newly_satisfied() -> None:
    task = _task({"id": "enabled", "subject_id": "target:1", "predicate": "enabled", "value": True})
    false_world = _world("before", (("target:1", "enabled", False),))
    true_world = _world("after", (("target:1", "enabled", True),))
    already_true = _world("already", (("target:1", "enabled", True),))

    obligations = derive_action_verification_obligations(task, _request(), false_world)
    assert len(obligations) == 1
    assert obligations[0].kind == VerificationObligationKind.CRITERION_PROGRESS
    assert derive_action_verification_obligations(task, _request(), already_true) == ()
    assert _apply(
        task, _request(), false_world, true_world, ActionEvaluationStatus.EFFECT_CONFIRMED,
        ("fact:after:target:1:enabled",),
    ).status == ActionEvaluationStatus.EFFECT_CONFIRMED
    assert _apply(
        task, _request(), already_true, true_world, ActionEvaluationStatus.EFFECT_CONFIRMED,
        ("fact:after:target:1:enabled",),
    ).status == ActionEvaluationStatus.UNKNOWN


def test_unrelated_target_and_empty_obligation_claims_are_unknown() -> None:
    task = _task({"id": "enabled", "subject_id": "target:1", "predicate": "enabled", "value": True})
    before = _world("before", (("target:1", "enabled", False), ("other", "enabled", False)))
    after = _world("after", (("target:1", "enabled", False), ("other", "enabled", True)))
    unrelated = _apply(
        task, _request(), before, after, ActionEvaluationStatus.EFFECT_CONFIRMED,
        ("fact:after:other:enabled",),
    )
    no_obligation = _apply(
        TaskGoal("empty", "No criteria"), _request(), before, after,
        ActionEvaluationStatus.EFFECT_CONFIRMED, ("fact:after:other:enabled",),
    )
    assert unrelated.status == ActionEvaluationStatus.UNKNOWN
    assert no_obligation.status == ActionEvaluationStatus.UNKNOWN


def test_artifact_created_requires_explicit_output_and_after_only_identity() -> None:
    task = TaskGoal("artifact", "Create report", requested_outputs=("report",))
    request = _request(expected_outcome={"output_id": "report"})
    before = _world("before", ())
    after = _world("after", (), artifacts={"report": {"public_summary": "created"}})
    existing = _world("existing", (), artifacts={"report": {"public_summary": "existing"}})

    accepted = _apply(
        task, request, before, after, ActionEvaluationStatus.EFFECT_CONFIRMED,
        ("artifact:source:after:report",),
    )
    rejected = _apply(
        task, request, existing, after, ActionEvaluationStatus.EFFECT_CONFIRMED,
        ("artifact:source:after:report",),
    )
    assert accepted.status == ActionEvaluationStatus.EFFECT_CONFIRMED
    assert rejected.status == ActionEvaluationStatus.UNKNOWN


def test_no_effect_requires_every_fact_obligation_strong_complete_and_referenced() -> None:
    task = _task(
        {"id": "enabled", "subject_id": "target:1", "predicate": "enabled", "value": True},
        {"id": "visible", "subject_id": "target:1", "predicate": "visible", "value": True},
    )
    facts = (("target:1", "enabled", False), ("target:1", "visible", False))
    before = _world("before", facts)
    after = _world("after", facts)
    one_ref = _apply(
        task, _request(), before, after, ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
        ("fact:after:target:1:enabled",),
    )
    all_refs = _apply(
        task, _request(), before, after, ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
        ("fact:after:target:1:enabled", "fact:after:target:1:visible"),
    )
    weak_after = _world("weak", facts, profile=ObservationSourceProfile.visual())
    weak = _apply(
        task, _request(), before, weak_after, ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
        ("fact:weak:target:1:enabled", "fact:weak:target:1:visible"),
    )
    assert one_ref.status == ActionEvaluationStatus.UNKNOWN
    assert all_refs.status == ActionEvaluationStatus.NO_EFFECT_CONFIRMED
    assert weak.status == ActionEvaluationStatus.UNKNOWN


def test_no_effect_requires_all_current_sources_to_agree_and_be_referenced() -> None:
    task = _task({"id": "enabled", "subject_id": "target:1", "predicate": "enabled", "value": True})
    before = _world("before", (("target:1", "enabled", False),))
    dom_fact = StateFact("fact:after:dom", "target:1", "enabled", False, "source:dom")
    wot_fact = StateFact("fact:after:wot", "target:1", "enabled", False, "source:wot")
    sources = (
        SurfaceObservation("source:dom", "dom", "r:dom", ObservationSourceProfile.dom(), facts=(dom_fact,)),
        SurfaceObservation("source:wot", "wot", "r:wot", ObservationSourceProfile.wot(), facts=(wot_fact,)),
    )
    after = WorldObservation(
        "after", (), (dom_fact, wot_fact), (),
        {"dom": CoverageState.COMPLETE, "wot": CoverageState.COMPLETE}, sources=sources,
    )
    partial = _apply(
        task, _request(), before, after, ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
        ("fact:after:dom",),
    )
    complete = _apply(
        task, _request(), before, after, ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
        ("fact:after:dom", "fact:after:wot"),
    )
    changed = StateFact("fact:after:wot", "target:1", "enabled", True, "source:wot")
    disagreement = WorldObservation(
        "after", (), (dom_fact, changed), (), after.coverage,
        sources=(sources[0], SurfaceObservation("source:wot", "wot", "r:wot", ObservationSourceProfile.wot(), facts=(changed,))),
    )
    disputed = _apply(
        task, _request(), before, disagreement, ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
        ("fact:after:dom", "fact:after:wot"),
    )
    assert partial.status == ActionEvaluationStatus.UNKNOWN
    assert complete.status == ActionEvaluationStatus.NO_EFFECT_CONFIRMED
    assert disputed.status == ActionEvaluationStatus.UNKNOWN


def test_artifact_absence_cannot_prove_no_effect_without_inventory_contract() -> None:
    task = TaskGoal("artifact", "Create report", requested_outputs=("report",))
    before = _world("before", (("target:1", "observed", True),))
    after = _world("after", (("target:1", "observed", True),))
    result = _apply(
        task, _request(expected_outcome={"output_id": "report"}), before, after,
        ActionEvaluationStatus.NO_EFFECT_CONFIRMED, ("fact:after:target:1:observed",),
    )
    assert result.status == ActionEvaluationStatus.UNKNOWN

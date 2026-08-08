import asyncio
from types import SimpleNamespace

from target_agent_loop_support import SharedStateActionEvaluator, shared_state_task

from affordance_runtime.evaluation import ActionEvaluationStatus
from affordance_runtime.world import CoverageState, SemanticTarget, StateFact, WorldObservation


def _observation(identity: str, expanded: bool, coverage: CoverageState) -> WorldObservation:
    return WorldObservation(
        identity,
        (SemanticTarget("shared", "control", "Shared", {"expanded": expanded}),),
        (StateFact(f"fact:{identity}:expanded", "shared", "expanded", expanded, identity),),
        (),
        {"fixture": coverage},
    )


def test_target_action_evaluation_statuses_have_explicit_effect_certainty() -> None:
    assert set(ActionEvaluationStatus) == {
        ActionEvaluationStatus.EFFECT_CONFIRMED,
        ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
        ActionEvaluationStatus.UNKNOWN,
        ActionEvaluationStatus.REJECTED,
    }
    assert not hasattr(ActionEvaluationStatus, "NOT_VERIFIED")


def test_shared_state_evaluator_distinguishes_effect_absence_from_unknown() -> None:
    async def scenario() -> None:
        evaluator = SharedStateActionEvaluator()
        before = _observation("before", False, CoverageState.COMPLETE)
        request = SimpleNamespace(request_id="request:certainty")

        changed = await evaluator.evaluate(
            shared_state_task(), before, request, None, _observation("changed", True, CoverageState.COMPLETE)
        )
        absent = await evaluator.evaluate(
            shared_state_task(), before, request, None, _observation("absent", False, CoverageState.COMPLETE)
        )
        unknown = await evaluator.evaluate(
            shared_state_task(), before, request, None, _observation("unknown", False, CoverageState.FAILED)
        )

        assert changed.status == ActionEvaluationStatus.EFFECT_CONFIRMED
        assert absent.status == ActionEvaluationStatus.NO_EFFECT_CONFIRMED
        assert unknown.status == ActionEvaluationStatus.UNKNOWN
        assert changed.evidence_refs
        assert absent.evidence_refs
        assert unknown.evidence_refs == ()

    asyncio.run(scenario())

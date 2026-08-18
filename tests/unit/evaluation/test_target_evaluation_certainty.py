import asyncio
from types import SimpleNamespace

from affordance_runtime.evaluation import (
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
)
from affordance_runtime.world import CoverageState, SemanticTarget, StateFact, WorldObservation
from tests.support.agent.target_agent_loop_support import SharedStateActionOutcomeProjector, shared_state_task
from tests.support.world import fused_world


def _observation(identity: str, expanded: bool, coverage: CoverageState) -> WorldObservation:
    return fused_world(
        identity,
        (SemanticTarget("shared", "control", "Shared", {"expanded": expanded}),),
        (StateFact(f"fact:{identity}:expanded", "shared", "expanded", expanded, identity),),
        coverage=coverage,
    )


def test_target_action_outcome_uses_orthogonal_closed_algebra() -> None:
    assert set(ObservedChange) == {
        ObservedChange.CHANGED,
        ObservedChange.UNCHANGED,
        ObservedChange.UNKNOWN,
    }
    assert set(LocalPostconditionStatus) == {
        LocalPostconditionStatus.SATISFIED,
        LocalPostconditionStatus.UNSATISFIED,
        LocalPostconditionStatus.UNKNOWN,
        LocalPostconditionStatus.NOT_APPLICABLE,
    }
    assert set(EvidenceMethod) == {
        EvidenceMethod.NATIVE,
        EvidenceMethod.STRUCTURAL,
        EvidenceMethod.VISUAL_DIFF,
        EvidenceMethod.NONE,
    }


def test_shared_state_evaluator_distinguishes_effect_absence_from_unknown() -> None:
    async def scenario() -> None:
        evaluator = SharedStateActionOutcomeProjector()
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

        assert changed.observed_change == ObservedChange.CHANGED
        assert absent.observed_change == ObservedChange.UNCHANGED
        assert unknown.observed_change == ObservedChange.UNKNOWN
        assert changed.evidence_refs
        assert absent.evidence_refs
        assert unknown.evidence_refs == ()

    asyncio.run(scenario())

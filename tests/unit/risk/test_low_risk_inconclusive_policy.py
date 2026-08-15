from dataclasses import replace

from affordance_runtime.actions import (
    ActionRisk,
)
from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder
from affordance_runtime.agent.control_outcome import Continue
from affordance_runtime.agent.post_action_policy import post_action_result
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus
from affordance_runtime.evaluation import ActionEvaluation, ActionEvaluationStatus, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.validation import validate_action_evaluation
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus
from affordance_runtime.world import (
    WorldFusion,
)
from tests.integration.agent.test_agent_loop import _task, _world


def _request(*, risk=ActionRisk.LOW, category="local_reversible"):
    world = _world("before", False, risk=risk)
    binding = replace(world.bindings[0], effect_category=category, risk=risk)
    source = replace(world.sources[0], bindings=(binding,))
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    world = fused.observation
    option = ActionSpaceBuilder().build(_task(), world).options[0]
    selection = ActionSpaceBuilder().admit(option, {})
    return world, ActionBinder().bind(selection, world, "context:policy")


def _action(request, status=ActionEvaluationStatus.UNKNOWN):
    return ActionEvaluation(
        request.request_id, request.world_observation_id, "after", status, "inconclusive"
    )


def _task_evaluation(status: TaskEvaluationStatus):
    refs = ("fact:complete",) if status == TaskEvaluationStatus.COMPLETE else ()
    return TaskEvaluation(_task().task_id, "after", status, "task result", completion_evidence_refs=refs)


def test_low_risk_sent_local_inconclusive_continues_from_fresh_world() -> None:
    world, request = _request()
    state = AgentLoopState(world)
    result = post_action_result(
        _task(), state, request, ActionResult(request.request_id, DispatchStatus.SENT, "dom", True),
        _action(request), _task_evaluation(TaskEvaluationStatus.INCOMPLETE),
    )
    assert isinstance(result, Continue)
    assert state.pending_unknown_request is None


def test_observable_unknown_effect_continues_without_claiming_user_pause() -> None:
    world, request = _request(risk=ActionRisk.MEDIUM)
    state = AgentLoopState(world)

    result = post_action_result(
        _task(),
        state,
        request,
        ActionResult(request.request_id, DispatchStatus.SENT, "dom", True),
        _action(request),
        _task_evaluation(TaskEvaluationStatus.UNKNOWN),
        unknown_recoverable=True,
    )

    assert isinstance(result, Continue)
    assert result.reason_code == "action_unknown_observation_available"
    assert state.pending_unknown_request is None
    assert state.unresolved_observable_request == request


def test_high_external_or_sent_unknown_inconclusive_waits_without_replay() -> None:
    for risk, category, dispatch, success in (
        (ActionRisk.HIGH, "external", DispatchStatus.SENT, True),
        (ActionRisk.LOW, "local_reversible", DispatchStatus.SENT_UNKNOWN, False),
    ):
        world, request = _request(risk=risk, category=category)
        state = AgentLoopState(world)
        result = post_action_result(
            _task(), state, request,
            ActionResult(request.request_id, dispatch, "dom", success, None if success else ActionError.EXECUTION_FAILED),
            _action(request), _task_evaluation(TaskEvaluationStatus.INCOMPLETE),
        )
        assert result is not None and result.status == AgentLoopStatus.WAITING_USER
        assert state.pending_unknown_request == request


def test_validated_task_completion_precedes_action_inconclusive_policy() -> None:
    world, request = _request(risk=ActionRisk.HIGH, category="external")
    result = post_action_result(
        _task(), AgentLoopState(world), request,
        ActionResult(request.request_id, DispatchStatus.SENT_UNKNOWN, "dom", False, ActionError.EXECUTION_FAILED),
        _action(request), _task_evaluation(TaskEvaluationStatus.COMPLETE),
    )
    assert result is not None and result.status == AgentLoopStatus.DONE


def test_source_less_confirmed_action_claim_is_downgraded() -> None:
    before, request = _request()
    after = replace(
        _world("after", True),
        targets=(),
        bindings=(),
        sources=(),
        source_manifest=(),
        entity_alignment_decisions=(),
        entity_source_links=(),
        media=(),
    )
    proposal = ActionEvaluation(
        request.request_id, before.observation_id, after.observation_id,
        ActionEvaluationStatus.EFFECT_CONFIRMED, "claimed", (after.facts[0].fact_id,),
    )

    result = validate_action_evaluation(
        proposal, _task(), request, before, after, WorldEvidenceIndex.from_observation(after)
    )

    assert result.status == ActionEvaluationStatus.UNKNOWN

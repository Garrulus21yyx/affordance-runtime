import asyncio
from dataclasses import replace

import pytest
from target_agent_loop_support import SharedStateActionEvaluator, SharedStateTaskEvaluator
from test_visual_surface_adapter import PointGrounder, Proposer, VisualSession

from affordance_runtime.actions import (
    ActionBinder,
    ActionSpaceBuilder,
)
from affordance_runtime.agent import (
    AgentLoop,
    AgentLoopStatus,
    ProposeDone,
    SelectAction,
)
from affordance_runtime.evaluation import ActionEvaluation, ActionEvaluationStatus
from affordance_runtime.surfaces.visual import VisualSurfaceAdapter
from affordance_runtime.task import LoopBudget, RiskProfile, TaskGoal
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


def _task(risk: RiskProfile = RiskProfile.LOW, *, turns: int = 2) -> TaskGoal:
    return TaskGoal(
        "shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=risk,
        loop_budget=LoopBudget(turns, turns + 1),
    )


class StatefulProposer(Proposer):
    def __init__(self, session: VisualSession, *, change: bool = True) -> None:
        super().__init__()
        self.session = session
        self.change = change

    def propose(self, request):
        regions = super().propose(request)
        expanded = self.change and bool(self.session.clicks)
        return [replace(regions[0], state={"expanded": expanded})]


class FailOnceCurrentnessSession(VisualSession):
    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    def capture_visual_frame(self, observation_id):
        self.attempts += 1
        if self.attempts == 2:
            raise RuntimeError("currentness capture unavailable")
        return super().capture_visual_frame(observation_id)


class MissingActionPolicy:
    async def decide(self, context):
        task, world, action_space = context.task, context.world, context.actions
        recent_turns = context.history.items
        del task, world, action_space, recent_turns
        return SelectAction(context.context_id, "missing-visual-action")


class FinishThenSelectPolicy:
    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, context):
        task, world, action_space = context.task, context.world, context.actions
        recent_turns = context.history.items
        del task, world, recent_turns
        self.calls += 1
        return (
            ProposeDone(context.context_id, (), (), "claim done", ())
            if self.calls == 1
            else SelectAction(context.context_id, action_space.options[0].action_id)
        )


class FirstPolicy:
    def __init__(self, parameters=None) -> None:
        self.parameters = parameters or {}

    async def decide(self, context):
        task, world, action_space = context.task, context.world, context.actions
        recent_turns = context.history.items
        del task, world, recent_turns
        return SelectAction(context.context_id, action_space.options[0].action_id, self.parameters)


class UnknownActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, result
        return ActionEvaluation(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ActionEvaluationStatus.UNKNOWN,
            "visual outcome remains unknown",
        )


def _run(session, proposer, task, policy, action_evaluator=None):
    environment = UnifiedWorldEnvironment(
        (VisualSurfaceAdapter(session, proposer, PointGrounder()),)  # type: ignore[arg-type]
    )
    loop = AgentLoop(
        policy,
        action_evaluator or SharedStateActionEvaluator(),
        SharedStateTaskEvaluator(),
    )
    return asyncio.run((loop).run(environment, task))


@pytest.mark.parametrize("key", ["x", "y", "bbox", "coordinate", "backend", "selector", "point"])
def test_visual_policy_cannot_inject_private_route_fields(key: str) -> None:
    session = VisualSession()
    result = _run(session, StatefulProposer(session), _task(), FirstPolicy({key: "injected"}))
    assert result.status == AgentLoopStatus.BLOCKED
    assert result.execution_count == 0
    assert session.clicks == []


def test_missing_visual_action_id_has_zero_execution() -> None:
    session = VisualSession()
    result = _run(session, StatefulProposer(session), _task(), MissingActionPolicy())
    assert result.status == AgentLoopStatus.BLOCKED
    assert result.execution_count == 0
    assert session.clicks == []


def test_finish_does_not_complete_unsatisfied_visual_task_and_policy_can_continue() -> None:
    session = VisualSession()
    policy = FinishThenSelectPolicy()
    result = _run(session, StatefulProposer(session), _task(), policy)
    assert result.status == AgentLoopStatus.DONE
    assert policy.calls == 2
    assert result.execution_count == 1


@pytest.mark.parametrize("risk", [RiskProfile.MEDIUM, RiskProfile.HIGH])
def test_effectful_visual_tasks_above_low_wait_for_confirmation(risk: RiskProfile) -> None:
    session = VisualSession()
    result = _run(session, StatefulProposer(session), _task(risk), FirstPolicy())
    assert result.status == AgentLoopStatus.WAITING_CONFIRMATION
    assert result.execution_count == 0
    assert session.clicks == []


def test_visual_transport_success_without_world_state_change_is_not_complete() -> None:
    session = VisualSession()
    result = _run(session, StatefulProposer(session, change=False), _task(turns=1), FirstPolicy())
    assert result.status != AgentLoopStatus.DONE
    assert result.execution_count == 1


def test_visual_currentness_unavailable_reobserves_without_counting_execution() -> None:
    session = FailOnceCurrentnessSession()
    proposer = StatefulProposer(session)
    result = _run(session, proposer, _task(turns=2), FirstPolicy())

    assert result.status == AgentLoopStatus.DONE
    assert result.observation_count == 3
    assert result.execution_count == 2
    assert result.currentness_probe_count == 2
    assert len(session.clicks) == 1
    assert proposer.calls == 3


def test_visual_sent_unknown_confirmed_by_fresh_world_is_done_without_replay() -> None:
    session = VisualSession()
    session.fail_click = True
    result = _run(session, StatefulProposer(session), _task(), FirstPolicy())
    assert result.status == AgentLoopStatus.DONE
    assert result.execution_count == 1
    assert len(session.clicks) == 1


def test_visual_sent_unknown_and_unknown_evaluation_waits_without_replay() -> None:
    session = VisualSession()
    session.fail_click = True
    result = _run(
        session,
        StatefulProposer(session, change=False),
        _task(),
        FirstPolicy(),
        UnknownActionEvaluator(),
    )
    assert result.status == AgentLoopStatus.WAITING_USER
    assert result.execution_count == 1
    assert len(session.clicks) == 1


def test_visual_effect_legality_and_exact_binding_prevent_route_escape() -> None:
    async def scenario() -> None:
        session = VisualSession()
        adapter = VisualSurfaceAdapter(
            session, Proposer(), PointGrounder(),  # type: ignore[arg-type]
        )
        world = UnifiedWorldEnvironment((adapter,))
        acquisition_task = TaskGoal(
            "shared",
            "Enable shared state",
            allowed_effects=("shared_state_enabled",),
            risk_profile=RiskProfile.LOW,
        )
        acquisition = await world.reset(acquisition_task)
        assert acquisition.observation is not None
        observed = acquisition.observation
        allowed = observed.bindings[0]
        forbidden = replace(
            allowed,
            binding_id=allowed.binding_id + ":forbidden",
            semantic_effects=("forbidden_effect",),
            confidence=1.0,
            verification_contract_digest="",
        )
        observed = replace(observed, bindings=(forbidden, allowed))
        task = replace(
            acquisition_task,
            allowed_effects=("shared_state_enabled", "forbidden_effect"),
            forbidden_effects=("forbidden_effect",),
        )
        space = ActionSpaceBuilder().build(task, observed)

        assert len(space.options) == 1
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(space.options[0], {}), observed, "context:test"
        )
        assert request.binding.binding_id == allowed.binding_id

        unrelated = TaskGoal(
            "other",
            "Send message",
            allowed_effects=("message_sent",),
            risk_profile=RiskProfile.LOW,
        )
        assert ActionSpaceBuilder().build(unrelated, observed).options == ()

    asyncio.run(scenario())

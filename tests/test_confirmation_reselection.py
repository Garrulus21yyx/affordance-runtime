import asyncio
from dataclasses import replace

from test_confirmation_continuation import ActionEvaluator, TaskEvaluator, _task, _world

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus, AskUser, SelectAction
from affordance_runtime.confirmation import ConfirmationDecision, ConfirmationDecisionKind
from affordance_runtime.task import TaskGoal
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import WorldObservation


class ReselectPolicy:
    def __init__(self, second: str = "last") -> None:
        self.calls = 0
        self.second = second
        self.selected_effects = ()

    async def decide(self, context):
        task, world, action_space = context.task, context.world, context.actions
        recent_turns, optional_plan = context.history.items, context.progress.plan_summary
        del task, world, recent_turns, optional_plan
        self.calls += 1
        if self.calls == 1:
            return SelectAction(context.context_id, action_space.options[0].action_id)
        if self.second == "ask":
            return AskUser(context.context_id, "The confirmed action changed; what should I do?")
        option = action_space.options[-1]
        self.selected_effects = option.semantic_effects
        return SelectAction(context.context_id, option.action_id)


def _decision(paused):
    request = paused.confirmation_request
    assert request is not None
    return ConfirmationDecision(
        request.confirmation_id,
        request.subject_id,
        ConfirmationDecisionKind.CONFIRM,
    )


def _changed_candidates_world() -> WorldObservation:
    base = _world("fresh", False, "#first")
    first = replace(
        base.bindings[0],
        binding_id="binding:fresh:first",
        target_fingerprint="fingerprint:fresh:first",
        semantic_effects=("effect_a",),
    )
    second = replace(
        base.bindings[0],
        binding_id="binding:fresh:second",
        target_fingerprint="fingerprint:fresh:second",
        semantic_effects=("effect_b",),
        payload={"selector": "#second"},
    )
    return replace(base, bindings=(first, second))


def _expanded_task() -> TaskGoal:
    return replace(
        _task(),
        allowed_effects=("shared_state_enabled", "effect_a", "effect_b"),
    )


def test_no_exact_subject_returns_to_policy_and_uses_its_new_selection() -> None:
    async def scenario() -> None:
        policy = ReselectPolicy()
        environment = StaticEnvironment(
            [_world("initial", False, "#initial"), _changed_candidates_world()]
        )
        loop = AgentLoop(policy, ActionEvaluator(), TaskEvaluator())
        session = await AgentEpisodeRunner(loop).start(environment, _expanded_task())
        paused = await session.run_until_pause()

        result = await session.resolve_confirmation(_decision(paused))

        assert policy.calls == 2
        assert result.status == AgentLoopStatus.WAITING_CONFIRMATION
        assert result.confirmation_request is not None
        assert result.confirmation_request.semantic_effects == policy.selected_effects == ("effect_b",)
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_no_exact_subject_allows_policy_to_ask_user() -> None:
    async def scenario() -> None:
        policy = ReselectPolicy("ask")
        environment = StaticEnvironment(
            [_world("initial", False, "#initial"), _changed_candidates_world()]
        )
        loop = AgentLoop(policy, ActionEvaluator(), TaskEvaluator())
        session = await AgentEpisodeRunner(loop).start(environment, _expanded_task())
        paused = await session.run_until_pause()

        result = await session.resolve_confirmation(_decision(paused))

        assert policy.calls == 2
        assert result.status == AgentLoopStatus.WAITING_USER
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_unavailable_confirmed_action_does_not_authorize_another_target() -> None:
    async def scenario() -> None:
        policy = ReselectPolicy()
        other = _world("fresh", False, "#other")
        other_target = replace(other.targets[0], target_id="other-target", label="Other action")
        other_binding = replace(
            other.bindings[0],
            binding_id="binding:fresh:other",
            target_id="other-target",
            source_target_id="other-target",
        )
        fresh = replace(other, targets=(other_target,), bindings=(other_binding,))
        environment = StaticEnvironment([_world("initial", False, "#initial"), fresh])
        loop = AgentLoop(policy, ActionEvaluator(), TaskEvaluator())
        session = await AgentEpisodeRunner(loop).start(environment, _task())
        paused = await session.run_until_pause()

        result = await session.resolve_confirmation(_decision(paused))

        assert policy.calls == 2
        assert result.status == AgentLoopStatus.WAITING_CONFIRMATION
        assert result.confirmation_request is not None
        assert result.confirmation_request.intent.target_id == "other-target"
        assert environment.executed_requests == []

    asyncio.run(scenario())

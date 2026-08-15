import asyncio
from dataclasses import fields

import pytest

from affordance_runtime.actions.binder import BindingError
from affordance_runtime.agent import AgentLoop, AgentLoopStatus
from affordance_runtime.agent.decisions import (
    Abort,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.task import IntentContext, IntentExcerpt, IntentSourceKind, LoopBudget
from tests.integration.agent.test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _sent, _task, _world
from tests.support.agent.static_environment import StaticEnvironment


@pytest.mark.parametrize(
    "decision_type",
    (
        SelectAction,
        RequestObservation,
        RequestActionPage,
        AskUser,
        ProposeDone,
        Wait,
        Abort,
    ),
)
def test_all_agent_decisions_require_context_id(decision_type) -> None:
    assert fields(decision_type)[0].name == "context_id"


@pytest.mark.parametrize(
    "factory",
    (
        lambda: SelectAction("", "action:1"),
        lambda: RequestObservation("", "criterion_verification", "target:1", "", "refresh"),
        lambda: RequestActionPage("", "query"),
        lambda: AskUser("", "question", ()),
        lambda: ProposeDone("", (), (), "done", ()),
        lambda: Wait("", "wait", 1),
        lambda: Abort("", "abort", "policy"),
    ),
)
def test_blank_context_id_fails_closed(factory) -> None:
    with pytest.raises(ValueError, match="context"):
        factory()


@pytest.mark.parametrize(
    "factory",
    (
        lambda: RequestObservation("context:1", "unsupported", "target", "", "reason"),
        lambda: RequestObservation("context:1", "visual_property", "target", "", "reason"),
        lambda: RequestActionPage("context:1", "q" * 121),
        lambda: AskUser("context:1", "q" * 1_001),
        lambda: AskUser("context:1", "question", tuple(str(index) for index in range(33))),
        lambda: ProposeDone("context:1", tuple(str(index) for index in range(33)), (), "done", ()),
        lambda: Abort("context:1", "abort", "invented-category"),
    ),
)
def test_decision_fields_are_bounded_and_typed(factory) -> None:
    with pytest.raises(ValueError):
        factory()


def test_runtime_propose_done_summary_uses_canonical_budget() -> None:
    ProposeDone("context:1", (), (), "x" * 1_024, ())

    with pytest.raises(ValueError, match="completion result summary"):
        ProposeDone("context:1", (), (), "x" * 1_025, ())


class _FakeWaiter:
    def __init__(self) -> None:
        self.waits: list[int] = []

    async def wait(self, max_wait_ms: int) -> None:
        self.waits.append(max_wait_ms)


def test_stale_decision_is_zero_execute_and_zero_probe_then_rebuilt() -> None:
    class Policy:
        def __init__(self) -> None:
            self.context_ids = []
            self.remaining_turns = []

        async def decide(self, context):
            self.context_ids.append(context.context_id)
            self.remaining_turns.append(context.budgets.remaining_turns)
            context_id = "context:stale" if len(self.context_ids) == 1 else context.context_id
            return SelectAction(context_id, context.actions.options[0].action_id)

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment([_world("before", False), _world("after", True)], [_sent()])
        result = await (AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())).run(
            environment, _task()
        )

        assert result.status == AgentLoopStatus.DONE
        assert policy.context_ids[0] != policy.context_ids[1]
        assert result.execution_count == 1
        assert result.observation_count == 2
        assert result.currentness_probe_count == 0
        assert len(environment.executed_requests) == 1
        assert policy.remaining_turns == [20, 19]
        assert result.control_transition_total_count == 1

    asyncio.run(scenario())


def test_replayed_old_context_decision_does_not_execute_again() -> None:
    class ReplayPolicy:
        cached = None

        async def decide(self, context):
            if self.cached is None:
                self.cached = SelectAction(context.context_id, context.actions.options[0].action_id)
            return self.cached

    async def scenario() -> None:
        task = _task()
        task = task.__class__(
            task.task_id,
            task.instruction,
            allowed_effects=task.allowed_effects,
            success_criteria=task.success_criteria,
            risk_profile=task.risk_profile,
            loop_budget=LoopBudget(2, 4),
        )
        environment = StaticEnvironment(
            [_world("before", False), _world("after", False)],
            [_sent()],
        )
        result = await (
            AgentLoop(ReplayPolicy(), SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, task)

        assert result.status == AgentLoopStatus.FAILED
        assert result.execution_count == 1
        assert len(environment.executed_requests) == 1

    asyncio.run(scenario())


def test_bound_action_request_carries_current_accepted_context() -> None:
    class Policy:
        context_id = ""

        async def decide(self, context):
            self.context_id = context.context_id
            return SelectAction(context.context_id, context.actions.options[0].action_id)

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment([_world("before", False), _world("after", True)], [_sent()])
        await (AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())).run(
            environment, _task()
        )

        assert environment.executed_requests[0].context_id == policy.context_id

    asyncio.run(scenario())


def test_wait_uses_fake_controller_and_performs_fresh_observe() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            if self.calls == 1:
                return Wait(context.context_id, "settle", 25)
            return Abort(context.context_id, "finished waiting", "policy")

    async def scenario() -> None:
        waiter = _FakeWaiter()
        environment = StaticEnvironment([_world("before", False), _world("after", False)])
        loop = AgentLoop(
            Policy(),
            SharedActionEvaluator(),
            SharedTaskEvaluator(),
            wait_controller=waiter,
        )
        result = await (loop).run(environment, _task())

        assert waiter.waits == [25]
        assert result.observation_count == 2
        assert result.execution_count == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("decision_kind", ("observe", "wait"))
def test_fresh_observation_decisions_reject_reused_identity(decision_kind: str) -> None:
    class Policy:
        async def decide(self, context):
            if decision_kind == "observe":
                return RequestObservation(
                    context.context_id,
                    "criterion_verification",
                    "shared-toggle",
                    "",
                    "refresh",
                )
            return Wait(context.context_id, "settle", 1)

    async def scenario() -> None:
        observation = _world("same", False)
        environment = StaticEnvironment([observation, observation])
        result = await (
            AgentLoop(
                Policy(),
                SharedActionEvaluator(),
                SharedTaskEvaluator(),
                wait_controller=_FakeWaiter(),
            )
        ).run(environment, _task())

        assert result.status == AgentLoopStatus.FAILED
        assert result.execution_count == 0
        assert result.observation_count == 2
        assert result.message == "observation_identity_reused"

    asyncio.run(scenario())


def test_each_policy_call_gets_a_new_context_epoch_even_when_projection_is_unchanged() -> None:
    class Policy:
        def __init__(self) -> None:
            self.context_ids = []

        async def decide(self, context):
            self.context_ids.append(context.context_id)
            if len(self.context_ids) == 1:
                return SelectAction("context:stale", context.actions.options[0].action_id)
            return Abort(context.context_id, "stop", "policy")

    async def scenario() -> None:
        policy = Policy()
        result = await (AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())).run(
            StaticEnvironment([_world("before", False)]), _task()
        )

        assert result.status == AgentLoopStatus.FAILED
        assert len(policy.context_ids) == 2
        assert policy.context_ids[0] != policy.context_ids[1]

    asyncio.run(scenario())


def test_no_op_page_request_advances_context_epoch() -> None:
    class Policy:
        def __init__(self) -> None:
            self.context_ids = []

        async def decide(self, context):
            self.context_ids.append(context.context_id)
            if len(self.context_ids) == 1:
                return RequestActionPage(context.context_id)
            return Abort(context.context_id, "page unchanged", "policy")

    async def scenario() -> None:
        policy = Policy()
        await (AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())).run(
            StaticEnvironment([_world("before", False)]), _task()
        )

        assert len(policy.context_ids) == 2
        assert policy.context_ids[0] != policy.context_ids[1]

    asyncio.run(scenario())


def test_stale_binding_refresh_rejects_reused_observation_identity() -> None:
    class UnavailableBinder:
        def bind(self, selection, observation, context_id):
            raise BindingError("unavailable")

    class Policy:
        async def decide(self, context):
            return SelectAction(context.context_id, context.actions.options[0].action_id)

    async def scenario() -> None:
        observation = _world("same", False)
        environment = StaticEnvironment([observation, observation])
        result = await (
            AgentLoop(
                Policy(),
                SharedActionEvaluator(),
                SharedTaskEvaluator(),
                binder=UnavailableBinder(),
            )
        ).run(environment, _task())

        assert result.status == AgentLoopStatus.FAILED
        assert result.execution_count == 0
        assert result.observation_count == 2
        assert environment.executed_requests == []
        assert result.message == "observation_identity_reused"

    asyncio.run(scenario())


def test_propose_done_cannot_bypass_validated_task_evaluator() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            if self.calls == 1:
                return ProposeDone(context.context_id, (), ("fact:before:enabled",), "done", ())
            return Abort(context.context_id, "validator rejected completion", "policy")

    class CountingEvaluator(SharedTaskEvaluator):
        def __init__(self) -> None:
            self.calls = 0

        async def evaluate(self, task, observation):
            self.calls += 1
            return await super().evaluate(task, observation)

    async def scenario() -> None:
        evaluator = CountingEvaluator()
        result = await (AgentLoop(Policy(), SharedActionEvaluator(), evaluator)).run(
            StaticEnvironment([_world("before", False)]), _task()
        )

        assert result.status == AgentLoopStatus.FAILED
        assert evaluator.calls == 2
        assert result.execution_count == 0

    asyncio.run(scenario())


def test_intent_context_cannot_expand_task_effect_authority() -> None:
    class Policy:
        async def decide(self, context):
            assert context.intent.authority == "context_only"
            assert context.task.allowed_effects.items == ()
            assert context.actions.options == ()
            return AskUser(context.context_id, "Need an authoritative task revision", ("allowed_effect",))

    async def scenario() -> None:
        intent = IntentContext(
            (
                IntentExcerpt(
                    "You may enable shared state",
                    IntentSourceKind.USER,
                    "request:1",
                    "sha256:" + "a" * 64,
                ),
            )
        )
        read_only = _task().__class__("inspect", "Inspect shared state")
        result = await (AgentLoop(Policy(), SharedActionEvaluator(), SharedTaskEvaluator())).run(
            StaticEnvironment([_world("before", False)]), read_only, intent
        )

        assert result.status == AgentLoopStatus.WAITING_USER
        assert result.task.allowed_effects == ()
        assert result.execution_count == 0

    asyncio.run(scenario())


def test_non_action_decisions_are_projected_into_recurrent_semantic_history() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            if self.calls == 1:
                return RequestObservation(
                    context.context_id,
                    "criterion_verification",
                    "shared-toggle",
                    "",
                    "refresh public state",
                )
            if self.calls == 2:
                observed = context.last_transition
                assert observed is not None
                observed = observed.previous_decision
                assert observed.decision_kind == "requestobservation"
                assert observed.details["subject_id"] == "shared-toggle"
                assert observed.details["reason"] == "refresh public state"
                return RequestActionPage(context.context_id, query="enable")
            latest = context.last_transition
            assert latest is not None
            paged = latest.previous_decision
            assert paged.decision_kind == "requestactionpage"
            assert paged.details["query"] == "enable"
            assert paged.details["result"] in {"page_changed", "page_unchanged"}
            return Abort(context.context_id, "history verified", "policy")

    async def scenario() -> None:
        result = await (AgentLoop(Policy(), SharedActionEvaluator(), SharedTaskEvaluator())).run(
            StaticEnvironment([_world("before", False), _world("after", False)]),
            _task(),
        )

        assert result.status == AgentLoopStatus.FAILED
        assert result.execution_count == 0

    asyncio.run(scenario())


def test_total_wait_budget_is_enforced_without_real_delay() -> None:
    class Policy:
        async def decide(self, context):
            return Wait(context.context_id, "settle", 60_000)

    async def scenario() -> None:
        waiter = _FakeWaiter()
        environment = StaticEnvironment([_world("one", False), _world("two", False), _world("three", False)])
        result = await (
            AgentLoop(
                Policy(),
                SharedActionEvaluator(),
                SharedTaskEvaluator(),
                wait_controller=waiter,
            )
        ).run(environment, _task())

        assert result.status == AgentLoopStatus.BLOCKED
        assert waiter.waits == [60_000, 60_000]
        assert result.observation_count == 3

    asyncio.run(scenario())

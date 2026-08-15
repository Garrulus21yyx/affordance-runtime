import asyncio

from affordance_runtime.actions import (
    ActionBinding,
    ActionPager,
    ActionRisk,
)
from affordance_runtime.agent import AgentLoop, AgentLoopStatus, SelectAction
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.model.context import ContextBuilder, ContextProjectionBudget
from affordance_runtime.task import LoopBudget, RiskProfile, TaskGoal
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    CoverageState,
    SemanticTarget,
    StateFact,
    WorldObservation,
)


def _destination_world(identity: str, delivered: bool) -> WorldObservation:
    targets = (
        SemanticTarget("message:1", "message", "Message", {"delivered": delivered}),
        SemanticTarget("person:alice", "person", "Alice"),
        SemanticTarget("person:bob", "person", "Bob"),
    )
    binding = ActionBinding(
        f"binding:{identity}",
        identity,
        identity,
        f"revision:{identity}",
        f"fingerprint:{identity}",
        "message:1",
        "message:1",
        "dom",
        "dom",
        "drag_to",
        "drag",
        "external",
        ("message_sent",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"selector": "#send"},
        risk=ActionRisk.LOW,
        destination_required=True,
        eligible_destination_ids=("person:alice", "person:bob"),
    )
    fact = StateFact(f"fact:{identity}:delivered", "message:1", "delivered", delivered, identity)
    return WorldObservation(identity, targets, (fact,), (binding,), {"dom": CoverageState.COMPLETE})


def _destination_task() -> TaskGoal:
    return TaskGoal(
        "destination-page",
        "Send the message",
        allowed_effects=("message_sent",),
        risk_profile=RiskProfile.LOW,
        loop_budget=LoopBudget(2, 3),
    )


class _TaskEvaluator:
    async def evaluate(self, task, observation):
        done = bool(observation.facts[0].value)
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE if done else TaskEvaluationStatus.INCOMPLETE,
            "done" if done else "pending",
            completion_evidence_refs=(observation.facts[0].fact_id,) if done else (),
        )


class _ActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, result
        return ActionEvaluation(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ActionEvaluationStatus.EFFECT_CONFIRMED,
            "delivered",
            (after.facts[0].fact_id,),
        )


def test_hidden_destination_is_rejected_before_execution() -> None:
    class Policy:
        async def decide(self, context):
            option = context.actions.options[0]
            assert tuple(item.destination_id for item in option.destinations.items) == ("person:alice",)
            return SelectAction(context.context_id, option.action_id, destination_id="person:bob")

    async def scenario() -> None:
        environment = StaticEnvironment([_destination_world("before", False)])
        result = await (
            AgentLoop(
                Policy(),
                _ActionEvaluator(),
                _TaskEvaluator(),
                context_builder=ContextBuilder(
                    ContextProjectionBudget(max_destinations_per_option=1),
                    ActionPager(),
                ),
            )
        ).run(environment, _destination_task())

        assert result.status == AgentLoopStatus.BLOCKED
        assert result.execution_count == 0
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_visible_destination_is_accepted() -> None:
    class Policy:
        async def decide(self, context):
            option = context.actions.options[0]
            return SelectAction(context.context_id, option.action_id, destination_id="person:alice")

    async def scenario() -> None:
        environment = StaticEnvironment(
            [_destination_world("before", False), _destination_world("after", True)],
            [ActionResult("*", DispatchStatus.SENT, "dom", True)],
        )
        result = await (
            AgentLoop(
                Policy(),
                _ActionEvaluator(),
                _TaskEvaluator(),
                context_builder=ContextBuilder(
                    ContextProjectionBudget(max_destinations_per_option=1),
                    ActionPager(),
                ),
            )
        ).run(environment, _destination_task())

        assert result.status == AgentLoopStatus.DONE
        assert result.execution_count == 1
        assert len(environment.executed_requests) == 1

    asyncio.run(scenario())

import asyncio
import json
from dataclasses import FrozenInstanceError

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus, SelectAction
from affordance_runtime.agent.result import AgentFailureCode
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.task import LoopBudget, RiskProfile, TaskGoal
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    ActionBinding,
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)
from affordance_runtime.world.binder import ActionBinder


def _world(observation_id: str, value: str) -> WorldObservation:
    target = SemanticTarget("target:textbox", "textbox", "Text", {"value": value})
    fact = StateFact(f"fact:{observation_id}:value", target.target_id, "value", value, observation_id)
    binding = ActionBinding(
        f"binding:{observation_id}",
        observation_id,
        observation_id,
        f"revision:{observation_id}",
        f"fingerprint:{observation_id}",
        target.target_id,
        target.target_id,
        "dom",
        "dom",
        "fill",
        "fill",
        "local_reversible",
        ("value_changed",),
        {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        {"private_route": "not-model-facing"},
    )
    source = SurfaceObservation(
        observation_id,
        "dom",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        (target,),
        (fact,),
        (binding,),
    )
    return WorldObservation(
        observation_id,
        (target,),
        (fact,),
        (binding,),
        {"dom": CoverageState.COMPLETE},
        sources=(source,),
    )


def _task() -> TaskGoal:
    return TaskGoal(
        "task:fill",
        "Enter the public value",
        allowed_effects=("value_changed",),
        risk_profile=RiskProfile.LOW,
        loop_budget=LoopBudget(6, 8),
    )


class RepeatedFillPolicy:
    def __init__(self) -> None:
        self.calls = 0
        self.context_ids: list[str] = []
        self.contexts = []

    async def decide(self, context):
        self.calls += 1
        self.context_ids.append(context.context_id)
        self.contexts.append(context)
        option = next(item for item in context.actions.options if item.semantic_action == "fill")
        return SelectAction(context.context_id, option.action_id, {"value": "desired"})


class IncompleteTaskEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "task remains incomplete",
        )


class ValueActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, result
        changed = before.targets[0].state["value"] != after.targets[0].state["value"]
        return ActionEvaluation(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ActionEvaluationStatus.EFFECT_CONFIRMED if changed else ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
            "value evaluated",
            (after.facts[0].fact_id,),
        )


class CountingBinder(ActionBinder):
    def __init__(self) -> None:
        self.calls = 0

    def bind(self, selection, observation, context_id):
        self.calls += 1
        return super().bind(selection, observation, context_id)


def _loop(policy) -> AgentLoop:
    return AgentLoop(policy, ValueActionEvaluator(), IncompleteTaskEvaluator())


def test_already_satisfied_selection_is_zero_call_then_typed_failure() -> None:
    async def scenario() -> None:
        policy = RepeatedFillPolicy()
        environment = StaticEnvironment([_world("observation:one", "desired")])
        loop = _loop(policy)
        binder = CountingBinder()
        loop.binder = binder
        result = await AgentEpisodeRunner(loop).run(environment, _task())

        assert result.status is AgentLoopStatus.FAILED
        assert result.failure_code is AgentFailureCode.NO_PROGRESS_REPETITION
        assert result.execution_count == 0
        assert result.currentness_probe_count == 0
        assert environment.executed_requests == []
        assert binder.calls == 0
        assert policy.calls == 2
        assert len(set(policy.context_ids)) == 2
        events = policy.contexts[1].progress.events
        assert len(events.items) == 1
        assert events.items[0].event_type == "already_satisfied_selection"
        assert events.items[0].strategy_transition_required is True
        progress_json = json.dumps(to_json_compatible(policy.contexts[1].progress))
        assert "desired" not in progress_json
        assert "private_route" not in progress_json

    asyncio.run(scenario())


def test_effectful_fill_executes_once_then_repeat_is_contained() -> None:
    async def scenario() -> None:
        policy = RepeatedFillPolicy()
        environment = StaticEnvironment(
            [_world("observation:one", ""), _world("observation:two", "desired")],
            [ActionResult("*", DispatchStatus.SENT, "dom", True)],
        )
        session = await AgentEpisodeRunner(_loop(policy)).start(environment, _task())
        result = await session.run_until_pause()

        assert result.status is AgentLoopStatus.FAILED
        assert result.failure_code is AgentFailureCode.NO_PROGRESS_REPETITION
        assert result.execution_count == 1
        assert result.currentness_probe_count == 0
        assert len(environment.executed_requests) == 1
        assert policy.calls == 3
        assert result.turns[0].action_evaluation.status is ActionEvaluationStatus.EFFECT_CONFIRMED
        snapshot = session.snapshot_partial_episode()
        assert snapshot.observation_count == 2
        assert snapshot.execution_count == 1
        assert snapshot.completed_turn_count == 3
        assert snapshot.latest_task_status == "incomplete"
        assert snapshot.latest_action_evaluation_status == "effect_confirmed"
        assert snapshot.latest_semantic_attempt_key_digest.startswith("sha256:")
        assert snapshot.same_attempt_streak == 2
        assert snapshot.no_progress_count == 2
        assert snapshot.last_progress_event_type == "already_satisfied_selection"
        try:
            snapshot.execution_count = 2
        except FrozenInstanceError:
            pass
        else:
            raise AssertionError("partial episode snapshot must be read-only")

    asyncio.run(scenario())

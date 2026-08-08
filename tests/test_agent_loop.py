import asyncio
from dataclasses import dataclass, replace

import pytest

from affordance_runtime.agent import (
    AgentEpisodeRunner,
    AgentLoop,
    AgentLoopStatus,
    Finish,
    Reobserve,
    SelectAction,
    Stop,
)
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution.contracts import ActionError, ActionResult, DispatchStatus
from affordance_runtime.task import LoopBudget, RiskProfile, TaskGoal
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    ActionBinding,
    ActionRisk,
    CoverageState,
    SemanticTarget,
    WorldObservation,
)


def _world(observation_id: str, enabled: bool, *, risk: ActionRisk = ActionRisk.LOW) -> WorldObservation:
    target = SemanticTarget(
        "shared-toggle",
        "button",
        "Shared state enabled" if enabled else "Enable shared state",
        {"enabled": enabled},
    )
    binding = ActionBinding(
        binding_id=f"binding:{observation_id}",
        world_observation_id=observation_id,
        source_observation_id=observation_id,
        source_revision=f"revision:{observation_id}",
        target_fingerprint=f"fingerprint:{observation_id}",
        target_id=target.target_id,
        source_target_id=target.target_id,
        surface="dom",
        executor_id="dom",
        semantic_action="activate",
        primitive_action="click",
        effect_category="local_reversible",
        semantic_effects=("shared_state_enabled",),
        parameter_schema={"type": "object", "properties": {}, "additionalProperties": False},
        payload={"selector": "#shared"},
        risk=risk,
    )
    return WorldObservation(
        observation_id,
        (target,),
        (),
        (binding,),
        {"dom": CoverageState.COMPLETE},
    )


def _task() -> TaskGoal:
    return TaskGoal(
        "enable-shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        success_criteria=({"target_id": "shared-toggle", "state": {"enabled": True}},),
        risk_profile=RiskProfile.LOW,
    )


@dataclass
class ScriptedPolicy:
    decisions: list[object]

    async def decide(self, task, world, action_space, recent_turns, optional_plan):
        del task, world, recent_turns, optional_plan
        decision = self.decisions.pop(0)
        if decision == "first":
            return SelectAction(action_space.options[0].action_id)
        return decision


class SharedTaskEvaluator:
    async def evaluate(self, task, observation):
        del task
        enabled = bool(observation.targets[0].state.get("enabled"))
        return TaskEvaluation(
            TaskEvaluationStatus.COMPLETE if enabled else TaskEvaluationStatus.INCOMPLETE,
            "shared state is enabled" if enabled else "shared state is disabled",
        )


class SharedActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task
        changed = before.targets[0].state.get("enabled") != after.targets[0].state.get("enabled")
        if result.dispatch_status == DispatchStatus.SENT_UNKNOWN and not changed:
            return ActionEvaluation(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ActionEvaluationStatus.UNKNOWN,
                "effect remains unknown",
            )
        return ActionEvaluation(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ActionEvaluationStatus.EFFECT_CONFIRMED
            if changed
            else ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
            "state changed" if changed else "state did not change",
            (f"world:{after.observation_id}:target:shared-toggle:enabled",),
        )


def _loop(policy) -> AgentLoop:
    return AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())


def _sent(status: DispatchStatus = DispatchStatus.SENT, success: bool = True) -> ActionResult:
    error = None if success else ActionError.EXECUTION_FAILED
    return ActionResult("*", status, "dom", success, error)


def test_initial_satisfaction_is_zero_execution_done() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment([_world("obs-1", True)])
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy([]))).run(environment, _task())
        assert result.status == AgentLoopStatus.DONE
        assert result.execution_count == 0
        assert result.observation_count == 1

    asyncio.run(scenario())


def test_sent_unknown_confirmed_effect_executes_once_and_completes() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("obs-1", False), _world("obs-2", True)],
            [_sent(DispatchStatus.SENT_UNKNOWN, False)],
        )
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first"]))).run(environment, _task())
        assert result.status == AgentLoopStatus.DONE
        assert result.execution_count == 1
        assert result.observation_count == 2

    asyncio.run(scenario())


def test_sent_unknown_unconfirmed_effect_waits_without_replay() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("obs-1", False), _world("obs-2", False)],
            [_sent(DispatchStatus.SENT_UNKNOWN, False)],
        )
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first"]))).run(environment, _task())
        assert result.status == AgentLoopStatus.WAITING_USER
        assert result.execution_count == 1
        assert len(environment.executed_requests) == 1

    asyncio.run(scenario())


def test_unknown_action_and_private_parameter_injection_are_zero_execution() -> None:
    async def scenario(decision) -> AgentLoopStatus:
        environment = StaticEnvironment([_world("obs-1", False)])
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy([decision]))).run(environment, _task())
        assert result.execution_count == 0
        return result.status

    assert asyncio.run(scenario(SelectAction("not-offered"))) == AgentLoopStatus.BLOCKED
    assert asyncio.run(scenario(SelectAction("not-offered", {"selector": "#other"}))) == AgentLoopStatus.BLOCKED


def test_selector_injection_on_offered_action_is_rejected() -> None:
    class InjectingPolicy:
        async def decide(self, task, world, action_space, recent_turns, optional_plan):
            del task, world, recent_turns, optional_plan
            return SelectAction(action_space.options[0].action_id, {"selector": "#other"})

    async def scenario() -> None:
        environment = StaticEnvironment([_world("obs-1", False)])
        result = await AgentEpisodeRunner(_loop(InjectingPolicy())).run(environment, _task())
        assert result.status == AgentLoopStatus.BLOCKED
        assert result.execution_count == 0

    asyncio.run(scenario())


def test_policy_finish_does_not_complete_an_unsatisfied_task() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment([_world("obs-1", False)])
        environment = StaticEnvironment([_world("obs-1", False), _world("obs-2", True)], [_sent()])
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy([Finish({"claim": "done"}), "first"]))).run(
            environment, _task()
        )
        assert result.status == AgentLoopStatus.DONE
        assert result.execution_count == 1
        assert isinstance(result.turns[0].decision, Finish)

    asyncio.run(scenario())


def test_transport_success_without_state_change_is_not_done() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("obs-1", False), _world("obs-2", False)],
            [_sent()],
        )
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first", Stop("no progress")]))).run(
            environment, _task()
        )
        assert result.status == AgentLoopStatus.FAILED
        assert result.execution_count == 1
        assert result.turns[0].task_evaluation.status == TaskEvaluationStatus.INCOMPLETE

    asyncio.run(scenario())


def test_reused_post_action_observation_is_rejected() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment([_world("obs-1", False), _world("obs-1", True)], [_sent()])
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first"]))).run(environment, _task())
        assert result.status == AgentLoopStatus.FAILED
        assert "reused" in result.message

    asyncio.run(scenario())


def test_non_low_risk_action_waits_for_confirmation_with_zero_execution() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment([_world("obs-1", False, risk=ActionRisk.MEDIUM)])
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first"]))).run(environment, _task())
        assert result.status == AgentLoopStatus.WAITING_CONFIRMATION
        assert result.execution_count == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("risk_profile", [RiskProfile.MEDIUM, RiskProfile.HIGH])
def test_medium_or_high_task_waits_even_for_low_risk_option(risk_profile: RiskProfile) -> None:
    async def scenario() -> None:
        task = replace(_task(), risk_profile=risk_profile)
        environment = StaticEnvironment([_world("obs-1", False)])
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first"]))).run(environment, task)

        assert result.status == AgentLoopStatus.WAITING_CONFIRMATION
        assert result.execution_count == 0
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_read_only_task_cannot_select_an_effectful_option() -> None:
    async def scenario() -> None:
        world = _world("obs-1", False)
        effectful_option = _loop(ScriptedPolicy([])).action_space_builder.build(_task(), world).options[0]
        task = TaskGoal("inspect", "Inspect shared state")
        environment = StaticEnvironment([world])
        result = await AgentEpisodeRunner(
            _loop(ScriptedPolicy([SelectAction(effectful_option.action_id)]))
        ).run(environment, task)

        assert result.status == AgentLoopStatus.BLOCKED
        assert result.execution_count == 0

    asyncio.run(scenario())


def test_stale_binding_reobserves_with_zero_executor_calls() -> None:
    class StaleEnvironment(StaticEnvironment):
        def is_current(self, request):
            del request
            return False

    async def scenario() -> None:
        environment = StaleEnvironment([_world("obs-1", False), _world("obs-2", False)])
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first", Stop("still stale")]))).run(
            environment, _task()
        )
        assert result.status == AgentLoopStatus.FAILED
        assert result.execution_count == 0
        assert environment.executed_requests == []
        assert result.observation_count == 2

    asyncio.run(scenario())


def test_recent_turns_are_bounded() -> None:
    async def scenario() -> None:
        observations = [_world(f"obs-{index}", False) for index in range(20)]
        decisions = [Reobserve("refresh") for _ in range(15)] + [Stop("enough")]
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(decisions))).run(
            StaticEnvironment(observations),
            _task(),
        )
        assert len(result.turns) == 12

    asyncio.run(scenario())


def test_sent_unknown_verified_effect_continues_when_task_is_incomplete() -> None:
    class IncompleteTaskEvaluator:
        async def evaluate(self, task, observation):
            del task, observation
            return TaskEvaluation(TaskEvaluationStatus.INCOMPLETE, "more work remains")

    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("obs-1", False), _world("obs-2", True)],
            [_sent(DispatchStatus.SENT_UNKNOWN, False)],
        )
        loop = AgentLoop(ScriptedPolicy(["first", Stop("next objective unavailable")]), SharedActionEvaluator(), IncompleteTaskEvaluator())
        result = await AgentEpisodeRunner(loop).run(environment, _task())
        assert result.status == AgentLoopStatus.FAILED
        assert result.execution_count == 1
        assert "unknown" not in result.message

    asyncio.run(scenario())


def test_observation_budget_is_reserved_before_execution() -> None:
    async def scenario() -> None:
        task = TaskGoal(
            "enable-shared",
            "Enable shared state",
            allowed_effects=("shared_state_enabled",),
            risk_profile=RiskProfile.LOW,
            loop_budget=LoopBudget(max_turns=2, max_observations=2),
        )
        environment = StaticEnvironment([_world("obs-1", False), _world("obs-2", False)])
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy([Reobserve("refresh"), "first"]))).run(
            environment, task
        )
        assert result.status == AgentLoopStatus.FAILED
        assert "observation budget" in result.message
        assert result.execution_count == 0

    asyncio.run(scenario())


def test_wrong_action_result_lineage_is_rejected_before_evaluation() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("obs-1", False), _world("obs-2", True)],
            [ActionResult("wrong-request", DispatchStatus.SENT, "wrong-backend", True)],
        )
        result = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first"]))).run(environment, _task())
        assert result.status == AgentLoopStatus.FAILED
        assert "lineage" in result.message
        assert result.turns[0].action_evaluation is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("request_id", "backend"),
    [("wrong-request", "dom"), ("*", "wrong-backend")],
)
def test_not_sent_wrong_lineage_fails_before_evaluation(request_id: str, backend: str) -> None:
    class FailIfEvaluated(SharedActionEvaluator):
        async def evaluate(self, task, before, request, result, after):
            raise AssertionError("ActionEvaluator must not run for wrong NOT_SENT lineage")

    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("obs-1", False)],
            [
                ActionResult(
                    request_id,
                    DispatchStatus.NOT_SENT,
                    backend,
                    False,
                    ActionError.EXECUTION_FAILED,
                )
            ],
        )
        loop = AgentLoop(ScriptedPolicy(["first"]), FailIfEvaluated(), SharedTaskEvaluator())
        result = await AgentEpisodeRunner(loop).run(environment, _task())

        assert result.status == AgentLoopStatus.FAILED
        assert "lineage" in result.message
        assert len(environment.executed_requests) == 1

    asyncio.run(scenario())

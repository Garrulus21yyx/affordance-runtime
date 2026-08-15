import asyncio
from dataclasses import dataclass

from affordance_runtime.actions import ActionBinding, ActionRisk
from affordance_runtime.agent import Abort, RequestActionPage, RunStatus, SelectAction
from affordance_runtime.agent.decisions import AbortCategory
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution.contracts import ActionResult, DispatchStatus
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.task.contracts import criterion_id
from affordance_runtime.world import (
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
    WorldObservation,
)


def _world(observation_id: str, enabled: bool) -> WorldObservation:
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
        risk=ActionRisk.LOW,
    )
    fact = StateFact(
        f"fact:{observation_id}:enabled",
        target.target_id,
        "enabled",
        enabled,
        observation_id,
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
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def _task() -> TaskGoal:
    return TaskGoal(
        "enable-shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        success_criteria=({"target_id": "shared-toggle", "state": {"enabled": True}},),
        risk_profile=RiskProfile.LOW,
    )


@dataclass
class CorePolicy:
    choice: str

    async def decide(self, context):
        if self.choice == "first_action":
            return SelectAction(context.context_id, context.actions.options[0].action_id)
        if self.choice == "action_page":
            return RequestActionPage(context.context_id, query="toggle")
        raise AssertionError("policy should not be called")


class CoreTaskEvaluator:
    async def evaluate(self, task, observation):
        enabled = bool(observation.targets[0].state.get("enabled"))
        fact_ref = observation.facts[0].fact_id
        criteria = tuple(
            CriterionEvaluation(
                criterion_id(item),
                (
                    CriterionEvaluationStatus.SATISFIED
                    if enabled
                    else CriterionEvaluationStatus.UNSATISFIED
                ),
                (fact_ref,),
                "criterion satisfied" if enabled else "criterion unsatisfied",
            )
            for item in task.success_criteria
        )
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE if enabled else TaskEvaluationStatus.INCOMPLETE,
            "shared state is enabled" if enabled else "shared state is disabled",
            criteria,
            (fact_ref,) if enabled else (),
        )


class CoreActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, result
        return ActionEvaluation(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ActionEvaluationStatus.EFFECT_CONFIRMED,
            "state changed",
            (after.facts[0].fact_id,),
        )


def _runtime(choice: str) -> TargetRuntime:
    return TargetRuntime(
        AgentDecisionPorts(CorePolicy(choice)),
        CoreActionEvaluator(),
        CoreTaskEvaluator(),
    )


def test_core_runtime_reuses_production_boundaries_and_completes_one_action() -> None:
    async def scenario() -> None:
        runtime = _runtime("first_action")
        loop = runtime.build_core_loop()
        assert loop.decision_ports is runtime.decision_ports
        assert loop.action_space_builder is runtime.action_space_builder
        assert loop.binder is runtime.binder
        assert loop.context_builder is runtime.context_builder

        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )
        state = await runtime.run_core_task(environment, _task())

        assert state.status is RunStatus.DONE
        assert state.current_world.observation_id == "after"
        assert state.observation_count == 2
        assert state.execution_count == 1
        assert state.last_step is not None
        assert state.last_step.action_evaluation is not None
        assert state.last_step.action_evaluation.status is ActionEvaluationStatus.EFFECT_CONFIRMED
        assert environment.execute_calls == 1

    asyncio.run(scenario())


def test_unmigrated_decision_path_stops_explicitly() -> None:
    async def scenario() -> None:
        environment = ScriptedEnvironment(initial_observation=_world("before", False))
        state = await _runtime("action_page").run_core_task(environment, _task())

        assert state.status is RunStatus.BLOCKED
        assert state.last_step is not None
        assert state.last_step.feedback == "decision_path_not_migrated"
        assert state.execution_count == 0

    asyncio.run(scenario())


def test_nonterminal_action_is_visible_before_the_next_decision() -> None:
    @dataclass
    class FeedbackAwarePolicy:
        turns: int = 0

        async def decide(self, context):
            self.turns += 1
            if self.turns == 1:
                assert not context.history.items
                return SelectAction(context.context_id, context.actions.options[0].action_id)
            previous = context.history.items
            assert len(previous) == 1
            assert previous[0].semantic_action == "activate"
            assert previous[0].dispatch_status == DispatchStatus.SENT
            assert previous[0].action_evaluation_status == ActionEvaluationStatus.NO_EFFECT_CONFIRMED
            assert previous[0].task_evaluation_status == TaskEvaluationStatus.INCOMPLETE
            assert previous[0].reason == "state did not change"
            return Abort(context.context_id, "feedback projection verified", AbortCategory.USER_REQUEST)

    class NoEffectActionEvaluator:
        async def evaluate(self, task, before, request, result, after):
            del task, result
            return ActionEvaluation(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
                "state did not change",
                (after.facts[0].fact_id,),
            )

    async def scenario() -> None:
        policy = FeedbackAwarePolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            NoEffectActionEvaluator(),
            CoreTaskEvaluator(),
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", False),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )
        state = await runtime.run_core_task(environment, _task())

        assert state.status is RunStatus.CANCELLED
        assert policy.turns == 2
        assert len(state.recent_actions) == 1
        assert environment.execute_calls == 1

    asyncio.run(scenario())

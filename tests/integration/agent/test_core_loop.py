import asyncio
from dataclasses import dataclass, replace

import pytest

from affordance_runtime.actions import ActionBinding, ActionRisk
from affordance_runtime.agent import (
    Abort,
    AskUser,
    LocalToolResult,
    RequestActionPage,
    RunStatus,
    SelectAction,
    Wait,
)
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
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.task.contracts import criterion_id
from affordance_runtime.world import (
    ObservationSourceProfile,
    ObservationStructureNode,
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


def _count_world() -> WorldObservation:
    base = _world("count", False)
    source = base.sources[0]
    counted_source = replace(
        source,
        structure=(
            ObservationStructureNode(
                "group",
                "group",
                "Blocks",
                child_structure_ids=("block:1", "block:2"),
            ),
            ObservationStructureNode(
                "block:1",
                "graphics-symbol",
                "",
                parent_structure_id="group",
            ),
            ObservationStructureNode(
                "block:2",
                "graphics-symbol",
                "",
                parent_structure_id="group",
            ),
            ObservationStructureNode(
                "group:2",
                "group",
                "More blocks",
                child_structure_ids=("block:3", "block:4", "block:5"),
            ),
            ObservationStructureNode(
                "block:3",
                "graphics-symbol",
                "",
                parent_structure_id="group:2",
            ),
            ObservationStructureNode(
                "block:4",
                "graphics-symbol",
                "",
                parent_structure_id="group:2",
            ),
            ObservationStructureNode(
                "block:5",
                "graphics-symbol",
                "",
                parent_structure_id="group:2",
            ),
        ),
        structure_total_count=7,
    )
    fused = WorldFusion().fuse((counted_source,))
    assert fused.observation is not None
    return fused.observation


@dataclass
class CorePolicy:
    choice: str
    turns: int = 0

    async def decide(self, context):
        self.turns += 1
        if self.choice == "first_action":
            return SelectAction(
                context.context_id,
                context.actions.options[0].action_id,
                tool_call_id="provider-call:test",
            )
        if self.choice == "action_page":
            if self.turns == 1:
                return RequestActionPage(context.context_id, query="toggle")
            assert context.actions.active_query == "toggle"
            assert context.recent_steps.items[-1].semantic_action == "next_actions"
            return Abort(context.context_id, "page observed", AbortCategory.USER_REQUEST)
        if self.choice == "wait":
            if self.turns == 1:
                return Wait(context.context_id, "allow interface to settle", 5)
            return Abort(context.context_id, "wait observed", AbortCategory.USER_REQUEST)
        if self.choice == "ask_user":
            if self.turns == 1:
                return AskUser(context.context_id, "Which value?", ("value",))
            assert context.task.public_inputs["value"] == "provided"
            assert context.recent_steps.items[-1].reason == "user_input_received"
            return Abort(context.context_id, "input observed", AbortCategory.USER_REQUEST)
        if self.choice == "count_children":
            if self.turns == 1:
                return LocalToolResult(
                    context.context_id,
                    "count_children",
                    {"containers": ("N1", "N4")},
                    {"counts": {"N1": 2, "N4": 3}, "total": 5},
                    "provider-call:count",
                )
            step = context.recent_steps.items[-1]
            assert step.semantic_action == "count_children"
            assert step.semantic_summary["result"] == {
                "counts": {"N1": 2, "N4": 3},
                "total": 5,
            }
            return Abort(context.context_id, "count observed", AbortCategory.USER_REQUEST)
        if self.choice == "confirm_once":
            if self.turns == 1:
                return SelectAction(context.context_id, context.actions.options[0].action_id)
            assert context.recent_steps.items[-1].reason == "confirmation_declined"
            return Abort(context.context_id, "decline observed", AbortCategory.USER_REQUEST)
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


def _runtime(choice: str, *, wait_controller=None) -> TargetRuntime:
    return TargetRuntime(
        AgentDecisionPorts(CorePolicy(choice)),
        CoreActionEvaluator(),
        CoreTaskEvaluator(),
        goal_compiler=NotRequiredGoalCompiler("atomic_core_loop_test"),
        **({"wait_controller": wait_controller} if wait_controller is not None else {}),
    )


def test_core_runtime_reuses_production_boundaries_and_completes_one_action() -> None:
    async def scenario() -> None:
        runtime = _runtime("first_action")
        loop = runtime.build_loop()
        assert loop.decision_ports is runtime.decision_ports
        assert loop.action_space_builder is runtime.action_space_builder
        assert loop.binder is runtime.binder
        assert loop.context_builder is runtime.context_builder

        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )
        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.DONE
        assert state.current_world.observation_id == "after"
        assert state.observation_count == 2
        assert state.execution_count == 1
        assert state.last_step is not None
        assert state.last_step.decision.tool_call_id == "provider-call:test"
        assert state.last_step.execution is not None
        assert state.last_step.execution.request.tool_call_id == "provider-call:test"
        assert state.last_step.action_evaluation is not None
        assert state.last_step.action_evaluation.status is ActionEvaluationStatus.EFFECT_CONFIRMED
        assert environment.execute_calls == 1

        with pytest.raises(ValueError, match="does not match"):
            replace(
                state.last_step,
                action_evaluation=replace(
                    state.last_step.action_evaluation,
                    request_id="request:wrong",
                ),
            )
        with pytest.raises(ValueError, match="tool call lineage"):
            replace(
                state.last_step,
                decision=replace(state.last_step.decision, tool_call_id="provider-call:wrong"),
            )

    asyncio.run(scenario())


def test_core_runtime_owns_count_result_and_pairs_it_with_the_request() -> None:
    async def scenario() -> None:
        runtime = _runtime("count_children")
        environment = ScriptedEnvironment(initial_observation=_count_world())

        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.CANCELLED
        assert state.execution_count == 0
        assert state.observation_count == 1
        assert state.recent_steps[0].semantic_summary["result"] == {
            "counts": {"N1": 2, "N4": 3},
            "total": 5,
        }

    asyncio.run(scenario())


def test_action_page_is_installed_for_the_next_turn() -> None:
    async def scenario() -> None:
        environment = ScriptedEnvironment(initial_observation=_world("before", False))
        state = await _runtime("action_page").run_task(environment, _task())

        assert state.status is RunStatus.CANCELLED
        assert state.last_step is not None
        assert state.last_step.feedback == "agent_aborted:user_request"
        assert state.execution_count == 0

    asyncio.run(scenario())


def test_wait_uses_runtime_boundary_then_refreshes_observation() -> None:
    @dataclass
    class RecordingWaitController:
        waits: list[int]

        async def wait(self, max_wait_ms: int) -> None:
            self.waits.append(max_wait_ms)

    async def scenario() -> None:
        waiter = RecordingWaitController([])
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            independent_observations=(_world("after-wait", False),),
        )
        state = await _runtime("wait", wait_controller=waiter).run_task(
            environment,
            _task(),
        )

        assert state.status is RunStatus.CANCELLED
        assert state.current_world.observation_id == "after-wait"
        assert state.observation_count == 2
        assert state.waited_ms == 5
        assert waiter.waits == [5]

    asyncio.run(scenario())


def test_user_input_resumes_with_one_consecutive_task_revision() -> None:
    async def scenario() -> None:
        runtime = _runtime("ask_user")
        environment = ScriptedEnvironment(initial_observation=_world("before", False))
        task = _task()
        paused = await runtime.run_task(environment, task)

        assert paused.status is RunStatus.WAITING_USER
        revised = replace(task, inputs={"value": "provided"}, revision=2)
        resumed = await runtime.resume_user(environment, revised, paused)

        assert resumed.status is RunStatus.CANCELLED
        assert resumed.task_revision == 2
        assert resumed.step_count == 2

    asyncio.run(scenario())


def test_confirmation_approval_executes_the_exact_pending_semantics() -> None:
    async def scenario() -> None:
        runtime = _runtime("confirm_once")
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", True),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )
        task = replace(_task(), risk_profile=RiskProfile.MEDIUM)
        paused = await runtime.run_task(environment, task)

        assert paused.status is RunStatus.WAITING_CONFIRMATION
        resumed = await runtime.resume_confirmation(
            environment,
            task,
            paused,
            approved=True,
        )

        assert resumed.status is RunStatus.DONE
        assert resumed.execution_count == 1
        assert resumed.step_count == 1
        assert environment.execute_calls == 1

    asyncio.run(scenario())


def test_confirmation_decline_returns_to_the_model_without_execution() -> None:
    async def scenario() -> None:
        runtime = _runtime("confirm_once")
        environment = ScriptedEnvironment(initial_observation=_world("before", False))
        task = replace(_task(), risk_profile=RiskProfile.MEDIUM)
        paused = await runtime.run_task(environment, task)
        resumed = await runtime.resume_confirmation(
            environment,
            task,
            paused,
            approved=False,
        )

        assert resumed.status is RunStatus.CANCELLED
        assert resumed.execution_count == 0
        assert resumed.step_count == 2
        assert environment.execute_calls == 0

    asyncio.run(scenario())


def test_nonterminal_action_is_visible_before_the_next_decision() -> None:
    @dataclass
    class FeedbackAwarePolicy:
        turns: int = 0

        async def decide(self, context):
            self.turns += 1
            if self.turns == 1:
                assert not context.recent_steps.items
                return SelectAction(context.context_id, context.actions.options[0].action_id)
            previous = context.recent_steps.items
            assert len(previous) == 1
            assert previous[0].semantic_action == "activate"
            assert previous[0].dispatch_status == DispatchStatus.SENT
            assert previous[0].action_evaluation_status == ActionEvaluationStatus.NO_EFFECT_CONFIRMED
            assert previous[0].task_evaluation_status == TaskEvaluationStatus.INCOMPLETE
            assert previous[0].reason == "state did not change"
            assert previous[0].semantic_summary["feedback_code"] == "action_no_effect_change_strategy"
            assert previous[0].target_snapshot == {
                "role": "button",
                "label": "Enable shared state",
                "before_state": {"enabled": False},
                "after_state": {"enabled": False},
            }
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
            goal_compiler=NotRequiredGoalCompiler("atomic_core_loop_test"),
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", False),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )
        state = await runtime.run_task(environment, _task())

        assert state.status is RunStatus.CANCELLED
        assert policy.turns == 2
        assert len(state.recent_steps) == 1
        assert environment.execute_calls == 1

    asyncio.run(scenario())

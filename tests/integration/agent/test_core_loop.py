import asyncio
from dataclasses import dataclass, field, replace

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
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.decisions import AbortCategory
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import (
    ActionOutcome,
    CriterionEvaluation,
    CriterionEvaluationStatus,
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution.contracts import ActionResult, DispatchStatus
from affordance_runtime.goals import NotRequired, NotRequiredGoalCompiler
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
from affordance_runtime.world.acquisition import ObservationRequestKind, WorldObservationRequest


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
            assert context.recent_steps.items[-1].semantic_action == "find_actions"
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


class CoreActionOutcomeProjector:
    async def evaluate(self, task, before, request, result, after):
        del task, result
        return ActionOutcome(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ObservedChange.CHANGED,
            LocalPostconditionStatus.UNKNOWN,
            EvidenceMethod.STRUCTURAL,
            "state changed",
            (after.facts[0].fact_id,),
        )


def _runtime(choice: str, *, wait_controller=None) -> TargetRuntime:
    return TargetRuntime(
        AgentDecisionPorts(CorePolicy(choice)),
        CoreActionOutcomeProjector(),
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
        assert state.last_step.action_outcome is not None
        assert state.last_step.action_outcome.observed_change is ObservedChange.CHANGED
        assert environment.execute_calls == 1

        with pytest.raises(ValueError, match="does not match"):
            replace(
                state.last_step,
                action_outcome=replace(
                    state.last_step.action_outcome,
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
            assert previous[0].target is not None
            assert previous[0].target.role == "button"
            assert previous[0].target.label == "Enable shared state"
            assert previous[0].dispatch_status == DispatchStatus.SENT
            assert previous[0].local_postcondition == LocalPostconditionStatus.UNKNOWN
            assert previous[0].transition["observed_change"] == ObservedChange.UNCHANGED
            assert previous[0].transition["evidence_method"] == EvidenceMethod.STRUCTURAL
            assert previous[0].task_evaluation_status == TaskEvaluationStatus.INCOMPLETE
            assert previous[0].reason == "state did not change"
            assert previous[0].semantic_summary["feedback_code"] == "action_unchanged_change_strategy"
            assert previous[0].transition == {
                    "role": "button",
                    "label": "Enable shared state",
                    "before_world": "before",
                    "after_world": "after",
                    "before_state": {"enabled": False},
                    "after_state": {"enabled": False},
                "observed_change": "unchanged",
                "evidence_method": "structural",
            }
            return Abort(context.context_id, "feedback projection verified", AbortCategory.USER_REQUEST)

    class NoEffectActionOutcomeProjector:
        async def evaluate(self, task, before, request, result, after):
            del task, result
            return ActionOutcome(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ObservedChange.UNCHANGED,
                LocalPostconditionStatus.UNKNOWN,
                EvidenceMethod.STRUCTURAL,
                "state did not change",
                (after.facts[0].fact_id,),
            )

    async def scenario() -> None:
        policy = FeedbackAwarePolicy()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            NoEffectActionOutcomeProjector(),
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
        assert state.last_step is not None
        assert state.last_step.policy_observation is not None
        assert environment.execute_calls == 1

    asyncio.run(scenario())


def test_executor_episode_can_yield_and_reinitialize_from_fresh_world_without_reset() -> None:
    @dataclass
    class EpisodePolicy:
        actions: list[str]

        async def decide(self, context):
            action = self.actions.pop(0)
            if action == "activate":
                return SelectAction(
                    context.context_id,
                    context.actions.options[0].action_id,
                    tool_call_id="provider-call:episode-1",
                )
            return Abort(context.context_id, "episode observed fresh world", AbortCategory.USER_REQUEST)

    @dataclass(frozen=True)
    class RecordingContextBuilder(ContextBuilder):
        seen_observation_ids: list[str] = field(default_factory=list)

        def build(self, task, observation, action_space, task_evaluation, *args, **kwargs):
            self.seen_observation_ids.append(observation.observation_id)
            return super().build(task, observation, action_space, task_evaluation, *args, **kwargs)

    @dataclass
    class ExplodingGoalCompiler:
        calls: int = 0

        async def compile(self, request):
            del request
            self.calls += 1
            raise AssertionError("episode initialization must not call GoalCompiler")

    async def scenario() -> None:
        policy = EpisodePolicy(["activate", "abort"])
        context_builder = RecordingContextBuilder()
        compiler = ExplodingGoalCompiler()
        runtime = TargetRuntime(
            AgentDecisionPorts(policy),
            CoreActionOutcomeProjector(),
            CoreTaskEvaluator(),
            context_builder=context_builder,
            goal_compiler=compiler,
        )
        loop = runtime.build_loop()
        task = _task()
        goal_resolution = NotRequired(task.revision, "manager_supplied_episode_goal")
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after-action", False),),
            independent_observations=(_world("fresh-current", False),),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
        )

        initial = await environment.reset(task)
        assert initial.observation is not None
        first = await loop.initialize_from_world(
            task,
            initial.observation,
            goal_resolution,
            max_turns=1,
            yield_on_budget_exhaustion=True,
        )
        yielded = await loop.continue_run(environment, task, first)

        assert yielded.status is RunStatus.YIELDED
        assert yielded.current_world.observation_id == "after-action"
        assert yielded.recent_steps[-1].semantic_action == "activate"
        assert environment.reset_calls == 1

        refreshed = await environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "fresh world before next executor episode",
            )
        )
        assert refreshed.observation is not None
        second = await loop.initialize_from_world(
            task,
            refreshed.observation,
            goal_resolution,
            max_turns=1,
            yield_on_budget_exhaustion=True,
        )
        resumed = await loop.continue_run(environment, task, second)

        assert resumed.status is RunStatus.CANCELLED
        assert resumed.current_world.observation_id == "fresh-current"
        assert environment.reset_calls == 1
        assert context_builder.seen_observation_ids == ["before", "fresh-current"]
        assert compiler.calls == 0

    asyncio.run(scenario())

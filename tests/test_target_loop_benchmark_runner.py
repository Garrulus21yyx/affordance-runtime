import asyncio
from dataclasses import dataclass

from affordance_runtime.agent import AgentLoopStatus, SelectAction
from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkCase, BenchmarkComposition
from affordance_runtime.benchmarks.target_loop.runner import run_suite
from affordance_runtime.evaluation import ActionEvaluation, ActionEvaluationStatus, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.task import LoopBudget, RiskProfile, TaskGoal
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    ActionBinding,
    CoverageState,
    ObservationCapabilities,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)


@dataclass
class NeverPolicy:
    calls: int = 0

    async def decide(self, context):
        self.calls += 1
        raise AssertionError("complete task must not call policy")


class ActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        return ActionEvaluation(request.request_id, before.observation_id, after.observation_id, ActionEvaluationStatus.UNKNOWN, "unused")


class CompleteEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(task.task_id, observation.observation_id, TaskEvaluationStatus.BLOCKED, "fixture terminal")


def test_runner_is_sequential_isolated_and_always_cleans_up() -> None:
    events = []

    class Environment(StaticEnvironment):
        async def reset(self, task):
            events.append(f"start:{task.task_id}")
            return await super().reset(task)

        async def close(self):
            events.append(f"close:{self.task.task_id}")

    def case(identity):
        return BenchmarkCase(
            identity, "suite", identity,
            lambda: TaskGoal(identity, "Already complete"),
            lambda _metrics: Environment([WorldObservation(identity, (), (), (), {"static": CoverageState.COMPLETE})]),
            lambda _metrics: BenchmarkComposition(NeverPolicy(), ActionEvaluator(), CompleteEvaluator()),
            (AgentLoopStatus.BLOCKED,), 2.0, 7, ("observations",),
        )

    from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest

    result = asyncio.run(run_suite(BenchmarkManifest(
        "target-loop-manifest.v1", "suite", "deterministic", 7, (case("a"), case("b")),
    )))
    assert result.acceptance.accepted
    assert events == ["start:a", "close:a", "start:b", "close:b"]
    assert [item.case_id for item in result.cases] == ["a", "b"]


def _action_world(observation_id: str) -> WorldObservation:
    target = SemanticTarget("target:button", "button", "Continue")
    fact = StateFact(f"fact:{observation_id}:enabled", target.target_id, "enabled", True, observation_id)
    binding = ActionBinding(
        f"binding:{observation_id}", observation_id, observation_id, f"revision:{observation_id}",
        f"fingerprint:{observation_id}", target.target_id, target.target_id, "dom", "dom",
        "activate", "click", "local_reversible", ("advanced",),
        {"type": "object", "properties": {}, "additionalProperties": False}, {},
    )
    source = SurfaceObservation(
        observation_id, "dom", f"revision:{observation_id}", ObservationSourceProfile.dom(),
        (target,), (fact,), (binding,),
    )
    return WorldObservation(
        observation_id, (target,), (fact,), (binding,), {"dom": CoverageState.COMPLETE},
        sources=(source,),
    )


def test_watchdog_timeout_preserves_privacy_safe_partial_episode() -> None:
    class ExecuteThenHangPolicy:
        def __init__(self) -> None:
            self.calls = 0

        async def decide(self, context):
            self.calls += 1
            if self.calls == 1:
                return SelectAction(context.context_id, context.actions.options[0].action_id)
            await asyncio.Event().wait()

    class IncompleteEvaluator:
        async def evaluate(self, task, observation):
            return TaskEvaluation(
                task.task_id, observation.observation_id, TaskEvaluationStatus.INCOMPLETE, "incomplete"
            )

    policy = ExecuteThenHangPolicy()

    def task():
        return TaskGoal(
            "timeout", "Exercise timeout snapshot", allowed_effects=("advanced",),
            risk_profile=RiskProfile.LOW, loop_budget=LoopBudget(4, 6),
        )
    case = BenchmarkCase(
        "timeout", "suite", "timeout snapshot", task,
        lambda _metrics: StaticEnvironment(
            [_action_world("observation:one"), _action_world("observation:two")],
            [ActionResult("*", DispatchStatus.SENT, "dom", True)],
        ),
        lambda _metrics: BenchmarkComposition(policy, ActionEvaluator(), IncompleteEvaluator()),
        (AgentLoopStatus.FAILED,), 0.05, 7, ("observations", "executions", "turns"),
    )
    from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest

    result = asyncio.run(run_suite(BenchmarkManifest(
        "target-loop-manifest.v1", "suite", "deterministic", 7, (case,),
    ))).cases[0]

    assert result.failure_reason == "case timeout"
    assert result.termination_origin == "harness_watchdog"
    assert result.case_failure_code == "case_timeout"
    assert result.partial_episode_available is True
    assert result.terminal_reason_code is None
    assert result.measurements["observations"].value == 2
    assert result.measurements["executions"].value == 1
    assert result.measurements["turns"].value == 1
    assert result.latest_task_status == "incomplete"
    assert result.latest_action_evaluation_status == "unknown"
    assert policy.calls == 2


def test_runner_preserves_typed_agent_failure_without_message_matching() -> None:
    class Policy:
        async def decide(self, context):
            return SelectAction(context.context_id, context.actions.options[0].action_id)

    class IncompleteEvaluator:
        async def evaluate(self, task, observation):
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.INCOMPLETE,
                "incomplete",
            )

    def task():
        return TaskGoal(
            "typed-failure",
            "Preserve typed failure",
            allowed_effects=("advanced",),
            risk_profile=RiskProfile.LOW,
        )

    case = BenchmarkCase(
        "typed-failure",
        "suite",
        "typed failure",
        task,
        lambda _metrics: StaticEnvironment(
            initial_observation=_action_world("observation:one"),
            results=(ActionResult("*", DispatchStatus.SENT, "dom", True),),
            observation_capabilities=ObservationCapabilities(False, True),
        ),
        lambda _metrics: BenchmarkComposition(
            Policy(),
            ActionEvaluator(),
            IncompleteEvaluator(),
        ),
        (AgentLoopStatus.WAITING_USER,),
        2.0,
        7,
        ("observations", "executions", "turns"),
    )
    from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest

    result = asyncio.run(
        run_suite(
            BenchmarkManifest(
                "target-loop-manifest.v1",
                "suite",
                "deterministic",
                7,
                (case,),
            )
        )
    ).cases[0]

    assert result.case_failure_code == "post_action_capability_unavailable"
    assert result.failure_code == "post_action_capability_unavailable"
    assert str(result.failure_origin) == "post_action_observation"

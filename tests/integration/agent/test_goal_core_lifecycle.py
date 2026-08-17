from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace

from affordance_runtime.agent import Abort, AskUser, RunStatus
from affordance_runtime.agent.decisions import AbortCategory
from affordance_runtime.agent.observability import RunTraceRecorder
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.goals import (
    Failed,
    GoalCompileTrigger,
    GoalPlanProposal,
    NeedsInput,
    NotRequired,
    Ready,
    Unsupported,
)
from tests.integration.agent.test_core_loop import CoreActionEvaluator, CoreTaskEvaluator, _task, _world


def _proposal(revision: int):
    return GoalPlanProposal(revision, (
        {
            "id": "complete_requested_changes",
            "objective": "Complete all requested visible changes.",
            "done_when": "Every relevant item visibly has the requested state.",
            "depends_on": (),
            "final": False,
        },
    ))


@dataclass
class SequenceCompiler:
    outcomes: list[object]
    requests: list[object] = field(default_factory=list)

    async def compile(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        return outcome(request) if callable(outcome) else outcome


@dataclass
class InspectPolicy:
    calls: int = 0

    async def decide(self, context):
        self.calls += 1
        assert context.goal_plan.resolution in {"ready", "not_required", "unavailable"}
        return Abort(context.context_id, "inspected", AbortCategory.USER_REQUEST)


def _runtime(policy, compiler, trace=None):
    return TargetRuntime(
        AgentDecisionPorts(policy),
        CoreActionEvaluator(),
        CoreTaskEvaluator(),
        goal_compiler=compiler,
        **({"trace_sink": trace} if trace is not None else {}),
    )


def test_ready_plan_compiles_once_and_remains_static_across_the_single_loop() -> None:
    async def scenario():
        compiler = SequenceCompiler([lambda request: _proposal(request.task.revision)])
        policy = InspectPolicy()
        state = await _runtime(policy, compiler).run_task(
            ScriptedEnvironment(initial_observation=_world("initial", False)), _task()
        )
        assert len(compiler.requests) == 1
        assert compiler.requests[0].trigger is GoalCompileTrigger.TASK_START
        assert policy.calls == 1
        assert state.status is RunStatus.CANCELLED
        assert isinstance(state.goal_resolution, Ready)
        assert state.goal_resolution.accepted_plan.items[0].id == "complete_requested_changes"
        assert state.goal_plan_version_counter == 1
        assert not hasattr(state, "current_goal_snapshot")
    asyncio.run(scenario())


def test_unavailable_dispositions_preserve_ordinary_action_turn_and_trace() -> None:
    async def scenario():
        for outcome in (NotRequired(1, "atomic"), Unsupported(1, "unsupported"), Failed(1, "provider_failed")):
            trace = RunTraceRecorder()
            policy = InspectPolicy()
            state = await _runtime(policy, SequenceCompiler([outcome]), trace).run_task(
                ScriptedEnvironment(initial_observation=_world("initial", False)), _task()
            )
            assert policy.calls == 1
            guidance = next(event["goal_guidance"] for event in trace.events if event["event"] == "run_started")
            assert guidance["disposition"] == ("not_required" if isinstance(outcome, NotRequired) else "unavailable")
            assert state.status is RunStatus.CANCELLED
    asyncio.run(scenario())


def test_needs_input_uses_existing_waiting_user_path_and_revision_recompiles_once() -> None:
    async def scenario():
        compiler = SequenceCompiler([
            NeedsInput(1, "Which value?", ("value",)),
            lambda request: _proposal(request.task.revision),
        ])
        runtime = _runtime(InspectPolicy(), compiler)
        environment = ScriptedEnvironment(initial_observation=_world("initial", False))
        first = await runtime.build_loop().initialize(environment, _task())
        assert first.status is RunStatus.WAITING_USER
        assert isinstance(first.last_step.decision, AskUser)
        revised = replace(_task(), revision=2)
        await runtime.build_loop().resume_user(environment, revised, first)
        assert [request.trigger for request in compiler.requests] == [
            GoalCompileTrigger.TASK_START, GoalCompileTrigger.TASK_REVISION,
        ]
        assert first.task_revision == 2
        assert isinstance(first.goal_resolution, Ready)
    asyncio.run(scenario())

from __future__ import annotations

import asyncio

from affordance_runtime.agent import RunStatus
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.app import (
    TargetRuntime,
)
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.task import (
    LoopBudget,
    NaturalLanguageTaskRequest,
    ReadyTask,
    RiskProfile,
    TaskBoundary,
    TaskInputRequired,
    TaskPolicyRejected,
    ThinTaskIntake,
)
from tests.support.world import fused_world


class NeverPolicy:
    async def decide(self, context):
        del context
        raise AssertionError("terminal initial observation must not call policy")


class UnusedActionOutcomeProjector:
    async def evaluate(self, task, before, request, result, after, public_world_delta):
        del task, before, request, result, after
        raise AssertionError("terminal initial observation must not evaluate an action")


class BlockedTaskEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.BLOCKED,
            "fixture terminal",
        )


def test_thin_intake_admits_stable_semantics_without_gui_identity() -> None:
    outcome = ThinTaskIntake().compile(
        NaturalLanguageTaskRequest(
            "task:save",
            "Save the current form",
            TaskBoundary(
                constraints=("use the current account",),
                allowed_effects=("form_saved",),
                forbidden_effects=("account_deleted",),
                inputs={"display_name": "Ada"},
                success_criteria=({"id": "saved", "predicate": "saved", "value": True},),
                risk_profile=RiskProfile.LOW,
                loop_budget=LoopBudget(4, 8),
            ),
            source_ref="user-message:1",
        )
    )

    assert isinstance(outcome, ReadyTask)
    assert outcome.task.task_id == "task:save"
    assert outcome.task.instruction == "Save the current form"
    assert outcome.task.allowed_effects == ("form_saved",)
    assert outcome.task.inputs == {"display_name": "Ada"}
    assert outcome.source_ref == "user-message:1"
    assert not hasattr(outcome.task, "action_id")
    assert not hasattr(outcome.task, "binding_id")
    assert not hasattr(outcome.task, "selector")


def test_thin_intake_preserves_bounded_official_goal_text_without_reinterpreting_schema() -> None:
    schema_text = '{"$defs":' + (" " * 4_100) + "{}}"
    instruction = f"Retrieve the record.\n---\nFinal response format:\n{schema_text}"

    outcome = ThinTaskIntake().compile(NaturalLanguageTaskRequest("task:official-goal", instruction))

    assert isinstance(outcome, ReadyTask)
    assert outcome.task.instruction == instruction
    assert outcome.task.inputs == {}


def test_thin_intake_returns_closed_nonready_outcomes() -> None:
    missing_effect_authority = ThinTaskIntake().compile(
        NaturalLanguageTaskRequest(
            "task:effect-unknown",
            "Change the current record",
            TaskBoundary(risk_profile=RiskProfile.LOW),
        )
    )
    conflicting_effects = ThinTaskIntake().compile(
        NaturalLanguageTaskRequest(
            "task:effect-conflict",
            "Change the current record",
            TaskBoundary(
                allowed_effects=("record_changed",),
                forbidden_effects=("record_changed",),
                risk_profile=RiskProfile.LOW,
            ),
        )
    )
    private_execution_input = ThinTaskIntake().compile(
        NaturalLanguageTaskRequest(
            "task:private-input",
            "Click the current control",
            TaskBoundary(inputs={"selector": "#save"}),
        )
    )

    assert isinstance(missing_effect_authority, TaskInputRequired)
    assert missing_effect_authority.requested_fields == ("allowed_effects",)
    assert missing_effect_authority.reason_code == "effect_authority_required"
    assert isinstance(conflicting_effects, TaskPolicyRejected)
    assert conflicting_effects.reason_code == "allowed_forbidden_effect_conflict"
    assert isinstance(private_execution_input, ReadyTask)
    assert private_execution_input.task.inputs == {"selector": "#save"}


def test_target_runtime_runs_a_natural_language_request_through_intake() -> None:
    observation = fused_world("observation:initial", surface="static")
    environment = ScriptedEnvironment(initial_observation=observation)
    runtime = TargetRuntime(
        AgentDecisionPorts(NeverPolicy()),
        UnusedActionOutcomeProjector(),
        BlockedTaskEvaluator(),
        goal_compiler=NotRequiredGoalCompiler("atomic_task_intake_test"),
    )

    outcome = asyncio.run(
        runtime.run_request(
            environment,
            NaturalLanguageTaskRequest("task:read", "Inspect the current page"),
        )
    )

    assert outcome.started
    assert isinstance(outcome.intake, ReadyTask)
    assert outcome.state is not None
    assert outcome.state.status is RunStatus.BLOCKED
    assert outcome.intake.task.instruction == "Inspect the current page"


def test_target_runtime_does_not_touch_environment_for_nonready_intake() -> None:
    class Environment:
        reset_calls = 0

        async def reset(self, task):
            del task
            self.reset_calls += 1
            raise AssertionError("nonready intake must not reset an environment")

    environment = Environment()
    runtime = TargetRuntime(
        AgentDecisionPorts(NeverPolicy()),
        UnusedActionOutcomeProjector(),
        BlockedTaskEvaluator(),
        goal_compiler=NotRequiredGoalCompiler("atomic_task_intake_test"),
    )
    outcome = asyncio.run(
        runtime.run_request(
            environment,
            NaturalLanguageTaskRequest(
                "task:missing-authority",
                "Modify the record",
                TaskBoundary(risk_profile=RiskProfile.LOW),
            ),
        )
    )

    assert not outcome.started
    assert isinstance(outcome.intake, TaskInputRequired)
    assert environment.reset_calls == 0

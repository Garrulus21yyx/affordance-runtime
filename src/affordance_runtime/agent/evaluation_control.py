"""Narrow evaluator-proposal validation at AgentLoop boundaries."""

from affordance_runtime.agent.decisions import AgentDecision
from affordance_runtime.agent.policy import ActionEvaluator, TaskEvaluator
from affordance_runtime.agent.state import Turn
from affordance_runtime.evaluation.contracts import ActionEvaluation, TaskEvaluation
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.validation import validate_action_evaluation, validate_task_evaluation
from affordance_runtime.execution.contracts import ActionResult, BoundActionRequest
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation


async def validated_task_evaluation(
    evaluator: TaskEvaluator,
    task: TaskGoal,
    observation: WorldObservation,
) -> TaskEvaluation:
    proposal = await evaluator.evaluate(task, observation)
    return validate_task_evaluation(
        proposal,
        task,
        observation,
        WorldEvidenceIndex.from_observation(observation),
    )


async def validated_action_evaluation(
    evaluator: ActionEvaluator,
    task: TaskGoal,
    before: WorldObservation,
    request: BoundActionRequest,
    result: ActionResult,
    after: WorldObservation,
) -> ActionEvaluation:
    proposal = await evaluator.evaluate(task, before, request, result, after)
    return validate_action_evaluation(
        proposal,
        task,
        request,
        before,
        after,
        WorldEvidenceIndex.from_observation(after),
    )


def untrusted_evaluation_turn(
    before_observation_id: str,
    decision: AgentDecision,
    request: BoundActionRequest,
    result: ActionResult,
    after_observation_id: str,
    action_evaluation: ActionEvaluation | None = None,
) -> Turn:
    return Turn(
        before_observation_id,
        decision,
        request.intent,
        request.request_id,
        result,
        after_observation_id,
        action_evaluation,
    )

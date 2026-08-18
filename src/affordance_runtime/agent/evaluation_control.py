"""Narrow evaluator-proposal validation at CoreAgentLoop boundaries."""

from affordance_runtime.agent.policy import ActionOutcomeProjector, TaskEvaluator
from affordance_runtime.evaluation.contracts import ActionOutcome, TaskEvaluation
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.validation import validate_action_outcome, validate_task_evaluation
from affordance_runtime.execution.contracts import ActionResult, BoundActionRequest
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation


async def validated_task_evaluation(
    evaluator: TaskEvaluator,
    task: TaskGoal,
    observation: WorldObservation,
) -> TaskEvaluation:
    proposal = await evaluator.evaluate(task, observation)
    if not isinstance(proposal, TaskEvaluation):
        raise ValueError("task evaluator returned a malformed result")
    return validate_task_evaluation(
        proposal,
        task,
        observation,
        WorldEvidenceIndex.from_observation(observation),
    )


async def validated_action_outcome(
    evaluator: ActionOutcomeProjector,
    task: TaskGoal,
    before: WorldObservation,
    request: BoundActionRequest,
    result: ActionResult,
    after: WorldObservation,
) -> ActionOutcome:
    proposal = await evaluator.evaluate(task, before, request, result, after)
    if not isinstance(proposal, ActionOutcome):
        raise ValueError("action outcome projector returned a malformed result")
    return validate_action_outcome(
        proposal,
        task,
        request,
        before,
        after,
        WorldEvidenceIndex.from_observation(after),
    )

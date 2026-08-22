"""Narrow evaluator-proposal validation at CoreAgentLoop boundaries."""

from dataclasses import replace

from affordance_runtime.agent.context.world_transition import (
    PublicWorldDelta,
    WorldTransitionProjector,
)
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
    public_world_delta: PublicWorldDelta | None = None,
) -> ActionOutcome:
    if public_world_delta is None and isinstance(before, WorldObservation) and isinstance(
        after, WorldObservation
    ):
        public_world_delta = WorldTransitionProjector().project(before, after)
    proposal = await evaluator.evaluate(
        task,
        before,
        request,
        result,
        after,
        public_world_delta,
    )
    if not isinstance(proposal, ActionOutcome):
        raise ValueError("action outcome projector returned a malformed result")
    if public_world_delta is None:
        public_world_delta = WorldTransitionProjector().project(before, after)
    if proposal.public_world_delta is None:
        proposal = replace(proposal, public_world_delta=public_world_delta)
    validated = validate_action_outcome(
        proposal,
        task,
        request,
        before,
        after,
        WorldEvidenceIndex.from_observation(after),
    )
    if validated.public_world_delta is not public_world_delta:
        raise ValueError("action outcome projector must consume the supplied public World delta")
    return validated

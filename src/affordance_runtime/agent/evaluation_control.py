"""Narrow evaluator-proposal validation at CoreAgentLoop boundaries."""

from dataclasses import replace

from affordance_runtime.agent.context.world_transition import (
    PublicWorldDelta,
    WorldTransitionProjector,
)
from affordance_runtime.agent.policy import ActionOutcomeProjector, TaskEvaluator
from affordance_runtime.evaluation.contracts import ActionOutcome, TaskEvaluation
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.invocation import (
    Evaluated,
    InternalFailure,
    TaskEvaluationAttempt,
    TaskEvaluationInternalError,
    TaskEvaluationStage,
    TaskEvaluationUnavailableError,
    Unavailable,
    task_evaluation_diagnostic_from_exception,
)
from affordance_runtime.evaluation.validation import validate_action_outcome, validate_task_evaluation
from affordance_runtime.execution.contracts import ActionResult, BoundActionRequest
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation


async def validated_task_evaluation(
    evaluator: TaskEvaluator,
    task: TaskGoal,
    observation: WorldObservation,
) -> TaskEvaluation:
    outcome = await validated_task_evaluation_attempt(evaluator, task, observation)
    if isinstance(outcome, Evaluated):
        return outcome.evaluation
    if isinstance(outcome, Unavailable):
        raise TaskEvaluationUnavailableError(outcome)
    if outcome.code == "task_evaluator_invalid_result":
        raise ValueError("task evaluator returned a malformed result")
    raise TaskEvaluationInternalError(outcome)


async def validated_task_evaluation_attempt(
    evaluator: TaskEvaluator,
    task: TaskGoal,
    observation: WorldObservation,
) -> TaskEvaluationAttempt:
    """Return evaluator truth or a typed boundary failure without fabricating UNKNOWN."""

    observation_id = str(getattr(observation, "observation_id", ""))
    try:
        proposal = await evaluator.evaluate(task, observation)
    except TaskEvaluationUnavailableError as exc:
        return exc.outcome
    except TaskEvaluationInternalError as exc:
        return exc.outcome
    except Exception as exc:
        return InternalFailure(
            "task_evaluator_call_failed",
            task_evaluation_diagnostic_from_exception(
                exc,
                stage=TaskEvaluationStage.EVALUATOR_CALL,
                observation_id=observation_id,
            ),
        )
    if not isinstance(proposal, TaskEvaluation):
        exc = TypeError("task evaluator returned a malformed result")
        return InternalFailure(
            "task_evaluator_invalid_result",
            task_evaluation_diagnostic_from_exception(
                exc,
                stage=TaskEvaluationStage.RESULT_CONTRACT,
                observation_id=observation_id,
            ),
        )
    try:
        evidence_index = WorldEvidenceIndex.from_observation(observation)
    except Exception as exc:
        return InternalFailure(
            "task_evaluator_evidence_index_failed",
            task_evaluation_diagnostic_from_exception(
                exc,
                stage=TaskEvaluationStage.EVIDENCE_INDEX,
                observation_id=observation_id,
            ),
        )
    try:
        validated = validate_task_evaluation(proposal, task, observation, evidence_index)
    except Exception as exc:
        return InternalFailure(
            "task_evaluator_validation_failed",
            task_evaluation_diagnostic_from_exception(
                exc,
                stage=TaskEvaluationStage.VALIDATION,
                observation_id=observation_id,
            ),
        )
    return Evaluated(validated)


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

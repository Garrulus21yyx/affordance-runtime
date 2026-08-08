"""Exact request and observation lineage checks for action evaluations."""

from affordance_runtime.evaluation.contracts import ActionEvaluation
from affordance_runtime.execution.contracts import BoundActionRequest
from affordance_runtime.world.contracts import WorldObservation


def evaluation_matches_execution(
    evaluation: ActionEvaluation,
    request: BoundActionRequest,
    before: WorldObservation,
    after: WorldObservation,
) -> bool:
    return (
        evaluation.request_id == request.request_id
        and evaluation.before_observation_id == before.observation_id
        and evaluation.after_observation_id == after.observation_id
    )

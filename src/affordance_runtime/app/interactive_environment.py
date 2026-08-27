"""Final-response authority for ordinary interactive Runtime sessions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace

from affordance_runtime.evaluation.contracts import (
    TaskEvaluation,
    TaskEvaluationStatus,
    TaskOutcomeFact,
    TaskOutcomeKind,
)
from affordance_runtime.execution.contracts import ActionError, ActionResult, DispatchStatus
from affordance_runtime.world.acquisition import (
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.contracts import StateFact
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.finalization import (
    PLAIN_TEXT_FINAL_RESPONSE_CODEC,
    EnvironmentFinalization,
    FinalResponseCodec,
)


@dataclass
class InteractiveTaskEnvironment:
    """Accept one model final response while delegating one authoritative World."""

    wrapped: WorldEnvironment
    final_response_codec: FinalResponseCodec = PLAIN_TEXT_FINAL_RESPONSE_CODEC
    _final_response: str | None = field(default=None, init=False, repr=False)

    def __getattr__(self, name: str):
        return getattr(self.wrapped, name)

    @property
    def supports_finalization(self) -> bool:
        return True

    @property
    def final_response_delivered(self) -> bool:
        return self._final_response is not None

    async def finalize(self, content: str) -> EnvironmentFinalization:
        if self._final_response is not None:
            return EnvironmentFinalization(
                ActionResult(
                    "final-response",
                    DispatchStatus.NOT_SENT,
                    "interaction-session",
                    False,
                    ActionError.INVALID_PARAMETERS,
                )
            )
        self._final_response = content
        post = await self.wrapped.capture(
            WorldObservationRequest(
                ObservationRequestKind.POST_ACTION_FALLBACK,
                "fresh World after interactive final response",
            )
        )
        if post.observation is not None:
            observation = post.observation
            assert post.fusion_outcome is not None
            digest = hashlib.sha256(observation.observation_id.encode()).hexdigest()[:24]
            proof = StateFact(
                f"fact:interactive-final-response:{digest}",
                "interaction-session:final-response",
                "final_response.delivered",
                True,
                "interaction-session",
            )
            post = replace(
                post,
                fusion_outcome=replace(
                    post.fusion_outcome,
                    observation=replace(
                        observation,
                        facts=(*observation.facts, proof),
                    ),
                ),
            )
        return EnvironmentFinalization(
            ActionResult(
                "final-response",
                DispatchStatus.SENT,
                "interaction-session",
                True,
            ),
            post,
        )


@dataclass(frozen=True)
class InteractiveTaskEvaluator:
    """Close an ordinary task only after its final response crossed the session port."""

    environment: InteractiveTaskEnvironment

    async def evaluate(self, task, observation) -> TaskEvaluation:
        delivered = self.environment.final_response_delivered
        status = TaskEvaluationStatus.COMPLETE if delivered else TaskEvaluationStatus.INCOMPLETE
        reason = "interactive_final_response_delivered" if delivered else "interactive_task_running"
        completion_refs = tuple(
            fact.fact_id
            for fact in observation.facts
            if fact.subject_id == "interaction-session:final-response"
            and fact.predicate == "final_response.delivered"
            and fact.value is True
        )
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            status,
            reason,
            completion_evidence_refs=completion_refs if delivered else (),
            outcome=(
                TaskOutcomeFact(
                    TaskOutcomeKind.TERMINAL_SUCCESS,
                    "interactive_final_response_delivered",
                    completion_refs,
                )
                if delivered
                else TaskOutcomeFact(TaskOutcomeKind.RUNNING_INCOMPLETE, "interactive_task_running")
            ),
        )

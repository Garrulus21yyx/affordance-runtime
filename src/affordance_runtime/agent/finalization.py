"""Direct final-response representation and lifecycle boundary."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent.decisions import FinalResponse
from affordance_runtime.evaluation.contracts import TaskEvaluationStatus
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex, public_text_evidence_records
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.world.contracts import WorldObservation


@dataclass(frozen=True)
class FinalResponseAdmission:
    admitted: bool
    rejection_code: str = ""


@dataclass(frozen=True)
class FinalizationProtocolResult:
    """Runtime-owned facts for the one-STOP finalization transition."""

    dispatch_status: DispatchStatus
    post_stop_observation_id: str = ""
    native_evaluator_invoked: bool = False
    native_evaluation_status: TaskEvaluationStatus | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dispatch_status, DispatchStatus):
            raise TypeError("finalization dispatch status must be typed")
        if type(self.native_evaluator_invoked) is not bool:
            raise TypeError("native evaluator invocation fact must be boolean")
        if not isinstance(self.post_stop_observation_id, str):
            raise TypeError("post-STOP observation id must be a string")
        if (
            len(self.post_stop_observation_id) > 512
            or any(ord(character) < 32 for character in self.post_stop_observation_id)
        ):
            raise ValueError("post-STOP observation id must be bounded public text")
        if self.native_evaluation_status is not None and not isinstance(
            self.native_evaluation_status,
            TaskEvaluationStatus,
        ):
            raise TypeError("native evaluation status must be typed")
        if self.dispatch_status is DispatchStatus.NOT_SENT and (
            self.post_stop_observation_id
            or self.native_evaluator_invoked
            or self.native_evaluation_status is not None
        ):
            raise ValueError("an unsent STOP cannot have post-STOP or evaluator facts")
        if self.post_stop_observation_id and not self.native_evaluator_invoked:
            raise ValueError("a captured post-STOP World requires one evaluator invocation")
        if self.native_evaluation_status is not None and not self.native_evaluator_invoked:
            raise ValueError("native evaluation status requires one evaluator invocation")
        if self.native_evaluator_invoked and not self.post_stop_observation_id:
            raise ValueError("native evaluator invocation requires a captured post-STOP World")

    @property
    def stop_send_count(self) -> int:
        return int(self.dispatch_status is not DispatchStatus.NOT_SENT)

    @property
    def post_stop_capture_count(self) -> int:
        return int(bool(self.post_stop_observation_id))

    @property
    def native_evaluator_count(self) -> int:
        return int(self.native_evaluator_invoked)


def admit_final_response(
    world: WorldObservation,
    response: FinalResponse,
) -> FinalResponseAdmission:
    """Validate optional current lineage; representation belongs to the environment codec."""

    current_refs = {
        item.evidence_ref
        for item in (*WorldEvidenceIndex.from_observation(world).records, *public_text_evidence_records(world))
    }
    if any(ref not in current_refs for ref in response.evidence_refs):
        return FinalResponseAdmission(False, "final_response_evidence_not_current")
    return FinalResponseAdmission(True)

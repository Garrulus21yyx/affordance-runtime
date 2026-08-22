"""Direct final-response representation and lifecycle boundary."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass

from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent.context.task_projection import PUBLIC_FINAL_RESPONSE_CONTRACT_KEY
from affordance_runtime.agent.decisions import FinalResponse
from affordance_runtime.agent.working_facts import WorkingFact
from affordance_runtime.evaluation.contracts import TaskEvaluationStatus
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex, public_text_evidence_records
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.task.contracts import TaskGoal
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
    task: TaskGoal,
    world: WorldObservation,
    working_facts: tuple[WorkingFact, ...],
    response: FinalResponse,
) -> FinalResponseAdmission:
    """Validate only representation and optional current lineage, never semantics."""

    current_refs = {
        item.evidence_ref
        for item in (*WorldEvidenceIndex.from_observation(world).records, *public_text_evidence_records(world))
    }
    retained_refs = {item.record.evidence_ref for item in working_facts}
    if any(ref not in current_refs | retained_refs for ref in response.evidence_refs):
        return FinalResponseAdmission(False, "final_response_evidence_not_current")
    schema = _public_schema(task)
    try:
        value = json.loads(response.content, parse_constant=_reject_non_json_constant)
        _validate_finite(value)
    except (json.JSONDecodeError, ValueError):
        value = response.content
    try:
        validate_value(to_json_compatible(value), schema, path="final_response")
    except (TypeError, ValueError):
        return FinalResponseAdmission(False, "final_response_invalid")
    return FinalResponseAdmission(True)


def _public_schema(task: TaskGoal) -> Mapping[str, object]:
    contract = task.inputs.get(PUBLIC_FINAL_RESPONSE_CONTRACT_KEY)
    if isinstance(contract, Mapping):
        schema = contract.get("json_schema")
        if isinstance(schema, Mapping):
            return schema
    return {"type": "string", "minLength": 1, "maxLength": 8_000}


def _reject_non_json_constant(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant is unsupported: {value}")


def _validate_finite(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite JSON number")
    if isinstance(value, Mapping):
        for item in value.values():
            _validate_finite(item)
    elif isinstance(value, list):
        for item in value:
            _validate_finite(item)

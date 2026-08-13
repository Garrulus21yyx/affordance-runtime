"""Independent semantic admission for model-proposed typed objectives."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_port import (
    ModelConfig,
    ModelMessage,
    ModelPort,
    ProviderModelError,
    StructuredModelError,
)
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation


class TaskSemanticValidationStatus(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TaskSemanticValidation:
    status: TaskSemanticValidationStatus
    reason_code: str
    validator_id: str

    def __post_init__(self) -> None:
        if not self.reason_code.strip() or not self.validator_id.strip():
            raise ValueError("task semantic validation requires typed evidence identity")


class TaskSemanticValidatorPort(Protocol):
    async def validate(
        self,
        task: TaskGoal,
        objective: dict[str, object],
        observation: WorldObservation,
    ) -> TaskSemanticValidation:
        """Judge task/objective consistency without granting action authority."""


class _ValidationPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    status: TaskSemanticValidationStatus
    reason_code: str


@dataclass(frozen=True)
class ModelTaskSemanticValidator:
    port: ModelPort
    config: ModelConfig

    async def validate(
        self,
        task: TaskGoal,
        objective: dict[str, object],
        observation: WorldObservation,
    ) -> TaskSemanticValidation:
        public_targets = tuple(
            {
                "role": item.role,
                "label": item.label,
                "state": to_json_compatible(item.state),
            }
            for item in observation.targets[:64]
        )
        request = {
            "task_instruction": task.instruction,
            "proposed_objective": to_json_compatible(objective),
            "current_public_entities": public_targets,
            "contract": {
                "supported": "faithful next objective with correct action, quantifier, scope, and conditions",
                "contradicted": "objective changes, omits, or expands explicit task semantics",
                "unknown": "current public evidence is insufficient to decide",
            },
        }
        messages = (
            ModelMessage(
                role="system",
                content=(
                    "You independently validate a typed GUI objective against the user's task and "
                    "current public state. Do not solve the GUI, choose targets, invent facts, or "
                    "grant execution. Check action, ordering, quantifier, scope, predicate conditions, "
                    "and aggregate operator. Return supported only when the proposed next objective is "
                    "faithful; contradicted for a definite mismatch; otherwise unknown. reason_code "
                    "must be short snake_case and contain no private identifiers."
                ),
            ),
            ModelMessage(
                role="user",
                content=json.dumps(
                    request,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ),
            ),
        )
        try:
            result = await self.port.generate_structured(messages, _ValidationPayload, self.config)
        except (ProviderModelError, StructuredModelError, TimeoutError):
            return TaskSemanticValidation(
                TaskSemanticValidationStatus.UNKNOWN,
                "semantic_validator_unavailable",
                f"{self.port.provider}:{self.port.model}",
            )
        reason = result.reason_code.strip().casefold()
        if not reason or len(reason) > 64 or not reason.replace("_", "").isalnum():
            return TaskSemanticValidation(
                TaskSemanticValidationStatus.UNKNOWN,
                "semantic_validator_invalid_reason",
                f"{self.port.provider}:{self.port.model}",
            )
        return TaskSemanticValidation(
            result.status,
            reason,
            f"{self.port.provider}:{self.port.model}",
        )

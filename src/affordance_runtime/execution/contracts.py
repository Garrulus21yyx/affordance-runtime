"""Small action-intent, bound request, and transport-result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from affordance_runtime.immutable import freeze_json
from affordance_runtime.schema_digest import schema_digest

if TYPE_CHECKING:
    from affordance_runtime.world.contracts import ActionBinding, AdmittedActionSelection


class DispatchStatus(StrEnum):
    NOT_SENT = "not_sent"
    SENT = "sent"
    SENT_UNKNOWN = "sent_unknown"


class ActionError(StrEnum):
    STALE_BINDING = "stale_binding"
    CURRENTNESS_UNAVAILABLE = "currentness_unavailable"
    RATE_LIMITED = "rate_limited"
    INVALID_PARAMETERS = "invalid_parameters"
    EXECUTION_FAILED = "execution_failed"
    UNSUPPORTED_ACTION = "unsupported_action"


@dataclass(frozen=True)
class ActionIntent:
    semantic_action: str
    target_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    destination_id: str = ""
    expected_outcome: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.semantic_action.strip() or not self.target_id.strip():
            raise ValueError("action intent requires semantic action and target")
        object.__setattr__(self, "parameters", freeze_json(self.parameters))
        object.__setattr__(self, "expected_outcome", freeze_json(self.expected_outcome))


@dataclass(frozen=True)
class BoundActionRequest:
    request_id: str
    context_id: str
    world_observation_id: str
    intent: ActionIntent
    selection: AdmittedActionSelection
    binding: ActionBinding
    timeout_ms: int = 5_000

    def __post_init__(self) -> None:
        if (
            not self.request_id.strip()
            or not self.context_id.strip()
            or self.world_observation_id != self.binding.world_observation_id
        ):
            raise ValueError("bound request must identify its binding observation")
        if (
            self.selection.observation_id != self.world_observation_id
            or self.selection.action_id.strip() == ""
            or self.intent.semantic_action != self.selection.semantic_action
            or self.intent.target_id != self.selection.target_id
            or self.intent.parameters != self.selection.parameters
            or self.intent.destination_id != self.selection.destination_id
            or self.binding.binding_id not in self.selection.eligible_binding_ids
            or self.selection.semantic_action != self.binding.semantic_action
            or self.selection.target_id != self.binding.target_id
            or self.selection.effect_category != self.binding.effect_category
            or self.selection.semantic_effects != self.binding.semantic_effects
            or self.selection.schema_digest != schema_digest(self.binding.parameter_schema)
            or _risk_rank(self.binding.risk) > _risk_rank(self.selection.risk)
            or self.binding.observation_barrier != self.selection.observation_barrier
            or self.binding.destination_required != self.selection.destination_required
            or self.binding.eligible_destination_ids != self.selection.eligible_destination_ids
            or self.binding.verification_contract_digest != self.selection.verification_contract_digest
            or (
                self.selection.destination_id
                and self.selection.destination_id not in self.selection.eligible_destination_ids
            )
            or (self.selection.destination_required and not self.selection.destination_id)
        ):
            raise ValueError("bound request must retain its admitted option and binding group")
        if self.timeout_ms <= 0:
            raise ValueError("timeout must be positive")

    @property
    def observation_id(self) -> str:
        """Compatibility read; world identity is canonical."""

        return self.world_observation_id


def _risk_rank(risk: object) -> int:
    return ("low", "medium", "high", "irreversible").index(str(risk))


@dataclass(frozen=True)
class ActionResult:
    request_id: str
    dispatch_status: DispatchStatus
    backend: str
    transport_success: bool
    error: ActionError | None = None
    adapter_evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.dispatch_status, DispatchStatus):
            raise TypeError("action result dispatch status must be typed")
        if self.error is not None and not isinstance(self.error, ActionError):
            raise TypeError("action result error must be typed")
        if type(self.transport_success) is not bool:
            raise TypeError("action result transport success must be boolean")
        if not self.request_id.strip() or not self.backend.strip():
            raise ValueError("action result requires request and backend identity")
        inconsistent = (
            (self.dispatch_status in {DispatchStatus.NOT_SENT, DispatchStatus.SENT_UNKNOWN} and self.transport_success)
            or (self.transport_success and self.error is not None)
            or (not self.transport_success and self.error is None)
        )
        if inconsistent:
            raise ValueError("action result dispatch status, transport success, and error are inconsistent")
        object.__setattr__(self, "adapter_evidence", freeze_json(self.adapter_evidence))

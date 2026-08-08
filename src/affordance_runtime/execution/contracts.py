"""Small action-intent, bound request, and transport-result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from affordance_runtime.immutable import freeze_json

if TYPE_CHECKING:
    from affordance_runtime.world.contracts import ActionBinding, AdmittedActionSelection


class DispatchStatus(StrEnum):
    NOT_SENT = "not_sent"
    SENT = "sent"
    SENT_UNKNOWN = "sent_unknown"


class ActionError(StrEnum):
    STALE_BINDING = "stale_binding"
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
    world_observation_id: str
    intent: ActionIntent
    selection: AdmittedActionSelection
    binding: ActionBinding
    timeout_ms: int = 5_000

    def __post_init__(self) -> None:
        if not self.request_id.strip() or self.world_observation_id != self.binding.world_observation_id:
            raise ValueError("bound request must identify its binding observation")
        if self.intent.target_id != self.binding.target_id:
            raise ValueError("intent target does not match binding target")
        if (
            self.selection.observation_id != self.world_observation_id
            or self.selection.action_id.strip() == ""
            or self.binding.binding_id not in self.selection.eligible_binding_ids
            or self.selection.semantic_action != self.binding.semantic_action
            or self.selection.target_id != self.binding.target_id
            or self.selection.effect_category != self.binding.effect_category
            or self.selection.semantic_effects != self.binding.semantic_effects
        ):
            raise ValueError("bound request must retain its admitted option and binding group")
        if self.timeout_ms <= 0:
            raise ValueError("timeout must be positive")

    @property
    def observation_id(self) -> str:
        """Compatibility read; world identity is canonical."""

        return self.world_observation_id


@dataclass(frozen=True)
class ActionResult:
    request_id: str
    dispatch_status: DispatchStatus
    backend: str
    transport_success: bool
    error: ActionError | None = None
    adapter_evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.backend.strip():
            raise ValueError("action result requires request and backend identity")
        object.__setattr__(self, "adapter_evidence", freeze_json(self.adapter_evidence))

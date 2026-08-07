"""Immutable unified-world and runtime-owned action-space contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from affordance_runtime.immutable import freeze_json


class CoverageState(StrEnum):
    COMPLETE = "complete"
    NOT_ACQUIRED = "not_acquired"
    FAILED = "failed"
    TRUNCATED = "truncated"
    STALE = "stale"


class ActionRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IRREVERSIBLE = "irreversible"


@dataclass(frozen=True)
class SemanticTarget:
    target_id: str
    role: str
    label: str
    state: dict[str, Any] = field(default_factory=dict)
    relations: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.target_id.strip() or not self.role.strip():
            raise ValueError("semantic target requires identity and role")
        object.__setattr__(self, "state", freeze_json(self.state))
        object.__setattr__(self, "relations", freeze_json(self.relations))


@dataclass(frozen=True)
class StateFact:
    fact_id: str
    subject_id: str
    predicate: str
    value: Any
    source_id: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.fact_id, self.subject_id, self.predicate, self.source_id)):
            raise ValueError("state fact identity fields cannot be blank")
        object.__setattr__(self, "value", freeze_json(self.value))


@dataclass(frozen=True)
class ObservationConflict:
    conflict_id: str
    subject_id: str
    predicate: str
    summary: str


@dataclass(frozen=True)
class ActionBinding:
    binding_id: str
    observation_id: str
    target_id: str
    surface: str
    executor_id: str
    supported_actions: tuple[str, ...]
    payload: dict[str, Any]
    expires_at_s: float = 0.0
    confidence: float = 1.0
    cost: float = 0.0
    risk: ActionRisk = ActionRisk.LOW

    def __post_init__(self) -> None:
        required = (self.binding_id, self.observation_id, self.target_id, self.surface, self.executor_id)
        if not all(value.strip() for value in required) or not self.supported_actions:
            raise ValueError("action binding requires identity, route, and supported actions")
        object.__setattr__(self, "supported_actions", tuple(self.supported_actions))
        object.__setattr__(self, "payload", freeze_json(self.payload))


@dataclass(frozen=True)
class SurfaceObservation:
    observation_id: str
    surface: str
    revision: str
    targets: tuple[SemanticTarget, ...] = ()
    facts: tuple[StateFact, ...] = ()
    bindings: tuple[ActionBinding, ...] = ()
    coverage: CoverageState = CoverageState.COMPLETE
    artifacts: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.observation_id.strip() or not self.surface.strip() or not self.revision.strip():
            raise ValueError("surface observation requires identity, surface, and revision")
        if any(binding.observation_id != self.observation_id for binding in self.bindings):
            raise ValueError("surface binding must belong to its observation")
        object.__setattr__(self, "targets", tuple(self.targets))
        object.__setattr__(self, "facts", tuple(self.facts))
        object.__setattr__(self, "bindings", tuple(self.bindings))
        object.__setattr__(self, "artifacts", freeze_json(self.artifacts))


@dataclass(frozen=True)
class WorldObservation:
    observation_id: str
    targets: tuple[SemanticTarget, ...]
    facts: tuple[StateFact, ...]
    bindings: tuple[ActionBinding, ...]
    coverage: dict[str, CoverageState]
    conflicts: tuple[ObservationConflict, ...] = ()
    sources: tuple[SurfaceObservation, ...] = ()

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("world observation requires non-empty identity")
        if any(binding.observation_id != self.observation_id for binding in self.bindings):
            raise ValueError("world binding must reference the current observation")
        object.__setattr__(self, "targets", tuple(self.targets))
        object.__setattr__(self, "facts", tuple(self.facts))
        object.__setattr__(self, "bindings", tuple(self.bindings))
        object.__setattr__(self, "coverage", freeze_json(self.coverage))
        object.__setattr__(self, "conflicts", tuple(self.conflicts))
        object.__setattr__(self, "sources", tuple(self.sources))


@dataclass(frozen=True)
class ActionOption:
    action_id: str
    observation_id: str
    semantic_action: str
    target_id: str
    parameter_schema: dict[str, Any]
    description: str
    risk: ActionRisk = ActionRisk.LOW
    destination_required: bool = False
    batchable: bool = False
    observation_barrier: bool = True

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.action_id, self.observation_id, self.semantic_action, self.target_id)):
            raise ValueError("action option requires current semantic identity")
        object.__setattr__(self, "parameter_schema", freeze_json(self.parameter_schema))


@dataclass(frozen=True)
class ActionSpace:
    observation_id: str
    options: tuple[ActionOption, ...]

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("action space requires observation identity")
        if any(option.observation_id != self.observation_id for option in self.options):
            raise ValueError("action-space option belongs to another observation")
        if len({option.action_id for option in self.options}) != len(self.options):
            raise ValueError("action ids must be unique within an action space")
        object.__setattr__(self, "options", tuple(self.options))

    def find(self, action_id: str) -> ActionOption | None:
        return next((option for option in self.options if option.action_id == action_id), None)

"""Unified immutable observation view for active-step planning.

SAR-5 foundation only. This module projects existing immutable planner
observation views into a target-centric observation contract. It does not read
BrowserSnapshot, adapters, StateKernel, Coordinator, or trace.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from affordance_runtime.immutable import FrozenDict, freeze_json
from affordance_runtime.planning_request import (
    PlannerObservationView,
    thaw_request_value,
)


@dataclass(frozen=True)
class UnifiedObservationTarget:
    target_id: str
    surface: str
    role: str
    label: str
    supported_actions: tuple[str, ...]
    state: FrozenDict
    confidence: float | None = None
    conflict_codes: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        target_id: str,
        surface: str,
        role: str,
        label: str,
        supported_actions: tuple[str, ...],
        state: Mapping[str, Any],
        confidence: float | None = None,
        conflict_codes: tuple[str, ...] = (),
        source_refs: tuple[str, ...] = (),
    ) -> None:
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(self, "surface", surface)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "supported_actions", tuple(supported_actions))
        object.__setattr__(self, "state", freeze_json(dict(state)))
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "conflict_codes", tuple(conflict_codes))
        object.__setattr__(self, "source_refs", tuple(source_refs))
        self.__post_init__()

    def __post_init__(self) -> None:
        _require_nonblank("target_id", self.target_id)
        _require_nonblank("surface", self.surface)
        _require_nonblank("role", self.role)
        _require_tuple("supported_actions", self.supported_actions)
        _require_unique_nonblank("supported actions", self.supported_actions)
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        _require_tuple("conflict_codes", self.conflict_codes)
        _require_no_blank_values("conflict_codes", self.conflict_codes)
        _require_tuple("source_refs", self.source_refs)
        _require_no_blank_values("source_refs", self.source_refs)


@dataclass(frozen=True)
class UnifiedObservation:
    snapshot_id: str
    page_revision: str
    environment_revision: str
    observed_text: str
    targets: tuple[UnifiedObservationTarget, ...]
    artifact_refs: tuple[str, ...] = ()

    @classmethod
    def from_planner_observation(
        cls,
        observation: PlannerObservationView,
    ) -> "UnifiedObservation":
        return cls(
            snapshot_id=observation.snapshot_id,
            page_revision=observation.page_revision,
            environment_revision=observation.environment_revision,
            observed_text=observation.observed_text,
            targets=tuple(
                UnifiedObservationTarget(
                    target_id=item.target_id,
                    surface=item.surface,
                    role=item.role,
                    label=item.label,
                    supported_actions=item.supported_actions,
                    state={key: thaw_request_value(value) for key, value in item.state},
                    confidence=item.confidence,
                    conflict_codes=item.conflict_codes,
                    source_refs=item.source_refs,
                )
                for item in observation.affordances
            ),
            artifact_refs=observation.artifact_refs,
        )

    def __post_init__(self) -> None:
        _require_nonblank("snapshot_id", self.snapshot_id)
        _require_nonblank("page_revision", self.page_revision)
        _require_nonblank("environment_revision", self.environment_revision)
        _require_tuple("targets", self.targets)
        target_ids = tuple(item.target_id for item in self.targets)
        _require_unique_nonblank("target ids", target_ids)
        _require_tuple("artifact_refs", self.artifact_refs)
        _require_no_blank_values("artifact_refs", self.artifact_refs)


def _require_nonblank(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} cannot be blank")


def _require_tuple(label: str, value: object) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be an immutable tuple")


def _require_no_blank_values(label: str, values: tuple[str, ...]) -> None:
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} cannot contain blank values")


def _require_unique_nonblank(label: str, values: tuple[str, ...]) -> None:
    _require_no_blank_values(label, values)
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")

"""Typed interaction grounding with no task-text or completion-criterion parsing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from affordance_runtime.immutable import FrozenDict
from affordance_runtime.simplified_runtime_contracts import (
    CollectionIntent,
    ElementIntent,
    InteractionIntent,
    RegionIntent,
    RelationIntent,
)


class GroundingStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    ABSENT = "absent"
    CAPABILITY_MISSING = "capability_missing"


@dataclass(frozen=True)
class GroundingTarget:
    target_id: str
    role: str
    label: str
    supported_actions: tuple[str, ...]
    state: Mapping[str, Any]


@dataclass(frozen=True)
class GroundingResult:
    status: GroundingStatus
    targets: tuple[GroundingTarget, ...] = ()
    destinations: tuple[GroundingTarget, ...] = ()
    parameters: FrozenDict = field(default_factory=lambda: FrozenDict({}))
    reason_code: str = ""


@dataclass(frozen=True)
class InteractionGrounder:
    def ground(
        self,
        interaction: InteractionIntent,
        targets: tuple[GroundingTarget, ...],
        *,
        capabilities: frozenset[str] = frozenset(),
    ) -> GroundingResult:
        if isinstance(interaction, RegionIntent):
            if interaction.capability not in capabilities:
                return GroundingResult(
                    GroundingStatus.CAPABILITY_MISSING,
                    reason_code="interaction_capability_missing",
                )
            return GroundingResult(
                GroundingStatus.ABSENT,
                reason_code="region_grounding_unavailable",
            )
        if isinstance(interaction, RelationIntent):
            source = _match_element(interaction.source, targets)
            destination = _match_element(interaction.destination, targets)
            status = _combined_status(source, destination)
            return GroundingResult(
                status,
                targets=source.targets,
                destinations=destination.targets,
                reason_code=("" if status == GroundingStatus.RESOLVED else "relation_target_unresolved"),
            )
        if isinstance(interaction, CollectionIntent):
            collection = _match_element(interaction.collection, targets)
            if collection.status != GroundingStatus.RESOLVED:
                return collection
            values = tuple(interaction.members.values)
            parameter: object = values[0] if len(values) == 1 else list(values)
            return GroundingResult(
                GroundingStatus.RESOLVED,
                targets=collection.targets,
                parameters=FrozenDict({"option": parameter}),
            )
        return _match_element(interaction, targets)


def _match_element(
    intent: ElementIntent,
    targets: tuple[GroundingTarget, ...],
) -> GroundingResult:
    identity = intent.target.strip().casefold()
    role = intent.role.strip().casefold()
    matches = tuple(
        item
        for item in targets
        if (not role or _role_matches(role, item.role))
        and (
            intent.match_by_role
            or
            item.target_id == intent.target
            or item.label.strip().casefold() == identity
        )
    )
    if intent.ordinal is not None:
        role_matches = tuple(
            item for item in targets if not role or _role_matches(role, item.role)
        )
        matches = (
            (role_matches[intent.ordinal - 1],)
            if len(role_matches) >= intent.ordinal
            else ()
        )
    if len(matches) == 1:
        return GroundingResult(GroundingStatus.RESOLVED, targets=matches)
    if len(matches) > 1:
        return GroundingResult(
            GroundingStatus.AMBIGUOUS,
            targets=matches,
            reason_code="interaction_target_ambiguous",
        )
    return GroundingResult(
        GroundingStatus.ABSENT,
        reason_code="interaction_target_absent",
    )


def _role_matches(requested: str, observed: str) -> bool:
    aliases = {
        "collection": {"combobox", "listbox", "select"},
        "textbox": {"textbox", "searchbox", "textarea"},
    }
    actual = observed.strip().casefold()
    return actual == requested or actual in aliases.get(requested, set())


def _combined_status(*results: GroundingResult) -> GroundingStatus:
    if any(item.status == GroundingStatus.CAPABILITY_MISSING for item in results):
        return GroundingStatus.CAPABILITY_MISSING
    if any(item.status == GroundingStatus.AMBIGUOUS for item in results):
        return GroundingStatus.AMBIGUOUS
    if any(item.status == GroundingStatus.ABSENT for item in results):
        return GroundingStatus.ABSENT
    return GroundingStatus.RESOLVED

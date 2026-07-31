"""Typed interaction grounding with no task-text or completion-criterion parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from affordance_runtime.immutable import FrozenDict
from affordance_runtime.simplified_runtime_contracts import (
    CollectionIntent,
    ElementIntent,
    ElementOperationKind,
    InteractionIntent,
    RegionIntent,
    RelationIntent,
)


class GroundingStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    ABSENT = "absent"
    CAPABILITY_MISSING = "capability_missing"


class GroundingRole(StrEnum):
    DIRECT = "direct"
    ENABLING = "enabling"


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
    role: GroundingRole = GroundingRole.DIRECT


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
            destination = (
                _match_element(interaction.destination, targets)
                if interaction.destination is not None
                else (
                    _match_relative_destination(source, interaction.destination_offset, targets)
                    if interaction.destination_offset is not None
                    else _match_absolute_destination(
                        source,
                        interaction.destination_ordinal,
                        targets,
                    )
                )
            )
            source, destination = _exclude_resolved_relation_endpoint(source, destination)
            status = _combined_status(source, destination)
            if (
                status == GroundingStatus.RESOLVED
                and source.targets[0].target_id == destination.targets[0].target_id
            ):
                return GroundingResult(
                    GroundingStatus.AMBIGUOUS,
                    targets=source.targets,
                    destinations=destination.targets,
                    reason_code="relation_endpoints_not_distinct",
                )
            if (
                status == GroundingStatus.RESOLVED
                and interaction.relation != "value_transfer"
                and "drag" not in source.targets[0].supported_actions
            ):
                return GroundingResult(
                    GroundingStatus.CAPABILITY_MISSING,
                    targets=source.targets,
                    destinations=destination.targets,
                    reason_code="relation_source_drag_capability_missing",
                )
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
        direct = _match_element(interaction, targets)
        if direct.status != GroundingStatus.ABSENT or interaction.enabler is None:
            return direct
        enabler = _match_element(interaction.enabler, targets)
        if enabler.status != GroundingStatus.RESOLVED:
            return GroundingResult(
                enabler.status,
                targets=enabler.targets,
                reason_code="interaction_enabler_unresolved",
            )
        enabling_target = enabler.targets[0]
        enabling_ready = _enabling_ready(interaction.enabler, enabling_target)
        if enabling_ready is False:
            return GroundingResult(
                GroundingStatus.ABSENT,
                reason_code="interaction_enabler_already_satisfied",
            )
        if enabling_ready is None:
            return GroundingResult(
                GroundingStatus.CAPABILITY_MISSING,
                reason_code="interaction_enabler_state_missing",
            )
        return GroundingResult(
            GroundingStatus.RESOLVED,
            targets=enabler.targets,
            role=GroundingRole.ENABLING,
        )


def _enabling_ready(
    intent: ElementIntent,
    target: GroundingTarget,
) -> bool | None:
    if intent.operation == ElementOperationKind.AUTO:
        expanded = target.state.get("expanded")
        return not expanded if isinstance(expanded, bool) else None
    scroll_top = target.state.get("scroll_top")
    scroll_height = target.state.get("scroll_height")
    client_height = target.state.get("client_height")
    if not isinstance(scroll_top, (int, float)):
        return None
    if not isinstance(scroll_height, (int, float)):
        return None
    if not isinstance(client_height, (int, float)):
        return None
    current = float(scroll_top)
    maximum = max(0.0, float(scroll_height) - float(client_height))
    if intent.operation == ElementOperationKind.SCROLL_FORWARD:
        return current < maximum
    return current > 0.0


def _match_element(
    intent: ElementIntent,
    targets: tuple[GroundingTarget, ...],
) -> GroundingResult:
    identity = intent.target.strip().casefold()
    role = intent.role.strip().casefold()
    scoped_targets = tuple(
        item
        for item in targets
        if not intent.collection_scope
        or _collection_scope_matches(intent.collection_scope, item)
    )
    if intent.relative_size:
        scoped_targets = tuple(
            item
            for item in scoped_targets
            if str(item.state.get("relative_size") or "").casefold()
            == intent.relative_size
        )
    if identity == "textarea":
        scoped_targets = tuple(
            item
            for item in scoped_targets
            if str(item.state.get("element_tag") or "").casefold() == "textarea"
        )
    if intent.collection_scope and not scoped_targets:
        return GroundingResult(
            GroundingStatus.ABSENT,
            reason_code="interaction_collection_scope_absent",
        )
    matches = tuple(
        item
        for item in scoped_targets
        if (
            (
                bool(intent.relative_size)
                and (
                    not role
                    or _role_matches(role, item.role)
                    or _role_capability_compatible(role, item)
                )
            )
            or (intent.match_by_role and (not role or _role_matches(role, item.role)))
            or (
                not intent.match_by_role
                and (
                    item.target_id == intent.target
                    or item.label.strip().casefold() == identity
                    or _semantic_label_matches(intent.target, item.label)
                )
                and (
                    not role
                    or _role_matches(role, item.role)
                    or _role_capability_compatible(role, item)
                )
            )
        )
    )
    role_matches = tuple(
        item for item in scoped_targets if not role or _role_matches(role, item.role)
    )
    if (
        intent.collection_cardinality is not None
        and len(role_matches) != intent.collection_cardinality
    ):
        return GroundingResult(
            GroundingStatus.AMBIGUOUS,
            targets=role_matches,
            reason_code="interaction_collection_cardinality_mismatch",
        )
    if intent.ordinal is not None:
        role_matches = _ordered_collection_members(role_matches)
        matches = (
            (role_matches[intent.ordinal - 1],)
            if len(role_matches) >= intent.ordinal
            else ()
        )
    role_matches = tuple(
        item for item in scoped_targets if role and _role_matches(role, item.role)
    )
    if not matches and role and intent.ordinal is None:
        if len(role_matches) == 1:
            matches = role_matches
        elif len(role_matches) > 1:
            return GroundingResult(
                GroundingStatus.AMBIGUOUS,
                targets=role_matches,
                reason_code="interaction_target_ambiguous",
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


def _exclude_resolved_relation_endpoint(
    source: GroundingResult,
    destination: GroundingResult,
) -> tuple[GroundingResult, GroundingResult]:
    if source.status == GroundingStatus.RESOLVED and destination.status == GroundingStatus.AMBIGUOUS:
        source_ids = {item.target_id for item in source.targets}
        remaining = tuple(item for item in destination.targets if item.target_id not in source_ids)
        if len(remaining) == 1:
            destination = GroundingResult(GroundingStatus.RESOLVED, targets=remaining)
    if destination.status == GroundingStatus.RESOLVED and source.status == GroundingStatus.AMBIGUOUS:
        destination_ids = {item.target_id for item in destination.targets}
        remaining = tuple(item for item in source.targets if item.target_id not in destination_ids)
        if len(remaining) == 1:
            source = GroundingResult(GroundingStatus.RESOLVED, targets=remaining)
    return source, destination


def _match_relative_destination(
    source: GroundingResult,
    offset: int | None,
    targets: tuple[GroundingTarget, ...],
) -> GroundingResult:
    if source.status != GroundingStatus.RESOLVED or offset in {None, 0}:
        return GroundingResult(
            source.status,
            reason_code="relation_source_unresolved",
        )
    source_target = source.targets[0]
    position = source_target.state.get("collection_position")
    if not isinstance(position, int) or position < 1:
        return GroundingResult(
            GroundingStatus.CAPABILITY_MISSING,
            reason_code="relation_collection_position_missing",
        )
    desired = position + offset
    return _match_collection_position(source_target, desired, targets)


def _match_absolute_destination(
    source: GroundingResult,
    ordinal: int | None,
    targets: tuple[GroundingTarget, ...],
) -> GroundingResult:
    if source.status != GroundingStatus.RESOLVED or ordinal is None or ordinal < 1:
        return GroundingResult(source.status, reason_code="relation_source_unresolved")
    return _match_collection_position(source.targets[0], ordinal, targets)


def _match_collection_position(
    source_target: GroundingTarget,
    desired: int,
    targets: tuple[GroundingTarget, ...],
) -> GroundingResult:
    source_context = _collection_context(source_target)
    matches = tuple(
        item
        for item in targets
        if item.target_id != source_target.target_id
        and item.state.get("collection_position") == desired
        and (
            source_context is None
            or _collection_context(item) == source_context
        )
    )
    if len(matches) == 1:
        return GroundingResult(GroundingStatus.RESOLVED, targets=matches)
    return GroundingResult(
        GroundingStatus.AMBIGUOUS if matches else GroundingStatus.ABSENT,
        targets=matches,
        reason_code=(
            "relation_destination_ambiguous"
            if matches
            else "relation_relative_destination_absent"
        ),
    )


def _collection_context(target: GroundingTarget) -> tuple[str, str] | None:
    for key in ("collection_owner", "container_context", "group_context"):
        value = target.state.get(key)
        if isinstance(value, str) and value.strip():
            return key, value.strip().casefold()
    return None


def _collection_scope_matches(scope: str, target: GroundingTarget) -> bool:
    expected = " ".join(scope.split()).casefold()
    return any(
        isinstance(value, str) and " ".join(value.split()).casefold() == expected
        for key in (
            "collection_owner",
            "container_context",
            "group_context",
            "pagination_owner",
        )
        if (value := target.state.get(key)) is not None
    )


def _ordered_collection_members(
    targets: tuple[GroundingTarget, ...],
) -> tuple[GroundingTarget, ...]:
    positioned: list[tuple[int, GroundingTarget]] = []
    for target in targets:
        position = target.state.get("collection_position")
        if not isinstance(position, int) or position < 1:
            return targets
        positioned.append((position, target))
    return tuple(target for _, target in sorted(positioned, key=lambda item: item[0]))


def _role_matches(requested: str, observed: str) -> bool:
    aliases = {
        "collection": {"combobox", "listbox", "select"},
        "textbox": {"textbox", "searchbox", "textarea"},
    }
    actual = observed.strip().casefold()
    return actual == requested or actual in aliases.get(requested, set())


def _role_capability_compatible(requested: str, target: GroundingTarget) -> bool:
    actual = target.role.strip().casefold()
    command_roles = {"button", "link", "menuitem", "tab"}
    if requested in command_roles and actual in command_roles:
        return "activate" in target.supported_actions
    if actual not in {"", "generic", "none"}:
        return False
    required_action = {
        "button": "activate",
        "checkbox": "activate",
        "combobox": "select_option",
        "link": "activate",
        "listbox": "select_option",
        "menuitem": "activate",
        "radio": "activate",
        "searchbox": "type_text",
        "slider": "press_key",
        "tab": "activate",
        "textbox": "type_text",
    }.get(requested)
    return required_action is not None and required_action in target.supported_actions


def _semantic_label_matches(requested: str, observed: str) -> bool:
    requested_tokens = set(re.findall(r"[a-z0-9]+", requested.casefold()))
    observed_tokens = set(re.findall(r"[a-z0-9]+", observed.casefold()))
    if not requested_tokens or not observed_tokens:
        return False
    return observed_tokens.issubset(requested_tokens) or requested_tokens.issubset(observed_tokens)


def _combined_status(*results: GroundingResult) -> GroundingStatus:
    if any(item.status == GroundingStatus.CAPABILITY_MISSING for item in results):
        return GroundingStatus.CAPABILITY_MISSING
    if any(item.status == GroundingStatus.AMBIGUOUS for item in results):
        return GroundingStatus.AMBIGUOUS
    if any(item.status == GroundingStatus.ABSENT for item in results):
        return GroundingStatus.ABSENT
    return GroundingStatus.RESOLVED

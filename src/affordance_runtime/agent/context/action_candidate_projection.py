"""Close current actions over complete bounded public candidate semantics."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    DestinationMode,
)
from affordance_runtime.actions.paging import ActionCandidateRanker
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.context import AgentGroundingEntityView, AgentGroundingIndexView
from affordance_runtime.agent.context.contracts import (
    AgentActionOptionView,
    AgentActionPageView,
    AgentDestinationView,
)
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.immutable import freeze_json, to_json_compatible


@dataclass(frozen=True)
class ActionCandidateDestination:
    """One current public destination required or offered by a candidate."""

    target_ref: str
    label: str
    role: str
    functional_path: tuple[str, ...]
    region_ref: str
    public_state: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            re.fullmatch(r"E[1-9][0-9]{0,3}", self.target_ref) is None
            or not self.role
            or re.fullmatch(r"R[1-9][0-9]{0,3}", self.region_ref) is None
        ):
            raise ValueError("action candidate destination requires current public identity")
        object.__setattr__(self, "functional_path", tuple(self.functional_path))
        object.__setattr__(self, "public_state", freeze_json(dict(self.public_state)))


@dataclass(frozen=True)
class ActionCandidate:
    """Disposable public ranking of one existing current ActionOption."""

    action_id: str
    target_ref: str
    operation: str
    label: str
    role: str
    functional_path: tuple[str, ...]
    region_ref: str
    public_state: Mapping[str, object] = field(default_factory=dict)
    rank: int = 1
    reasons: tuple[str, ...] = ()
    destination_required: bool = False
    destinations: tuple[ActionCandidateDestination, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.action_id
            or re.fullmatch(r"E[1-9][0-9]{0,3}", self.target_ref) is None
            or not self.operation
            or not self.role
            or re.fullmatch(r"R[1-9][0-9]{0,3}", self.region_ref) is None
            or self.rank < 1
        ):
            raise ValueError("action candidate requires current public identity")
        object.__setattr__(self, "functional_path", tuple(self.functional_path))
        object.__setattr__(self, "public_state", freeze_json(dict(self.public_state)))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "destinations", tuple(self.destinations))
        if self.destination_required and not self.destinations:
            raise ValueError("destination-required candidate must close current destinations")
        if len({item.target_ref for item in self.destinations}) != len(self.destinations):
            raise ValueError("candidate destination refs must be unique")


@dataclass(frozen=True)
class ActionCandidateProjection:
    action_space_id: str
    world_observation_id: str
    candidates: tuple[ActionCandidate, ...]
    scope: str = "automatic"
    projection_id: str = ""

    def __post_init__(self) -> None:
        candidates = tuple(self.candidates)
        if not self.action_space_id.strip() or not self.world_observation_id.strip():
            raise ValueError("candidate projection requires current authority identities")
        if self.scope not in {"automatic", "search"}:
            raise ValueError("candidate projection scope is invalid")
        if self.scope == "automatic" and len(candidates) > 5:
            raise ValueError("automatic action candidates are bounded to Top-5")
        if len({item.target_ref for item in candidates}) != len(candidates):
            raise ValueError("candidate projection prints each executable target once")
        payload = {
            "action_space_id": self.action_space_id,
            "world_observation_id": self.world_observation_id,
            "scope": self.scope,
            "candidates": to_json_compatible(candidates),
        }
        expected = "action-candidates:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        if self.projection_id and self.projection_id != expected:
            raise ValueError("candidate projection identity does not bind its ranking")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "projection_id", expected)


def project_action_candidates(
    actions: tuple[AgentActionOptionView, ...],
    *,
    action_space_id: str,
    world_observation_id: str,
    region_index: WorldDeliveryIndex,
    query: str = "",
    instruction: str = "",
    objectives: tuple[str, ...] = (),
    done_when: tuple[str, ...] = (),
    recent_outcomes: tuple[object, ...] = (),
    allowed_action_ids: frozenset[str] | None = None,
    top_k: int | None = 5,
) -> ActionCandidateProjection:
    """Project the shared ranker without changing World or action authority."""

    by_action = {item.action_id: item for item in actions}
    ranked = ActionCandidateRanker().rank(
        actions,
        labels={item.target_id: item.target_label for item in actions},
        roles={item.target_id: item.target_role for item in actions},
        states={item.target_id: item.target_state for item in actions},
        functional_paths={
            item.target_id: region_index.functional_path_for_target(item.target_id)
            for item in actions
        },
        query=query,
        instruction=instruction,
        objectives=objectives,
        done_when=done_when,
        recent_outcomes=recent_outcomes,
        require_match=bool(query),
    )
    candidates: list[ActionCandidate] = []
    emitted_refs: set[str] = set()
    for ranked_item in ranked:
        if allowed_action_ids is not None and ranked_item.action_id not in allowed_action_ids:
            continue
        option = by_action[ranked_item.action_id]
        region = region_index.region_for_action(option.action_id) or region_index.region_for_target(
            option.target_id
        )
        if region is None or option.target_ref in emitted_refs:
            continue
        destinations = tuple(
            _project_destination(item, region_index)
            for item in option.destinations.items
        )
        candidates.append(ActionCandidate(
            option.action_id,
            option.target_ref,
            option.operation,
            option.target_label,
            option.target_role,
            region_index.functional_path_for_target(option.target_id),
            region.public_ref,
            option.target_state,
            len(candidates) + 1,
            ranked_item.reasons,
            option.destination_required,
            destinations,
        ))
        emitted_refs.add(option.target_ref)
        if top_k is not None and len(candidates) == top_k:
            break
    return ActionCandidateProjection(
        action_space_id,
        world_observation_id,
        tuple(candidates),
        "search" if query else "automatic",
    )


def _project_destination(
    destination: AgentDestinationView,
    region_index: WorldDeliveryIndex,
) -> ActionCandidateDestination:
    region = region_index.region_for_target(destination.destination_id)
    if region is None:
        raise ValueError("current action destination is absent from the World delivery index")
    state = destination.semantics.get("state", {})
    return ActionCandidateDestination(
        destination.grounding_ref,
        destination.label,
        str(destination.semantics.get("role", "")),
        region_index.functional_path_for_target(destination.destination_id),
        region.public_ref,
        state if isinstance(state, Mapping) else {},
    )


def close_action_candidates(
    actions: AgentActionPageView,
    grounding: AgentGroundingIndexView,
    *,
    context_id: str,
) -> AgentActionPageView:
    """Close each public candidate once without choosing its final selector."""

    entities_by_ref = {item.ref: item for item in grounding.entities}
    refs_by_target = dict(grounding.target_refs)
    projected = []
    for option in actions.options:
        definition = INTERACTION_CAPABILITY_REGISTRY.require(option.semantic_action)
        entity = _grounded_entity(option.target_id, refs_by_target, entities_by_ref)
        state = _candidate_state(entity.state)
        destinations = tuple(
            _destination_candidate(
                item.destination_id,
                refs_by_target,
                entities_by_ref,
                context_id,
            )
            for item in option.destinations.items
        )
        projected.append(
            replace(
                option,
                operation=definition.semantic_action,
                target_ref=entity.ref,
                target_semantics=_target_semantics(entity, entities_by_ref, state),
                target_label=entity.label,
                target_role=entity.role,
                target_state=state,
                target_marked=entity.marked,
                subject_kind=_subject_kind(option.subject_kind, entity.role),
                destination_mode=_destination_mode(option).value,
                grounding_context_id=context_id,
                destinations=BoundedSection(
                    destinations,
                    option.destinations.total_count,
                    option.destinations.truncated,
                ),
            )
        )
    return replace(actions, options=tuple(projected))


def _subject_kind(default: str, role: str) -> str:
    if role == "viewport":
        return "viewport"
    if role == "focused_context":
        return "focused_context"
    return default


def _destination_mode(option) -> DestinationMode:
    if option.destination_required:
        return DestinationMode.REQUIRED
    if option.destinations.items:
        return DestinationMode.OPTIONAL
    return DestinationMode.FORBIDDEN


def _grounded_entity(
    target_id: str,
    refs_by_target: Mapping[str, str],
    entities_by_ref: Mapping[str, AgentGroundingEntityView],
) -> AgentGroundingEntityView:
    ref = refs_by_target.get(target_id)
    entity = entities_by_ref.get(ref or "")
    if entity is None:
        raise ValueError("current action candidate is absent from grounding projection")
    return entity


def _destination_candidate(
    destination_id: str,
    refs_by_target: Mapping[str, str],
    entities_by_ref: Mapping[str, AgentGroundingEntityView],
    context_id: str,
) -> AgentDestinationView:
    entity = _grounded_entity(destination_id, refs_by_target, entities_by_ref)
    state = _candidate_state(entity.state)
    return AgentDestinationView(
        destination_id,
        entity.label,
        entity.ref,
        _target_semantics(entity, entities_by_ref, state),
        entity.marked,
        context_id,
    )


def _candidate_state(state: Mapping[str, object]) -> dict[str, object]:
    """Expose semantic coordinates, never lattice-construction coordinates."""

    result = dict(state)
    coordinate = result.get("grid_coordinate")
    if isinstance(coordinate, Mapping):
        x = coordinate.get("x")
        y = coordinate.get("y")
        if isinstance(x, int | float) and not isinstance(x, bool) and isinstance(y, int | float) and not isinstance(y, bool):
            result["grid_coordinate"] = {"x": x, "y": y}
            result.pop("grid_membership", None)
            result.pop("grid_coordinate_confidence", None)
    return result


def _target_semantics(
    entity: AgentGroundingEntityView,
    entities_by_ref: Mapping[str, AgentGroundingEntityView],
    state: Mapping[str, object],
) -> dict[str, object]:
    semantics: dict[str, object] = {"role": entity.role}
    if entity.label.strip():
        semantics["label"] = entity.label.strip()
    choice_state = {
        key: value
        for key, value in state.items()
        if key not in {"semantic_scope_label", "semantic_scope_role"} and _is_public_facet_value(value)
    }
    if choice_state:
        semantics["state"] = choice_state
    parent_ref = next(
        (hint.removeprefix("parent:") for hint in entity.relation_hints if hint.startswith("parent:")),
        "",
    )
    parent = entities_by_ref.get(parent_ref)
    if parent is not None:
        within: dict[str, object] = {"role": parent.role}
        if parent.label.strip():
            within["label"] = parent.label.strip()
        semantics["within"] = within
    scope_label = state.get("semantic_scope_label")
    if "within" not in semantics and isinstance(scope_label, str) and scope_label.strip():
        scope_role = state.get("semantic_scope_role")
        semantics["within"] = {
            **(
                {"role": scope_role.strip()}
                if isinstance(scope_role, str) and scope_role.strip()
                else {}
            ),
            "label": scope_label.strip(),
        }
    relations = tuple(
        sorted(
            hint for hint in entity.relation_hints
            if not hint.startswith(("parent:", "children:")) and len(hint) <= 160
        )
    )
    if relations:
        semantics["relations"] = relations
    return semantics


def _is_public_facet_value(value: object) -> bool:
    return (
        value is None
        or isinstance(value, str) and len(value) <= 160
        or isinstance(value, int | float | bool)
        or isinstance(value, tuple | list)
        and len(value) <= 4
        and all(item is None or isinstance(item, str | int | float | bool) for item in value)
    )

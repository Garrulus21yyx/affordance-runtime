"""Close current actions over complete bounded public candidate semantics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    DestinationMode,
)
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.context import AgentGroundingEntityView, AgentGroundingIndexView
from affordance_runtime.agent.context.contracts import (
    AgentActionPageView,
    AgentDestinationView,
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
    coordinate = result.pop("grid_coordinate", None)
    if isinstance(coordinate, Mapping):
        x = coordinate.get("x")
        y = coordinate.get("y")
        if isinstance(x, int | float) and not isinstance(x, bool) and isinstance(y, int | float) and not isinstance(y, bool):
            result["semantic_grid_coordinate"] = (x, y)
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

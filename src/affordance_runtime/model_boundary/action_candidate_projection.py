"""Close current actions over compact, public semantic target choices."""

from __future__ import annotations

import itertools
import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import replace

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary.context import AgentGroundingIndexView
from affordance_runtime.model_boundary.contracts import AgentActionPageView


def public_action_operation(semantic_action: str) -> str:
    """Return the only model-facing operation name for one semantic action."""

    return {"activate": "click", "fill": "fill", "select": "select"}.get(
        semantic_action,
        semantic_action,
    )


def close_action_candidates(
    actions: AgentActionPageView,
    grounding: AgentGroundingIndexView,
) -> AgentActionPageView:
    """Bind options once, then expose only their smallest semantic discriminator."""

    entities_by_ref = {item.ref: item for item in grounding.entities}
    refs_by_target = dict(grounding.target_refs)
    projected = []
    for option in actions.options:
        ref = refs_by_target.get(option.target_id)
        entity = entities_by_ref.get(ref or "")
        if entity is None:
            raise ValueError("current action target is absent from grounding projection")
        state = _candidate_state(entity.state)
        semantics = _target_semantics(entity, entities_by_ref, state)
        projected.append(
            replace(
                option,
                operation=public_action_operation(option.semantic_action),
                target_ref=entity.ref,
                selection_key=entity.ref,
                selection_fields=("ref",),
                target_semantics=semantics,
                target_label=entity.label,
                target_role=entity.role,
                target_state=state,
                target_marked=entity.marked,
            )
        )
    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, option in enumerate(projected):
        grouped[(option.operation, _schema_key(option.parameter_schema))].append(index)
    for indices in grouped.values():
        fields = _minimal_discriminator(tuple(projected[index] for index in indices))
        keys = [_selection_key(projected[index], fields) for index in indices]
        counts = Counter(keys)
        for index, key in zip(indices, keys, strict=True):
            option = projected[index]
            if counts[key] > 1:
                key = f"{key}@{option.target_ref}" if key else option.target_ref
                effective_fields = (*fields, "ref")
            else:
                effective_fields = fields
            projected[index] = replace(
                option,
                selection_key=key,
                selection_fields=effective_fields,
            )
    options = tuple(projected)
    return replace(actions, options=options)


def _candidate_state(state) -> dict[str, object]:
    """Expose one semantic coordinate system, never screen or lattice-construction indices."""

    result = dict(state)
    coordinate = result.pop("grid_coordinate", None)
    if isinstance(coordinate, Mapping):
        x = coordinate.get("x")
        y = coordinate.get("y")
        if isinstance(x, int | float) and isinstance(y, int | float):
            result["semantic_grid_coordinate"] = (x, y)
            result.pop("grid_membership", None)
            result.pop("grid_coordinate_confidence", None)
    return result


def _target_semantics(entity, entities_by_ref, state: Mapping[str, object]) -> dict[str, object]:
    semantics: dict[str, object] = {"role": entity.role}
    if entity.label.strip():
        semantics["label"] = entity.label.strip()
    choice_state = {
        key: value
        for key, value in state.items()
        if key not in {"semantic_scope_label", "semantic_scope_role"} and _is_choice_value(value)
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
        if within:
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
    return semantics


def _schema_key(schema: Mapping[str, object]) -> str:
    return json.dumps(
        to_json_compatible(schema),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _minimal_discriminator(options) -> tuple[str, ...]:
    if len(options) == 1:
        fields = _ordered_paths(options[0].target_semantics)
        return (fields[0],) if fields else ("ref",)
    paths = tuple(dict.fromkeys(
        path for option in options for path in _ordered_paths(option.target_semantics)
    ))
    varying = tuple(
        path for path in paths
        if len({_value_token(_path_value(option.target_semantics, path)) for option in options}) > 1
    )
    for size in range(1, min(3, len(varying)) + 1):
        for fields in itertools.combinations(varying, size):
            identities = {
                tuple(_value_token(_path_value(option.target_semantics, field)) for field in fields)
                for option in options
            }
            if len(identities) == len(options):
                return tuple(fields)
    return varying or ("ref",)


def _ordered_paths(selector: Mapping[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    state = selector.get("state")
    if isinstance(state, Mapping) and "semantic_grid_coordinate" in state:
        values.append("state.semantic_grid_coordinate")
    for path in ("label", "within.label", "role", "within.role"):
        if _path_value(selector, path) is not None:
            values.append(path)
    if isinstance(state, Mapping):
        values.extend(
            f"state.{key}" for key in sorted(state)
            if key != "semantic_grid_coordinate" and _is_choice_value(state[key])
        )
    return tuple(values)


def _path_value(selector: Mapping[str, object], path: str) -> object:
    value: object = selector
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _is_choice_value(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) <= 160
        or isinstance(value, int | float | bool)
    ) or (
        isinstance(value, tuple | list)
        and len(value) <= 4
        and all(isinstance(item, str | int | float | bool) for item in value)
    )


def _selection_key(option, fields: tuple[str, ...]) -> str:
    if fields == ("ref",):
        return option.target_ref
    rendered = tuple(_render_value(_path_value(option.target_semantics, field)) for field in fields)
    if len(rendered) == 1:
        return rendered[0]
    return " | ".join(f"{field}={value}" for field, value in zip(fields, rendered, strict=True))


def _value_token(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _render_value(value: object) -> str:
    if isinstance(value, tuple | list):
        return "(" + ",".join(_render_value(item) for item in value) + ")"
    if isinstance(value, float | int) and not isinstance(value, bool):
        return _number_token(value)
    if isinstance(value, str):
        return value
    return _value_token(value)


def _number_token(value: int | float) -> str:
    if isinstance(value, int) or value.is_integer():
        return str(int(value))
    token = format(value, ".15g")
    return "0" if token == "-0" else token

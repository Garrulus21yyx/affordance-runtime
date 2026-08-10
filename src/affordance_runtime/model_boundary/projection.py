"""Project Runtime-owned values into bounded, secret-safe model views."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from affordance_runtime.model_boundary.budgets import BoundedSection
from affordance_runtime.model_boundary.contracts import (
    AgentActionOptionView,
    AgentActionSpaceView,
    AgentDestinationView,
    AgentMilestoneView,
    AgentPlanView,
)
from affordance_runtime.task.planning_contracts import TaskPlan
from affordance_runtime.world.action_paging import InternalActionPage
from affordance_runtime.world.contracts import ActionSpace
from affordance_runtime.world.relevance import ActionRelevance
from affordance_runtime.world.view import AgentWorldView

if TYPE_CHECKING:
    from affordance_runtime.agent.control_transition import Turn
    from affordance_runtime.model_boundary.contracts import AgentTaskView, AgentTurnView
    from affordance_runtime.task.contracts import TaskGoal

_SECRET_MARKERS = ("password", "secret", "token", "credential", "authorization", "api_key", "apikey")
_PRIVATE_PATH_MARKERS = ("path", "local_file", "file_name")
_PRIVATE_ROUTE_MARKERS = (
    "backend",
    "bbox",
    "coordinate",
    "executor",
    "href",
    "method",
    "point",
    "screenshot_digest",
    "selector",
    "surface",
    "td_digest",
    "viewport",
)
_MAX_ITEMS = 12
_MAX_DEPTH = 3
_MAX_STRING = 240
_SCHEMA_TYPES = frozenset({"object", "string", "number", "integer", "boolean"})
_SCHEMA_KEYS = frozenset(
    {"type", "properties", "required", "additionalProperties", "enum", "minimum", "maximum", "description"}
)


def project_task(task: TaskGoal) -> AgentTaskView:
    """Compatibility import edge; canonical owner is task_projection."""

    from affordance_runtime.model_boundary.task_projection import project_task as project

    return project(task)


def project_action_space(
    action_space: ActionSpace,
    world: AgentWorldView,
    relevance: Mapping[str, ActionRelevance] | None = None,
) -> AgentActionSpaceView:
    return AgentActionSpaceView(
        _project_action_options(
            action_space,
            tuple(option.action_id for option in action_space.options),
            world,
            relevance or {},
            max_destinations_per_option=max(
                (len(option.eligible_destination_ids) for option in action_space.options),
                default=1,
            ),
        )
    )


def project_action_page(
    action_space: ActionSpace,
    page: InternalActionPage,
    world: AgentWorldView,
    max_destinations_per_option: int,
) -> AgentActionSpaceView:
    if page.action_space_id != action_space.action_space_id:
        raise ValueError("action page does not belong to the projected ActionSpace")
    return AgentActionSpaceView(
        _project_action_options(
            action_space,
            page.visible_action_ids,
            world,
            dict(page.relevance),
            max_destinations_per_option,
            dict(page.visible_destinations),
        )
    )


def _project_action_options(
    action_space: ActionSpace,
    visible_action_ids: tuple[str, ...],
    world: AgentWorldView,
    relevance: Mapping[str, ActionRelevance],
    max_destinations_per_option: int,
    visible_destinations: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[AgentActionOptionView, ...]:
    labels = {target.target_id: target.label for target in world.targets}
    by_id = {option.action_id: option for option in action_space.options}
    return tuple(
            AgentActionOptionView(
                option.action_id,
                option.semantic_action,
                option.target_id,
                labels.get(option.target_id, option.target_id),
                option.destination_required,
                BoundedSection(
                    tuple(
                        AgentDestinationView(item, labels.get(item, item))
                        for item in (
                            visible_destinations.get(option.action_id, ())
                            if visible_destinations is not None
                            else option.eligible_destination_ids[:max_destinations_per_option]
                        )
                    ),
                    len(option.eligible_destination_ids),
                    len(option.eligible_destination_ids) > max_destinations_per_option,
                ),
                project_parameter_schema_for_model(option.parameter_schema),
                option.description,
                option.semantic_effects,
                option.risk,
                option.observation_barrier,
                option.effect_category,
                option.effect_category,
                option.risk != "irreversible",
                relevance[option.action_id].role if option.action_id in relevance else "other",
                relevance[option.action_id].score if option.action_id in relevance else 0.0,
                relevance[option.action_id].reason_codes if option.action_id in relevance else (),
            )
            for action_id in visible_action_ids
            if (option := by_id.get(action_id)) is not None
        )


def project_turns(turns: tuple[Turn, ...]) -> tuple[AgentTurnView, ...]:
    from affordance_runtime.model_boundary.control_transition_projection import (
        project_turns as project,
    )

    return project(turns)


def project_plan(plan: TaskPlan | None) -> AgentPlanView | None:
    if plan is None:
        return None
    return AgentPlanView(
        tuple(
            AgentMilestoneView(
                item.milestone_id,
                item.description or item.milestone_id,
                completion_criteria=project_public_value(item.desired_state),
            )
            for item in plan.milestones
        )
    )


def project_public_value(value: Any, depth: int = 0) -> Any:
    if isinstance(value, str):
        return value[:_MAX_STRING] + ("…" if len(value) > _MAX_STRING else "")
    if value is None or isinstance(value, bool | int | float):
        return value
    if depth >= _MAX_DEPTH:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        result = {}
        for key, item in list(value.items())[:_MAX_ITEMS]:
            name = str(key)
            if _route_key(name):
                continue
            result[name] = "[REDACTED]" if _private_key(name) else project_public_value(item, depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [project_public_value(item, depth + 1) for item in list(value)[:_MAX_ITEMS]]
    return str(value)[:_MAX_STRING]


def project_parameter_schema_for_model(schema: Mapping[str, object]) -> dict[str, object]:
    """Project the supported finite JSON-schema subset without broken references."""

    try:
        return _project_schema_node(schema, root=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"parameter schema is unsupported or malformed: {exc}") from exc


def _project_schema_node(schema: Mapping[str, object], *, root: bool = False) -> dict[str, object]:
    if not isinstance(schema, Mapping) or set(schema) - _SCHEMA_KEYS:
        raise ValueError("unsupported keys")
    schema_type = schema.get("type")
    if schema_type not in _SCHEMA_TYPES or (root and schema_type != "object"):
        raise ValueError("unsupported type")
    result: dict[str, object] = {"type": schema_type}
    description = schema.get("description")
    if description is not None:
        if not isinstance(description, str):
            raise TypeError("description must be a string")
        result["description"] = _bounded_string(description, _MAX_STRING)
    if schema_type == "object":
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            raise TypeError("properties must be an object")
        projected_properties = {
            str(name): _project_schema_node(value)
            for name, value in list(properties.items())[:_MAX_ITEMS]
            if isinstance(name, str) and not _model_private_key(name)
        }
        if len(projected_properties) != sum(
            1
            for name, value in list(properties.items())[:_MAX_ITEMS]
            if isinstance(name, str) and not _model_private_key(name) and isinstance(value, Mapping)
        ):
            raise TypeError("property schemas must be objects")
        result["properties"] = projected_properties
        required = schema.get("required", ())
        if not isinstance(required, Sequence) or isinstance(required, str | bytes):
            raise TypeError("required must be a string array")
        if any(not isinstance(item, str) for item in required):
            raise TypeError("required must be a string array")
        result["required"] = [item for item in required if item in projected_properties]
        additional = schema.get("additionalProperties", False)
        if not isinstance(additional, bool):
            raise TypeError("additionalProperties must be boolean")
        result["additionalProperties"] = additional
    else:
        if any(key in schema for key in ("properties", "required", "additionalProperties")):
            raise ValueError("primitive schema contains object fields")
        enum = schema.get("enum")
        if enum is not None:
            if not isinstance(enum, Sequence) or isinstance(enum, str | bytes) or len(enum) > _MAX_ITEMS:
                raise TypeError("enum must be a bounded array")
            if any(not isinstance(item, str | bool | int | float) for item in enum):
                raise TypeError("enum values must be scalar")
            result["enum"] = list(enum)
        for key in ("minimum", "maximum"):
            if key in schema:
                value = schema[key]
                if not isinstance(value, int | float) or isinstance(value, bool):
                    raise TypeError(f"{key} must be numeric")
                result[key] = value
    return result


def _model_private_key(key: str) -> bool:
    return _private_key(key) or _route_key(key)


def _bounded_string(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _private_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(marker in normalized for marker in (*_SECRET_MARKERS, *_PRIVATE_PATH_MARKERS))


def _route_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(marker in normalized for marker in _PRIVATE_ROUTE_MARKERS)

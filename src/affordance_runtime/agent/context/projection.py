"""Project Runtime-owned values into bounded, secret-safe model views."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from affordance_runtime.actions.capabilities import INTERACTION_CAPABILITY_REGISTRY
from affordance_runtime.actions.effect_semantics import Reversibility
from affordance_runtime.actions.paging import InternalActionPage
from affordance_runtime.actions.relevance import ActionRelevance
from affordance_runtime.actions.schema_validation import validate_parameter_schema_contract
from affordance_runtime.actions.space_contracts import ActionSpace
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.contracts import (
    AgentActionOptionView,
    AgentActionSpaceView,
    AgentDestinationView,
)
from affordance_runtime.immutable import to_json_compatible

if TYPE_CHECKING:
    from affordance_runtime.agent.context.contracts import AgentTaskView
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


def project_task(task: TaskGoal) -> AgentTaskView:
    """Compatibility import edge; canonical owner is task_projection."""

    from affordance_runtime.agent.context.task_projection import project_task as project

    return project(task)


def project_action_space(
    action_space: ActionSpace,
    target_labels: Mapping[str, str],
    relevance: Mapping[str, ActionRelevance] | None = None,
) -> AgentActionSpaceView:
    return AgentActionSpaceView(
        _project_action_options(
            action_space,
            tuple(option.action_id for option in action_space.options),
            target_labels,
            relevance or {},
        )
    )


def project_action_page(
    action_space: ActionSpace,
    page: InternalActionPage,
    target_labels: Mapping[str, str],
) -> AgentActionSpaceView:
    if page.action_space_id != action_space.action_space_id:
        raise ValueError("action page does not belong to the projected ActionSpace")
    return AgentActionSpaceView(
        _project_action_options(
            action_space,
            page.visible_action_ids,
            target_labels,
            dict(page.relevance),
            dict(page.visible_destinations),
        )
    )


def _project_action_options(
    action_space: ActionSpace,
    visible_action_ids: tuple[str, ...],
    target_labels: Mapping[str, str],
    relevance: Mapping[str, ActionRelevance],
    visible_destinations: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[AgentActionOptionView, ...]:
    labels = dict(target_labels)
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
                            else option.eligible_destination_ids
                        )
                    ),
                    len(option.eligible_destination_ids),
                    (
                        visible_destinations is not None
                        and len(visible_destinations.get(option.action_id, ()))
                        < len(option.eligible_destination_ids)
                    ),
                ),
                project_parameter_schema_for_model(option.parameter_schema),
                option.description,
                option.semantic_effects,
                option.risk,
                option.observation_barrier,
                option.effect_category,
                option.effect_category,
                option.reversibility is Reversibility.REVERSIBLE,
                relevance[option.action_id].role if option.action_id in relevance else "other",
                relevance[option.action_id].score if option.action_id in relevance else 0.0,
                relevance[option.action_id].reason_codes if option.action_id in relevance else (),
                subject_kind=INTERACTION_CAPABILITY_REGISTRY.require(
                    option.semantic_action
                ).subject_kinds[0].value,
                verification_family=option.verification_family,
                verification_contract_digest=option.verification_contract_digest,
                reversibility=option.reversibility,
                resource_ref=option.resource_ref,
            )
            for action_id in visible_action_ids
            if (option := by_id.get(action_id)) is not None
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
    """Conserve the validated business schema exactly at the model boundary."""

    try:
        validate_parameter_schema_contract(schema)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"parameter schema is unsupported or malformed: {exc}") from exc
    projected = to_json_compatible(schema)
    if not isinstance(projected, dict):  # pragma: no cover - validator guarantees object root
        raise TypeError("parameter schema root must remain an object")
    return projected


def _model_private_key(key: str) -> bool:
    """Shared model-boundary privacy predicate for non-schema projections."""

    return _private_key(key) or _route_key(key)


def _bounded_string(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _private_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(marker in normalized for marker in (*_SECRET_MARKERS, *_PRIVATE_PATH_MARKERS))


def _route_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(marker in normalized for marker in _PRIVATE_ROUTE_MARKERS)

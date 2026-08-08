"""Project Runtime-owned values into bounded, secret-safe model views."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from affordance_runtime.model_boundary.contracts import (
    AgentActionOptionView,
    AgentActionSpaceView,
    AgentDestinationView,
    AgentMaterialBindingView,
    AgentMilestoneView,
    AgentPlanView,
    AgentSuccessCriterionView,
    AgentTaskView,
    AgentTurnView,
)
from affordance_runtime.task.contracts import TaskGoal, criterion_id
from affordance_runtime.task.planning_contracts import TaskPlan
from affordance_runtime.world.contracts import ActionSpace
from affordance_runtime.world.view import AgentWorldView

if TYPE_CHECKING:
    from affordance_runtime.agent.state import Turn

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
    return AgentTaskView(
        task.task_id,
        task.instruction,
        task.constraints,
        task.allowed_effects,
        task.forbidden_effects,
        tuple(AgentSuccessCriterionView(criterion_id(item), item) for item in task.success_criteria),
        task.requested_outputs,
        task.risk_profile,
        project_public_value(task.inputs),
        tuple(AgentMaterialBindingView(item.name, item.media_type, item.digest) for item in task.material_bindings),
    )


def project_action_space(action_space: ActionSpace, world: AgentWorldView) -> AgentActionSpaceView:
    labels = {target.target_id: target.label for target in world.targets}
    return AgentActionSpaceView(
        tuple(
            AgentActionOptionView(
                option.action_id,
                option.semantic_action,
                option.target_id,
                labels.get(option.target_id, option.target_id),
                option.destination_required,
                tuple(AgentDestinationView(item, labels.get(item, item)) for item in option.eligible_destination_ids),
                project_public_value(option.parameter_schema),
                option.description,
                option.semantic_effects,
                option.risk,
                option.observation_barrier,
            )
            for option in action_space.options
        )
    )


def project_turns(turns: tuple[Turn, ...]) -> tuple[AgentTurnView, ...]:
    return tuple(_project_turn(turn) for turn in turns[-12:])


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


def _project_turn(turn: Turn) -> AgentTurnView:
    intent = turn.intent
    action_reason = turn.action_evaluation.reason if turn.action_evaluation is not None else ""
    task_reason = turn.task_evaluation.reason if turn.task_evaluation is not None else ""
    return AgentTurnView(
        type(turn.decision).__name__.lower(),
        intent.semantic_action if intent else "",
        intent.target_id if intent else "",
        intent.destination_id if intent else "",
        project_public_value(intent.parameters) if intent else {},
        turn.result.dispatch_status if turn.result is not None else "",
        turn.action_evaluation.status if turn.action_evaluation is not None else "",
        turn.task_evaluation.status if turn.task_evaluation is not None else "",
        (task_reason or action_reason)[:_MAX_STRING],
    )


def _private_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(marker in normalized for marker in (*_SECRET_MARKERS, *_PRIVATE_PATH_MARKERS))


def _route_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(marker in normalized for marker in _PRIVATE_ROUTE_MARKERS)

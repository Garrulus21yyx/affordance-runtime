"""One-way model-safe projection of a completed core step."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from affordance_runtime.agent.context.actor_world_snapshot import (
    ActorWorldNodeView,
    ActorWorldSnapshot,
)
from affordance_runtime.agent.context.contracts import AgentHistoricalTargetView, AgentTurnView
from affordance_runtime.agent.context.projection import project_public_value
from affordance_runtime.agent.decisions import (
    Abort,
    AgentDecision,
    AskUser,
    FinalResponse,
    LocalToolResult,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.evaluation.contracts import ActionOutcome

_MAX_STRING = 240


def project_step_result(result: StepResult) -> AgentTurnView:
    """Pair one chosen action with its observed outcome and task status."""

    decision = result.decision
    if not isinstance(
        decision,
        (
            SelectAction,
            RequestObservation,
            RequestActionPage,
            AskUser,
            LocalToolResult,
            FinalResponse,
            Wait,
            Abort,
        ),
    ):
        raise TypeError("policy failures do not enter model step history")
    if isinstance(decision, SelectAction) and result.execution is not None:
        intent = result.execution.request.intent
        action = result.action_outcome
        return AgentTurnView(
            "selectaction",
            intent.semantic_action,
            _historical_target(result, intent.target_id),
            _historical_target(result, intent.destination_id),
            _historical_value(project_public_value(intent.parameters)),
            intent.expected_outcome,
            str(result.execution.result.dispatch_status),
            str(action.local_postcondition) if action is not None else "",
            _transition(result, action),
            str(result.task_evaluation.status),
            action.reason if action is not None else result.feedback,
            {"feedback_code": result.feedback},
        )
    target_id = ""
    if isinstance(decision, RequestObservation | RequestActionPage):
        target_id = decision.subject_id if isinstance(decision, RequestObservation) else decision.target_id
    summary = dict(project_decision_summary(decision))
    if result.tool_result is not None:
        summary["result"] = project_public_value(result.tool_result)
    summary["feedback_code"] = result.feedback
    return AgentTurnView(
        type(decision).__name__.lower(),
        _control_tool_name(decision),
        _historical_target(result, target_id),
        task_evaluation_status=str(result.task_evaluation.status),
        reason=result.feedback,
        semantic_summary=_historical_value(summary),
    )


def _historical_target(result: StepResult, target_id: str) -> AgentHistoricalTargetView | None:
    if not target_id or result.policy_observation is None:
        return None
    ref = result.policy_target_refs.get(target_id, "")
    path = _node_path(result.policy_observation, ref)
    if not path:
        return None
    node = path[-1]
    label = node.label.strip() or " ".join(_class_tokens(node.state.get("semantic.dom.attribute.class_tokens")))
    return AgentHistoricalTargetView(
        _bounded(node.role, 80),
        _bounded(label),
        _semantic_neighborhood(path),
    )


def _node_path(snapshot: ActorWorldSnapshot, ref: str) -> tuple[ActorWorldNodeView, ...]:
    if not ref:
        return ()

    def visit(node: ActorWorldNodeView, parents: tuple[ActorWorldNodeView, ...]):
        path = (*parents, node)
        if node.ref == ref:
            return path
        for child in node.children:
            if found := visit(child, path):
                return found
        return ()

    for document in snapshot.documents:
        for root in document.roots:
            if found := visit(root, ()):
                return found
    return ()


def _semantic_neighborhood(path: tuple[ActorWorldNodeView, ...]) -> tuple[str, ...]:
    """Describe the target's nearest textual group without retaining generation-local refs."""

    if len(path) < 2:
        return ()
    target = path[-1]
    values: list[str] = []
    excluded_roles = {
        "button", "checkbox", "combobox", "link", "listbox", "menuitem",
        "option", "radio", "slider", "spinbutton", "switch", "textbox",
    }

    def add(value: str) -> None:
        value = value.strip()
        if value and value != target.label.strip() and value not in values:
            values.append(_bounded(value))

    def collect(node: ActorWorldNodeView) -> None:
        if node is target:
            return
        if node.role.casefold() not in excluded_roles:
            add(node.label)
        for child in node.children:
            collect(child)

    for ancestor in reversed(path[:-1]):
        before_count = len(values)
        add(ancestor.label)
        for child in ancestor.children:
            collect(child)
        # The first ancestor with useful text is the nearest semantic container.
        # Never cross into its parent's sibling groups merely to fill the bound.
        if len(values) > before_count:
            break
    return tuple(values[:4])


def _class_tokens(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    return ()


def _historical_value(value: object) -> object:
    """Drop private identity/lineage fields before a value becomes model history."""

    if isinstance(value, Mapping):
        return {
            str(key): _historical_value(item)
            for key, item in value.items()
            if str(key) not in {"subject_id", "target_id", "destination_id"}
            and not str(key).endswith("_ref")
        }
    if isinstance(value, tuple | list):
        return tuple(_historical_value(item) for item in value)
    return value


def project_decision_summary(decision: AgentDecision) -> Mapping[str, object]:
    if isinstance(decision, RequestObservation):
        return {
            "subject_id": _bounded(decision.subject_id),
            "purpose": decision.purpose,
            "evidence_property": decision.evidence_property,
            "reason": _bounded(decision.reason),
        }
    if isinstance(decision, RequestActionPage):
        return {
            "query": _bounded(decision.query, 120),
            "target_id": _bounded(decision.target_id),
            "relevance_role": decision.relevance_role,
            "cursor_requested": bool(decision.cursor),
        }
    if isinstance(decision, AskUser):
        return {"question": decision.question, "requested_fields": decision.requested_fields}
    if isinstance(decision, LocalToolResult):
        return project_public_value(decision.arguments)
    if isinstance(decision, FinalResponse):
        return {"content": _bounded(decision.content)}
    if isinstance(decision, Wait):
        return {"reason": decision.reason, "max_wait_ms": decision.max_wait_ms}
    if isinstance(decision, Abort):
        return {"category": decision.category, "reason": decision.reason}
    return {}


def _transition(result: StepResult, action: ActionOutcome | None) -> Mapping[str, object]:
    transition = dict(_target_snapshot(result, result.execution.request.intent.target_id if result.execution else ""))
    if action is not None:
        transition["observed_change"] = action.observed_change.value
        transition["evidence_method"] = action.evidence_method.value
        for key in ("fact_changes", "screenshot_changed", "target_changed", "structural_world_changed"):
            if key in action.evidence:
                transition[key] = _historical_value(project_public_value(action.evidence[key]))
    return transition


def _target_snapshot(result: StepResult, target_id: str) -> Mapping[str, object]:
    before = next(
        (item for item in result.before_world.targets if item.target_id == target_id),
        None,
    )
    if before is None:
        return {}
    after = next(
        (item for item in result.after_world.targets if item.target_id == target_id),
        None,
    )
    return {
        "role": _bounded(before.role, 80),
        "label": _bounded(before.label),
        "before_state": project_public_value(before.state),
        "after_state": project_public_value(after.state) if after is not None else None,
    }


def _control_tool_name(decision: AgentDecision) -> str:
    if isinstance(decision, LocalToolResult):
        return decision.tool_name
    return {
        RequestObservation: "request_evidence",
        RequestActionPage: "find_actions",
        AskUser: "ask_user",
        FinalResponse: "final_response",
        Wait: "wait",
        Abort: "abort",
        SelectAction: "select_action",
    }[type(decision)]


def _bounded(value: str, limit: int = _MAX_STRING) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"

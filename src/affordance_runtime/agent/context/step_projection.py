"""One-way model-safe projection of a completed core step."""

from __future__ import annotations

from collections.abc import Mapping

from affordance_runtime.agent.context.actor_world_snapshot import (
    ActorWorldNodeView,
    ActorWorldSnapshot,
)
from affordance_runtime.agent.context.contracts import (
    AgentHistoricalTargetView,
    AgentTurnView,
    sanitize_history_arguments,
    sanitize_history_prose,
    sanitize_history_value,
)
from affordance_runtime.agent.context.observation_delivery import (
    InformationDelta,
)
from affordance_runtime.agent.context.projection import project_public_value
from affordance_runtime.agent.decisions import (
    Abort,
    AgentDecision,
    FinalResponse,
    InteractionRequestDraft,
    LocalToolResult,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.interactions import InteractionRequest
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.evaluation.contracts import ActionOutcome

_MAX_STRING = 240


def project_step_result(
    result: StepResult,
    *,
    information_delta: InformationDelta | None = None,
) -> AgentTurnView:
    """Pair one chosen action with its observed outcome and task status."""

    decision = result.decision
    if not isinstance(
        decision,
        (
            SelectAction,
            RequestObservation,
            RequestActionPage,
            InteractionRequestDraft,
            InteractionRequest,
            LocalToolResult,
            FinalResponse,
            Wait,
            Abort,
        ),
    ):
        raise TypeError("policy failures do not enter model step history")
    if (
        isinstance(decision, SelectAction)
        and result.execution_receipts is not None
        and result.execution_receipts.receipts
    ):
        receipt = result.execution_receipts.receipts[-1]
        intent = receipt.request.intent
        action = result.action_outcome
        return AgentTurnView(
            decision.kind.value,
            sanitize_history_prose(intent.semantic_action),
            _historical_target(result, intent.target_id),
            _historical_target(result, intent.destination_id),
            _historical_value(project_public_value(intent.parameters)),
            sanitize_history_prose(intent.expected_outcome),
            str(sanitize_history_value(str(receipt.result.dispatch_status))),
            str(sanitize_history_value(str(action.local_postcondition))) if action is not None else "",
            _transition(result, action),
            _task_evaluation_status(result),
            sanitize_history_prose(action.reason if action is not None else result.feedback),
            {"feedback_code": sanitize_history_prose(result.feedback)},
        )
    target_id = ""
    if isinstance(decision, RequestObservation):
        target_id = (decision.subject_ids or decision.candidate_ids or ("",))[0]
    summary = dict(project_decision_summary(decision))
    if information_delta is not None:
        summary["information_delta"] = information_delta.kind.value
        summary["new_information_count"] = information_delta.new_information_count
    if isinstance(decision, RequestActionPage) and result.action_page_result is not None and information_delta is None:
        summary["result"] = result.action_page_result.to_history_value()
    summary["feedback_code"] = sanitize_history_prose(result.feedback)
    return AgentTurnView(
        decision.kind.value,
        _control_tool_name(decision),
        _historical_target(result, target_id),
        task_evaluation_status=_task_evaluation_status(result),
        reason=sanitize_history_prose(result.feedback),
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
    label = node.label.strip()
    return AgentHistoricalTargetView(
        _bounded(node.role, 80),
        _bounded(label),
        _semantic_neighborhood(path),
    )


def _task_evaluation_status(result: StepResult) -> str:
    return str(result.task_evaluation.status) if result.task_evaluation is not None else "not_evaluated"


def _historical_target_summary(result: StepResult, target_id: str) -> dict[str, object] | None:
    target = _historical_target(result, target_id)
    if target is None:
        return None
    return {"role": target.role, "label": target.label, "context": target.context}


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
        "button",
        "checkbox",
        "combobox",
        "link",
        "listbox",
        "menuitem",
        "option",
        "radio",
        "slider",
        "spinbutton",
        "switch",
        "textbox",
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


def _historical_value(value: object) -> object:
    """Drop private identity/lineage fields before a value becomes model history."""

    return sanitize_history_value(value)


def project_decision_summary(decision: AgentDecision | InteractionRequest) -> Mapping[str, object]:
    if isinstance(decision, RequestObservation):
        return {
            "purpose": decision.purpose.value,
            "atomic_query": _bounded(decision.atomic_query),
            "predicate": _bounded(decision.predicate),
            "max_results": decision.max_results,
            "public_intent": _bounded(decision.public_intent),
        }
    if isinstance(decision, RequestActionPage):
        return {"query": decision.query, "public_intent": _bounded(decision.public_intent)}
    if isinstance(decision, InteractionRequest):
        return {
            "prompt": decision.prompt,
            "response_kind": decision.response_kind.value,
            "public_intent": _bounded(decision.public_intent),
        }
    if isinstance(decision, InteractionRequestDraft):
        return {
            # A draft only survives into recent-step history on rejected
            # admission. Preserve the legacy AskUser projection keys for
            # compatibility consumers; admitted requests use the canonical
            # InteractionRequest branch above.
            "question": decision.prompt,
            "requested_fields": tuple(field.label for field in decision.field_drafts),
            "response_kind": decision.response_kind.value,
            "public_intent": _bounded(decision.public_intent),
            "committed": False,
        }
    if isinstance(decision, LocalToolResult):
        arguments = sanitize_history_arguments(
            project_public_value(decision.arguments),
            ephemeral_paths=decision.ephemeral_argument_paths,
        )
        summary = dict(arguments) if isinstance(arguments, Mapping) else {}
        for name in (
            "scope",
            "has_more",
            "result_page",
            "source_coverage",
            "region_membership",
            "collection_coverage",
        ):
            if name in decision.result:
                summary[name] = project_public_value(decision.result[name])
        continuations = decision.result.get("collection_continuations")
        if isinstance(continuations, tuple | list):
            summary["collection_continuation_count"] = len(continuations)
        continuation = decision.result.get("continuation")
        if isinstance(continuation, Mapping):
            summary["continuation"] = {
                name: project_public_value(continuation[name])
                for name in ("kind", "item_offset", "total_items", "path", "offset", "total")
                if name in continuation
            }
        return summary
    if isinstance(decision, FinalResponse):
        return {"content": _bounded(decision.content), "public_intent": _bounded(decision.public_intent)}
    if isinstance(decision, Wait):
        return {
            "reason": decision.reason,
            "max_wait_ms": decision.max_wait_ms,
            "public_intent": _bounded(decision.public_intent),
        }
    if isinstance(decision, Abort):
        return {
            "category": decision.category,
            "reason": decision.reason,
            "public_intent": _bounded(decision.public_intent),
        }
    return {}


def _transition(result: StepResult, action: ActionOutcome | None) -> Mapping[str, object]:
    receipt = (
        result.execution_receipts.receipts[-1]
        if result.execution_receipts is not None and result.execution_receipts.receipts
        else None
    )
    transition = dict(_target_snapshot(result, receipt.request.intent.target_id if receipt else ""))
    delta = result.public_world_delta
    assert delta is not None
    transition["semantic_change"] = "changed" if delta.semantic_changed else "unchanged"
    if action is not None:
        transition["observed_change"] = action.observed_change.value
        transition["evidence_method"] = action.evidence_method.value
        for key in ("screenshot_changed", "target_changed", "structural_world_changed"):
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


def _control_tool_name(decision: AgentDecision | InteractionRequest) -> str:
    if isinstance(decision, LocalToolResult):
        return decision.tool_name
    return decision.kind.value


def _bounded(value: str, limit: int = _MAX_STRING) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"

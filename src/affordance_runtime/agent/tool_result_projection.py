"""Pure provider-result projection from the committed ``StepResult`` algebra.

The committed step remains execution truth.  This module does not retain a
pending call, mutate delivery state, or create a second outcome wrapper.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, assert_never

from affordance_runtime.agent.context.compact_world_renderer import inspect_result_grounding
from affordance_runtime.agent.context.contracts import HISTORY_RETURN_PATHS_METADATA_KEY
from affordance_runtime.agent.decisions import (
    Abort,
    FinalResponse,
    InteractionRequestDraft,
    LocalToolResult,
    ReadRegionResult,
    RequestActionPage,
    RequestObservation,
    SearchPageContentResult,
    SelectAction,
    ToolRejectedResult,
    Wait,
)
from affordance_runtime.agent.interactions import InteractionRequest
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.world.observation_outcomes import (
    InputLocator,
    QueryScopeLocator,
    ResultLocator,
)
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind

if TYPE_CHECKING:
    from affordance_runtime.agent.run_state import StepResult


@dataclass(frozen=True)
class ToolReturnGrounding:
    """Exact same-call refs/routes declared by the ToolReturn producer."""

    public_refs: tuple[str, ...] = ()
    action_routes: tuple[tuple[str, str, str], ...] = ()

    def __post_init__(self) -> None:
        refs = tuple(self.public_refs)
        routes = tuple(tuple(route) for route in self.action_routes)
        if len(set(refs)) != len(refs) or any(
            not isinstance(ref, str) or not PublicRefCodec.accepts(ref) for ref in refs
        ):
            raise ValueError("ToolReturn grounding refs are invalid")
        if len(set(routes)) != len(routes) or any(
            len(route) != 3
            or any(not isinstance(item, str) for item in route)
            or not route[0].strip()
            or not PublicRefCodec.accepts(route[1], expected=PublicRefKind.EXECUTABLE)
            or route[2]
            or route[1] not in refs
            for route in routes
        ):
            raise ValueError("ToolReturn grounding routes are invalid")
        object.__setattr__(self, "public_refs", refs)
        object.__setattr__(self, "action_routes", routes)


def committed_tool_call_id(step: StepResult) -> str:
    """Return the accepted external-call identity, exhaustively and without inference."""

    decision = step.decision
    if isinstance(decision, PolicyFailure):
        return ""
    if isinstance(
        decision,
        (
            SelectAction,
            RequestObservation,
            RequestActionPage,
            InteractionRequestDraft,
            InteractionRequest,
            ReadRegionResult,
            SearchPageContentResult,
            ToolRejectedResult,
            Wait,
            Abort,
        ),
    ):
        return decision.tool_call_id
    if isinstance(decision, FinalResponse):
        return ""
    assert_never(decision)


def project_committed_tool_return(step: StepResult) -> Mapping[str, object] | None:
    """Project one public ``ToolReturn.return_value`` from committed typed facts.

    ``None`` means the step did not originate from an accepted external tool
    call. Local tools own and bound the exact mapping before the step commits;
    this projection never edits or reconstructs that mapping.
    """

    call_id = committed_tool_call_id(step)
    if not call_id:
        return None
    decision = step.decision
    assert not isinstance(decision, PolicyFailure | FinalResponse)

    failure = (
        {
            "stage": step.runtime_failure.stage.value,
            "kind": step.runtime_failure.kind.value,
            "code": step.runtime_failure.code,
        }
        if step.runtime_failure is not None
        else None
    )
    common: dict[str, object] = {
        "status": step.status_after.value,
        "failed": failure is not None,
    }
    if failure is not None:
        common["failure"] = failure

    if isinstance(decision, SelectAction):
        batch = step.execution_receipts
        terminal_failure = batch.terminal_failure if batch is not None else None
        dispatch: dict[str, object] = {
            "completion": batch.completion.value if batch is not None else "not_dispatched",
            "receipts": (
                tuple(
                    {
                        "dispatch_status": item.result.dispatch_status.value,
                        "transport_success": item.result.transport_success,
                        "error": item.result.error.value if item.result.error is not None else None,
                    }
                    for item in batch.receipts
                )
                if batch is not None
                else ()
            ),
        }
        if batch is not None and batch.cancellation_phase is not None:
            dispatch["cancellation_phase"] = batch.cancellation_phase.value
        if terminal_failure is not None:
            currentness = {
                key.removeprefix("currentness_"): terminal_failure.adapter_evidence[key]
                for key in ("currentness_status", "currentness_reason")
                if key in terminal_failure.adapter_evidence
            }
            dispatch["terminal_failure"] = {
                "dispatch_status": terminal_failure.dispatch_status.value,
                "transport_success": terminal_failure.transport_success,
                "error": terminal_failure.error.value if terminal_failure.error is not None else None,
                **({"currentness": currentness} if currentness else {}),
            }
        gui_result: dict[str, object] = {
            "run_status": step.status_after.value,
            "runtime_failed": failure is not None,
            "kind": "gui_action_result",
            "dispatch": dispatch,
            "effect": _public_gui_effect(step),
        }
        if failure is not None:
            gui_result["runtime_failure"] = failure
        return freeze_json(gui_result)
    if isinstance(decision, RequestObservation):
        outcome = step.observation_outcome
        if outcome is None:
            common.update({"kind": "observation", "purpose": decision.purpose.value})
            return freeze_json(common)
        observed_items = tuple(_public_observed_item(step, item) for item in outcome.observed_items)
        public_evidence_refs = tuple(
            dict.fromkeys(
                ref
                for item in observed_items
                for ref in _public_string_tuple(item.get("evidence_refs", ()))
                if isinstance(ref, str)
            )
        )
        common["run_status"] = common.pop("status")
        common.update(
            {
                "kind": "observation",
                "query_id": outcome.query_id,
                "purpose": outcome.purpose.value,
                "status": outcome.disposition.value,
                "observed_items": observed_items,
                "unknown_items": tuple(
                    {
                        "locator": _public_locator(item.locator),
                        "reason": item.reason.value,
                    }
                    for item in outcome.unknown_items
                ),
                "evidence_refs": public_evidence_refs,
            }
        )
        if outcome.failure_reason is not None:
            common["reason_code"] = outcome.failure_reason.value
        if any(item.get("target_ref") and item.get("verbs") for item in observed_items):
            common["executable_grounding"] = "attached_to_returned_readable_targets"
        return freeze_json(common)
    if isinstance(decision, RequestActionPage):
        action_page_result = step.action_page_result
        if action_page_result is None:
            common.update({"kind": "discovery", "matches": ()})
            return freeze_json(common)
        return freeze_json(action_page_result.to_public_value())
    if isinstance(decision, InteractionRequest):
        common.update(
            {
                "kind": "needs_input",
                "request_id": decision.request_id,
                "response_kind": decision.response_kind.value,
                "field_ids": tuple(item.field_id for item in decision.fields),
                "option_ids": tuple(item.option_id for item in decision.options),
            }
        )
        return freeze_json(common)
    if isinstance(decision, InteractionRequestDraft):
        common.update(
            {
                "kind": "needs_input",
                "response_kind": decision.response_kind.value,
                "committed": False,
            }
        )
        return freeze_json(common)
    if isinstance(decision, LocalToolResult):
        return freeze_json(decision.result)
    if isinstance(decision, Wait):
        common.update({"kind": "wait", "waited_ms": step.waited_ms})
        return freeze_json(common)
    if isinstance(decision, Abort):
        common.update({"kind": "abort", "category": decision.category})
        return freeze_json(common)
    assert_never(decision)


def _public_locator(locator: InputLocator | QueryScopeLocator | ResultLocator) -> Mapping[str, object]:
    if isinstance(locator, InputLocator):
        return {"kind": locator.kind, "input_indices": locator.input_indices}
    if isinstance(locator, ResultLocator):
        return {"kind": locator.kind, "result_index": locator.result_index}
    return {"kind": locator.kind}


def _public_string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _public_gui_effect(step: StepResult) -> Mapping[str, object]:
    outcome = step.action_outcome
    if outcome is None:
        return {
            "availability": "unavailable",
            "reason": _gui_effect_unavailable_reason(step),
        }
    projection = step.after_public_world
    refs: tuple[str, ...] = ()
    if projection is not None:
        refs = tuple(
            dict.fromkeys(
                public
                for evidence in outcome.evidence_refs
                for public in (
                    projection.private_fact_id_refs.get(
                        evidence,
                        projection.fact_refs.get(evidence, ""),
                    ),
                )
                if public
            )
        )
    return {
        "availability": "available",
        "observed_change": outcome.observed_change.value,
        "local_postcondition": outcome.local_postcondition.value,
        "evidence_method": outcome.evidence_method.value,
        "reason": outcome.reason[:500],
        "evidence_refs": refs,
    }


def _gui_effect_unavailable_reason(step: StepResult) -> str:
    batch = step.execution_receipts
    if batch is None:
        return "not_dispatched"
    if batch.cancellation_phase is not None:
        return f"{batch.cancellation_phase.value}_cancelled"
    if any(item.result.dispatch_status.value == "sent_unknown" for item in batch.receipts):
        return "sent_unknown"
    if batch.terminal_failure is not None:
        return "execution_terminal_failure"
    if step.runtime_failure is not None:
        return f"{step.runtime_failure.stage.value}_runtime_failure"
    if batch.receipts:
        return "not_evaluated"
    return "not_dispatched"


def _public_observed_item(step: StepResult, item) -> Mapping[str, object]:
    projection = step.after_public_world
    target_refs = projection.target_refs if projection is not None else {}
    fact_refs = projection.fact_refs if projection is not None else {}
    private_fact_refs = projection.private_fact_id_refs if projection is not None else {}
    public_targets = tuple(target_refs[subject] for subject in item.subject_ids if subject in target_refs)
    public_evidence = tuple(
        dict.fromkeys(
            public
            for evidence in item.evidence_refs
            for public in (private_fact_refs.get(evidence, fact_refs.get(evidence, "")),)
            if public
        )
    )
    result: dict[str, object] = {
        "locator": _public_locator(item.locator),
        "evidence_refs": public_evidence,
    }
    if len(public_targets) == 1:
        target_ref = public_targets[0]
        result["target_ref"] = target_ref
        if projection is not None:
            record = next(
                (candidate for candidate in projection.ordered_target_records if candidate.ref == target_ref),
                None,
            )
            if record is not None and record.verbs:
                result["verbs"] = record.verbs
    elif public_targets:
        result["target_refs"] = public_targets
    return freeze_json(result)


def project_committed_tool_metadata(step: StepResult) -> Mapping[str, object]:
    """Project Runtime-private ToolReturn metadata from the same committed step."""

    call_id = committed_tool_call_id(step)
    if not call_id:
        return freeze_json({})
    decision = step.decision
    assert not isinstance(decision, PolicyFailure | FinalResponse)
    return_value = project_committed_tool_return(step)
    assert return_value is not None
    ephemeral_paths = _committed_tool_return_ephemeral_paths(step, return_value)
    return freeze_json(
        {
            "tool_call_id": call_id,
            "tool_name": getattr(decision, "tool_name", decision.kind.value),
            "before_world": step.before_world.observation_id,
            "after_world": step.after_world.observation_id,
            "runtime_failure": (to_json_compatible(step.runtime_failure) if step.runtime_failure is not None else None),
            HISTORY_RETURN_PATHS_METADATA_KEY: tuple(tuple(path) for path in ephemeral_paths),
        }
    )


def project_committed_tool_grounding(
    step: StepResult,
    return_value: Mapping[str, object],
) -> ToolReturnGrounding:
    """Project same-call grounding without scanning arbitrary result values."""

    if return_value.get("executable_grounding") != "attached_to_returned_readable_targets":
        return ToolReturnGrounding()
    decision = step.decision
    if isinstance(decision, ReadRegionResult | SearchPageContentResult):
        refs, routes = inspect_result_grounding(return_value)
        return ToolReturnGrounding(refs, routes)
    if isinstance(decision, RequestObservation):
        return _observation_tool_return_grounding(return_value)
    return ToolReturnGrounding()


def _observation_tool_return_grounding(
    return_value: Mapping[str, object],
) -> ToolReturnGrounding:
    refs: set[str] = set()
    routes: set[tuple[str, str, str]] = set()
    items = return_value.get("observed_items", ())
    if not isinstance(items, tuple | list):
        return ToolReturnGrounding()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        evidence_refs = item.get("evidence_refs", ())
        if isinstance(evidence_refs, tuple | list):
            refs.update(
                ref
                for ref in evidence_refs
                if isinstance(ref, str) and PublicRefCodec.accepts(ref, expected=PublicRefKind.FACT)
            )
        target_refs = item.get("target_refs", ())
        if isinstance(target_refs, tuple | list):
            refs.update(ref for ref in target_refs if isinstance(ref, str) and PublicRefCodec.accepts(ref))
        target_ref = item.get("target_ref")
        if isinstance(target_ref, str) and PublicRefCodec.accepts(target_ref):
            refs.add(target_ref)
        verbs = item.get("verbs", ())
        if (
            isinstance(target_ref, str)
            and PublicRefCodec.accepts(target_ref, expected=PublicRefKind.EXECUTABLE)
            and isinstance(verbs, tuple | list)
        ):
            routes.update(
                (operation, target_ref, "") for operation in verbs if isinstance(operation, str) and operation.strip()
            )
    return ToolReturnGrounding(tuple(sorted(refs)), tuple(sorted(routes)))


def _committed_tool_return_ephemeral_paths(
    step: StepResult,
    value: Mapping[str, object],
) -> tuple[tuple[str, ...], ...]:
    """Return the typed at-rest projection owned by this ToolReturn producer."""

    decision = step.decision
    if isinstance(decision, LocalToolResult):
        return decision.ephemeral_result_paths
    if isinstance(decision, SelectAction):
        return (("effect", "evidence_refs"),)
    if isinstance(decision, RequestObservation):
        return (
            ("query_id",),
            ("evidence_refs",),
            ("executable_grounding",),
            ("observed_items", "*", "evidence_refs"),
            ("observed_items", "*", "target_ref"),
            ("observed_items", "*", "target_refs"),
            ("observed_items", "*", "verbs"),
        )
    if isinstance(decision, RequestActionPage):
        return (
            ("matches", "*", "target_ref"),
            ("matches", "*", "destination_refs"),
        )
    if isinstance(decision, InteractionRequest):
        return (("request_id",), ("field_ids",), ("option_ids",))
    if isinstance(decision, InteractionRequestDraft | Wait | Abort):
        return ()
    assert value
    assert_never(decision)

"""Pure provider-result projection from the committed ``StepResult`` algebra.

The committed step remains execution truth.  This module does not retain a
pending call, mutate delivery state, or create a second outcome wrapper.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, assert_never

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

if TYPE_CHECKING:
    from affordance_runtime.agent.run_state import StepResult


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
        result: dict[str, object] = {
            "run_status": step.status_after.value,
            "runtime_failed": failure is not None,
            "kind": "gui_action_result",
            "dispatch": dispatch,
            "effect": _public_gui_effect(step),
        }
        if failure is not None:
            result["runtime_failure"] = failure
        return freeze_json(result)
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
        result = step.action_page_result
        if result is None:
            common.update({"kind": "discovery", "matches": ()})
            return freeze_json(common)
        return freeze_json(result.to_public_value())
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
    refs = ()
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
    public_targets = tuple(
        target_refs[subject]
        for subject in item.subject_ids
        if subject in target_refs
    )
    public_evidence = tuple(
        dict.fromkeys(
            public
            for evidence in item.evidence_refs
            for public in (
                private_fact_refs.get(evidence, fact_refs.get(evidence, "")),
            )
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
    return freeze_json(
        {
            "tool_call_id": call_id,
            "tool_name": getattr(decision, "tool_name", decision.kind.value),
            "before_world": step.before_world.observation_id,
            "after_world": step.after_world.observation_id,
            "runtime_failure": (
                to_json_compatible(step.runtime_failure) if step.runtime_failure is not None else None
            ),
        }
    )

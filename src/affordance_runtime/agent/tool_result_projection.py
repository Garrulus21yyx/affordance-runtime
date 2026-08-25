"""Pure provider-result projection from the committed ``StepResult`` algebra.

The committed step remains execution truth.  This module does not retain a
pending call, mutate delivery state, or create a second outcome wrapper.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, assert_never

from affordance_runtime.agent.decisions import (
    Abort,
    AskUser,
    FinalResponse,
    LocalToolResult,
    ReadRegionResult,
    RequestActionPage,
    RequestObservation,
    SearchPageContentResult,
    SelectAction,
    ToolRejectedResult,
    Wait,
)
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.immutable import freeze_json, to_json_compatible

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
            AskUser,
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
        receipt_failure = bool(
            batch is not None
            and any(
                not item.result.transport_success or item.result.error is not None
                for item in batch.receipts
            )
        )
        common["failed"] = failure is not None or terminal_failure is not None or receipt_failure
        common.update(
            {
                "kind": "execution_receipt",
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
        )
        if terminal_failure is not None:
            currentness = {
                key.removeprefix("currentness_"): terminal_failure.adapter_evidence[key]
                for key in ("currentness_status", "currentness_reason")
                if key in terminal_failure.adapter_evidence
            }
            common["terminal_failure"] = {
                "dispatch_status": terminal_failure.dispatch_status.value,
                "transport_success": terminal_failure.transport_success,
                "error": terminal_failure.error.value if terminal_failure.error is not None else None,
                **({"currentness": currentness} if currentness else {}),
            }
        return freeze_json(common)
    if isinstance(decision, RequestObservation):
        common.update({"kind": "observation", "purpose": decision.purpose})
        return freeze_json(common)
    if isinstance(decision, RequestActionPage):
        result = step.action_page_result
        if result is None:
            common.update({"kind": "discovery", "matches": ()})
            return freeze_json(common)
        return freeze_json(result.to_public_value())
    if isinstance(decision, AskUser):
        common.update({"kind": "needs_input", "requested_fields": decision.requested_fields})
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

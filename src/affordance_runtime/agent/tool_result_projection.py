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
    ContinueDeliveryResult,
    FinalResponse,
    LocalToolResult,
    PublicEvidenceResult,
    ReadRegionResult,
    RememberFactResult,
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
            ContinueDeliveryResult,
            RememberFactResult,
            ToolRejectedResult,
            Wait,
            Abort,
        ),
    ):
        return decision.tool_call_id
    if isinstance(decision, FinalResponse):
        return ""
    assert_never(decision)


def committed_public_evidence(step: StepResult) -> PublicEvidenceResult | None:
    """Select typed public evidence by result type, never by operation name."""

    decision = step.decision
    if isinstance(decision, LocalToolResult):
        result = decision.result
        return result if isinstance(result, PublicEvidenceResult) else None
    if isinstance(
        decision,
        (
            SelectAction,
            RequestObservation,
            RequestActionPage,
            AskUser,
            FinalResponse,
            Wait,
            Abort,
            PolicyFailure,
        ),
    ):
        return None
    assert_never(decision)


def project_committed_tool_return(
    step: StepResult,
    *,
    admitted_evidence_records: tuple[Mapping[str, object], ...] | None = None,
) -> Mapping[str, object] | None:
    """Project one public ``ToolReturn.return_value`` from committed typed facts.

    ``None`` means the step did not originate from an accepted external tool
    call.  Supplying ``admitted_evidence_records`` selects an exact complete
    prefix; an empty tuple is a legal zero-prefix result.
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
        result = decision.result
        if isinstance(result, PublicEvidenceResult):
            records = result.records if admitted_evidence_records is None else admitted_evidence_records
            return freeze_json(result.with_records(tuple(records)))
        return freeze_json(result)
    if isinstance(decision, Wait):
        common.update({"kind": "wait", "waited_ms": step.waited_ms})
        return freeze_json(common)
    if isinstance(decision, Abort):
        common.update({"kind": "abort", "category": decision.category})
        return freeze_json(common)
    assert_never(decision)


def project_committed_tool_metadata(
    step: StepResult,
    *,
    record_digests: tuple[str, ...] = (),
) -> Mapping[str, object]:
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
            "record_digests": tuple(record_digests),
            "before_world": step.before_world.observation_id,
            "after_world": step.after_world.observation_id,
            "runtime_failure": (
                to_json_compatible(step.runtime_failure) if step.runtime_failure is not None else None
            ),
        }
    )

"""公共 Session 的纯投影与兼容转换。

本模块只把 Runtime owner 已产生的事实转换为公共值，不拥有 Session 状态，
也不得根据展示需要重新推断执行结果、权限或完成状态。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from affordance_runtime.actions.reconciliation import (
    EffectReconciliation,
)
from affordance_runtime.agent.decisions import FinalResponse, RequestObservation, SelectAction
from affordance_runtime.agent.interactions import (
    BooleanFieldValue,
    DateFieldValue,
    DecimalFieldValue,
    FreeTextResponse,
    IntegerFieldValue,
    InteractionAdmissionCode,
    InteractionRequest,
    InteractionResponse,
    MultiSelectionResponse,
    SingleSelectionResponse,
    TextFieldValue,
)
from affordance_runtime.agent.observability import NullRunTraceSink
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.run_state import RunState, RunStatus, StepResult
from affordance_runtime.evaluation.contracts import (
    EvidenceMethod,
    LocalPostconditionStatus,
    TaskOutcomeKind,
)
from affordance_runtime.execution.contracts import ExecutionCompletion
from affordance_runtime.risk.contracts import RiskAssessment
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intake import (
    TaskInputRequired,
    TaskPolicyRejected,
    TaskUnsupported,
)
from affordance_runtime.task.revision import (
    RevisionFailed,
    RevisionNeedsInput,
    RevisionNewTaskSuggested,
    RevisionNoChange,
    RevisionReady,
    RevisionUnsupported,
    revision_outcome_code,
)
from affordance_runtime.world.observation_outcomes import ObservationQueryDisposition

from .public_session_contracts import (
    PublicAgentIntent,
    PublicCommandAccepted,
    PublicCommandAdmission,
    PublicCommandConflict,
    PublicCommandRejected,
    PublicCommandUnsupported,
    PublicCompletion,
    PublicConfirmationRequired,
    PublicConflictCode,
    PublicControlOutcome,
    PublicEffectReconciliation,
    PublicEvidenceSummary,
    PublicFailure,
    PublicFeedSource,
    PublicInteractionRequest,
    PublicInteractionRequested,
    PublicPendingConfirmation,
    PublicRevisionApplied,
    PublicRuntimeActivity,
    PublicSessionCommandCapability,
    PublicSessionCommandKind,
    PublicSessionConflict,
    PublicSessionControlOwner,
    PublicSessionStatus,
)

if TYPE_CHECKING:
    # 只为静态类型检查引用状态 owner；运行时禁止反向导入，避免投影模块参与控制流。
    from .public_session import TargetRuntimeSession


def _convert_public_session_conflict(
    command_id: str,
    conflict: PublicSessionConflict,
) -> PublicCommandAdmission:
    """在 Runtime owner 边界穷尽地规范化旧内部错误码。"""

    code = conflict.code
    if code in {
        "revision_needs_input",
        "revision_no_change",
        "revision_new_task_suggested",
        "revision_unsupported",
        "revision_failed",
        "effect_reconciliation_required",
        "effect_non_compensable",
        "effect_reconciliation_unknown",
        "effect_reconciliation_unsupported",
    }:
        return PublicCommandAccepted("accepted", command_id, conflict.snapshot)
    conflict_codes: dict[str, PublicConflictCode] = {
        "stale_command": "stale_command",
        "command_identity_reused": "command_identity_reused",
        "revision_command_conflict": "command_identity_reused",
        "resume_command_conflict": "command_identity_reused",
        "takeover_command_conflict": "command_identity_reused",
        "interrupt_mismatch": "interaction_ref_mismatch",
        "checkpoint_mismatch": "checkpoint_mismatch",
        "checkpoint_already_resumed": "checkpoint_already_consumed",
        "checkpoint_already_revised": "checkpoint_already_consumed",
        "takeover_command_consumed": "checkpoint_already_consumed",
        "session_closed": "session_closed",
        "session_not_idle": "session_state_conflict",
        "run_active": "session_state_conflict",
        "run_not_active": "session_state_conflict",
        "run_not_resumable": "session_state_conflict",
        "run_not_revisable": "session_state_conflict",
        "control_request_conflict": "session_state_conflict",
        "user_control_return_unavailable": "session_state_conflict",
        "user_control_active": "control_owner_conflict",
        "user_control_not_active": "control_owner_conflict",
        "control_lease_mismatch": "control_lease_mismatch",
    }
    if code in conflict_codes:
        return PublicCommandConflict(
            "conflict",
            command_id,
            conflict_codes[code],
            conflict.snapshot,
        )
    if code in {
        "pause_unavailable",
        "resume_unavailable",
        "revision_unavailable",
        "takeover_unavailable",
    }:
        return PublicCommandUnsupported(
            "unsupported",
            command_id,
            "command_not_supported",
            conflict.snapshot,
        )
    if code in {
        "pause_persistence_failed",
        "resume_persistence_failed",
        "revision_persistence_failed",
        "takeover_persistence_failed",
        "checkpoint_not_found",
    }:
        return PublicCommandRejected(
            "rejected",
            command_id,
            "command_persistence_failed",
            conflict.snapshot,
        )
    if code in {item.value for item in InteractionAdmissionCode}:
        return PublicCommandRejected(
            "rejected",
            command_id,
            "interaction_response_invalid",
            conflict.snapshot,
        )
    if code in {
        "control_boundary_failed",
        "revision_pause_failed",
        "takeover_pause_failed",
        "user_control_currentness_unavailable",
    }:
        return PublicCommandRejected(
            "rejected",
            command_id,
            "command_processing_failed",
            conflict.snapshot,
        )
    return PublicCommandRejected(
        "rejected",
        command_id,
        "internal_contract_failure",
        conflict.snapshot,
    )


def _v3_command_capabilities(
    *,
    status: PublicSessionStatus,
    checkpoint_store_available: bool,
    checkpoint_id: str | None,
    resume_eligible: bool,
    pending_interaction: PublicInteractionRequest | None,
    pending_confirmation: PublicPendingConfirmation | None,
    control_owner: PublicSessionControlOwner,
    control_return_in_progress: bool,
    reconciliation_blocks_control: bool,
    closed: bool,
) -> tuple[PublicSessionCommandCapability, ...]:
    if closed:
        return ()
    if control_return_in_progress:
        return (PublicSessionCommandCapability(PublicSessionCommandKind.CLOSE_SESSION),)
    if control_owner is PublicSessionControlOwner.USER:
        return (
            PublicSessionCommandCapability(PublicSessionCommandKind.RETURN_CONTROL),
            PublicSessionCommandCapability(PublicSessionCommandKind.CLOSE_SESSION),
        )

    capabilities: list[PublicSessionCommandCapability] = []
    if status is PublicSessionStatus.IDLE:
        capabilities.append(PublicSessionCommandCapability(PublicSessionCommandKind.START_TASK))
    if status in {
        PublicSessionStatus.RUNNING,
        PublicSessionStatus.WAITING_USER,
        PublicSessionStatus.WAITING_CONFIRMATION,
        PublicSessionStatus.PAUSED,
    }:
        capabilities.append(PublicSessionCommandCapability(PublicSessionCommandKind.CANCEL_TASK))
    if pending_interaction is not None and status is PublicSessionStatus.WAITING_USER:
        capabilities.append(
            PublicSessionCommandCapability(
                PublicSessionCommandKind.RESPOND_INTERACTION,
                interaction_ref=pending_interaction.request_id,
                prompt=pending_interaction.prompt,
            )
        )
    if pending_confirmation is not None and status is PublicSessionStatus.WAITING_CONFIRMATION:
        for kind in (
            PublicSessionCommandKind.APPROVE_ACTION,
            PublicSessionCommandKind.REJECT_ACTION,
        ):
            capabilities.append(
                PublicSessionCommandCapability(
                    kind,
                    interaction_ref=pending_confirmation.interrupt_id,
                    summary=pending_confirmation.summary,
                    risk=pending_confirmation.risk,
                )
            )
    if checkpoint_store_available and status in {
        PublicSessionStatus.RUNNING,
        PublicSessionStatus.WAITING_USER,
        PublicSessionStatus.WAITING_CONFIRMATION,
    }:
        capabilities.append(PublicSessionCommandCapability(PublicSessionCommandKind.PAUSE_TASK))
    if (
        checkpoint_store_available
        and not reconciliation_blocks_control
        and status
        in {
            PublicSessionStatus.RUNNING,
            PublicSessionStatus.WAITING_USER,
            PublicSessionStatus.WAITING_CONFIRMATION,
            PublicSessionStatus.PAUSED,
        }
    ):
        capabilities.append(PublicSessionCommandCapability(PublicSessionCommandKind.REVISE_TASK))
    if status is PublicSessionStatus.PAUSED and resume_eligible and checkpoint_id is not None:
        capabilities.append(PublicSessionCommandCapability(PublicSessionCommandKind.RESUME_TASK))
    if (
        checkpoint_store_available
        and status
        in {
            PublicSessionStatus.RUNNING,
            PublicSessionStatus.WAITING_USER,
            PublicSessionStatus.WAITING_CONFIRMATION,
            PublicSessionStatus.PAUSED,
        }
        and (status is not PublicSessionStatus.PAUSED or checkpoint_id is not None)
    ):
        capabilities.append(PublicSessionCommandCapability(PublicSessionCommandKind.TAKE_OVER))
    capabilities.append(PublicSessionCommandCapability(PublicSessionCommandKind.CLOSE_SESSION))
    kinds = tuple(capability.kind for capability in capabilities)
    if len(kinds) != len(set(kinds)):
        raise AssertionError("Runtime v3 command capabilities must be unique by kind")
    return tuple(capabilities)


def _revision_pause_command_id(command_id: str) -> str:
    digest = hashlib.sha256(command_id.encode()).hexdigest()[:32]
    return f"revision-pause:{digest}"


def _takeover_pause_command_id(command_id: str) -> str:
    digest = hashlib.sha256(command_id.encode()).hexdigest()[:32]
    return f"takeover-pause:{digest}"


def _public_effect_reconciliation(
    reconciliation: EffectReconciliation | None,
) -> PublicEffectReconciliation | None:
    if reconciliation is None:
        return None
    return PublicEffectReconciliation(
        cast(
            Literal["pending", "compensated", "needs_input"],
            reconciliation.status.value,
        ),
        reconciliation.reason.value,
        reconciliation.original_effect.effect_ref,
        reconciliation.original_effect.semantic_action,
        reconciliation.original_effect.resource_ref,
        cast(
            Literal["reversible", "compensatable", "irreversible", "unknown"],
            reconciliation.original_effect.reversibility.value,
        ),
        (reconciliation.compensation_effect.effect_ref if reconciliation.compensation_effect is not None else ""),
    )


def _revision_rejection(
    compiler: object,
    intake: object,
) -> tuple[str, str]:
    if isinstance(intake, TaskInputRequired):
        return "revision_needs_input", intake.question
    if isinstance(intake, TaskPolicyRejected | TaskUnsupported):
        return "revision_unsupported", intake.reason_code
    if isinstance(
        compiler,
        RevisionNeedsInput | RevisionNoChange | RevisionNewTaskSuggested | RevisionUnsupported | RevisionFailed,
    ):
        message = compiler.question if isinstance(compiler, RevisionNeedsInput) else compiler.reason
        return revision_outcome_code(compiler), message
    if isinstance(compiler, RevisionReady):
        return "revision_failed", "task_intake_failed"
    return "revision_failed", "invalid_task_revision_outcome"


@dataclass(frozen=True)
class _SessionProjectionSink(NullRunTraceSink):
    session: TargetRuntimeSession

    def run_started(self, task: object, state: object) -> None:
        if isinstance(task, TaskGoal) and isinstance(state, RunState):
            self.session._observe_started(task, state)

    def step_completed(self, step_number: int, result: object) -> None:
        if isinstance(result, StepResult):
            self.session._observe_step(step_number, result)

    def run_paused(self, state: object) -> None:
        if isinstance(state, RunState):
            self.session._observe_paused(state)

    def run_finished(self, state: object) -> None:
        if isinstance(state, RunState):
            self.session._observe_finished(state)

    def run_resumed(self, kind: str, details: Mapping[str, object]) -> None:
        del kind, details
        self.session._observe_resumed()

    def run_error(self, error: BaseException, state: object) -> None:
        if isinstance(state, RunState):
            self.session._observe_error(error, state)


def _feed_source(
    factory: Callable[[str], PublicFeedSource],
) -> Callable[[str], PublicFeedSource]:
    return factory


def _public_interaction_request(request: InteractionRequest) -> PublicInteractionRequest:
    return PublicInteractionRequest(
        request.request_id,
        request.prompt,
        request.response_kind.value,
        request.fields,
        request.options,
        request.public_intent,
    )


def _public_confirmation(risk: RiskAssessment) -> PublicPendingConfirmation:
    if not isinstance(risk, RiskAssessment):
        raise TypeError("pending confirmation requires a typed risk assessment")
    return PublicPendingConfirmation(
        f"confirmation:{risk.subject_id}",
        risk.reason,
        risk.risk.value,
    )


def _interaction_response_text(
    request: InteractionRequest,
    response: InteractionResponse,
) -> str:
    if isinstance(response, FreeTextResponse):
        return response.text
    options = {item.option_id: item.title for item in request.options}
    if isinstance(response, SingleSelectionResponse):
        return options[response.option_id]
    if isinstance(response, MultiSelectionResponse):
        return ", ".join(options[item] for item in response.option_ids)
    fields = {item.field_id: item.label for item in request.fields}
    rendered = []
    for value in response.values:
        if isinstance(value, TextFieldValue):
            public_value = value.text
        elif isinstance(value, IntegerFieldValue):
            public_value = str(value.integer)
        elif isinstance(value, DecimalFieldValue):
            public_value = value.decimal_string
        elif isinstance(value, BooleanFieldValue):
            public_value = "true" if value.boolean else "false"
        elif isinstance(value, DateFieldValue):
            public_value = value.iso_date
        else:  # pragma: no cover - InteractionResponse is a closed algebra
            raise TypeError("unsupported interaction field response")
        rendered.append(f"{fields[value.field_id]}: {public_value}")
    return "; ".join(rendered)


def _revision_feed_diff(
    before: TaskGoal,
    after: TaskGoal,
    source_id: str,
) -> PublicRevisionApplied:
    before_items = _public_goal_conditions(before)
    after_items = _public_goal_conditions(after)
    before_set = set(before_items)
    after_set = set(after_items)
    return PublicRevisionApplied(
        source_id,
        after.revision,
        before.instruction != after.instruction,
        tuple(item for item in after_items if item not in before_set),
        tuple(item for item in before_items if item not in after_set),
        tuple(item for item in after_items if item in before_set),
    )


def _public_goal_conditions(task: TaskGoal) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                *task.constraints,
                *(f"Allowed effect: {item}" for item in task.allowed_effects),
                *(f"Forbidden effect: {item}" for item in task.forbidden_effects),
                *(f"Requested output: {item}" for item in task.requested_outputs),
            )
        )
    )


def _step_feed_sources(
    result: StepResult,
) -> tuple[Callable[[str], PublicFeedSource], ...]:
    sources: list[Callable[[str], PublicFeedSource]] = []
    decision = result.decision
    intent = str(getattr(decision, "public_intent", "")).strip()
    if intent:
        sources.append(_feed_source(lambda source_id: PublicAgentIntent(source_id, intent)))

    if isinstance(decision, InteractionRequest):
        request = _public_interaction_request(decision)
        sources.append(_feed_source(lambda source_id: PublicInteractionRequested(source_id, request)))
        return tuple(sources)

    if result.confirmation is not None:
        confirmation = _public_confirmation(result.confirmation)
        sources.append(_feed_source(lambda source_id: PublicConfirmationRequired(source_id, confirmation)))
        return tuple(sources)

    if isinstance(decision, RequestObservation) and result.observation_outcome is not None:
        outcome = result.observation_outcome
        status = {
            ObservationQueryDisposition.OBSERVED: "observed",
            ObservationQueryDisposition.PARTIAL: "partial",
            ObservationQueryDisposition.UNKNOWN: "unknown",
            ObservationQueryDisposition.FAILED: "failed",
        }[outcome.disposition]
        message = {
            "observed": "Visual evidence was observed.",
            "partial": "Some visual evidence could not be confirmed.",
            "unknown": "The requested visual evidence could not be confirmed.",
            "failed": "Visual evidence acquisition failed.",
        }[status]
        refs = outcome.evidence_refs
        sources.append(
            _feed_source(
                lambda source_id: PublicEvidenceSummary(
                    source_id,
                    "visual",
                    cast(
                        Literal["observed", "partial", "unknown", "failed", "stale"],
                        status,
                    ),
                    message,
                    evidence_refs=refs,
                )
            )
        )
        return tuple(sources)

    if isinstance(decision, SelectAction):
        activity, evidence = _action_feed_sources(result)
        sources.append(activity)
        if evidence is not None:
            sources.append(evidence)
        return tuple(sources)

    if isinstance(decision, PolicyFailure):
        code = result.failure_code.value if result.failure_code is not None else decision.kind.value
        sources.append(
            _feed_source(
                lambda source_id: PublicFailure(
                    source_id,
                    code,
                    decision.reason,
                )
            )
        )
        return tuple(sources)

    kind = getattr(getattr(decision, "kind", None), "value", "")
    labels = {
        "request_action_page": "Updated the available interface actions.",
        "read_region": "Read more of the current interface.",
        "search_page_content": "Searched the current interface content.",
        "wait": "Waited for the interface to update.",
    }
    if kind in labels:
        label = labels[kind]
        sources.append(
            _feed_source(
                lambda source_id: PublicRuntimeActivity(
                    source_id,
                    "completed",
                    label,
                )
            )
        )
    return tuple(sources)


def _action_feed_sources(
    result: StepResult,
) -> tuple[
    Callable[[str], PublicFeedSource],
    Callable[[str], PublicFeedSource] | None,
]:
    outcome = result.action_outcome
    if outcome is not None:
        activity_status, message = {
            LocalPostconditionStatus.SATISFIED: (
                "completed",
                "The interface change was confirmed.",
            ),
            LocalPostconditionStatus.UNSATISFIED: (
                "failed",
                "The requested interface change was not confirmed.",
            ),
            LocalPostconditionStatus.UNKNOWN: (
                "uncertain",
                "The interface action finished, but its effect could not be confirmed.",
            ),
            LocalPostconditionStatus.NOT_APPLICABLE: (
                "completed",
                "The interface action was completed.",
            ),
        }[outcome.local_postcondition]
        refs = outcome.evidence_refs

        def activity(source_id: str) -> PublicFeedSource:
            return PublicRuntimeActivity(
                source_id,
                cast(Literal["started", "completed", "uncertain", "failed"], activity_status),
                message,
                refs,
            )

        if not refs:
            return activity, None
        evidence_kind = {
            EvidenceMethod.STRUCTURAL: "structural",
            EvidenceMethod.VISUAL_DIFF: "frame_change",
            EvidenceMethod.NATIVE: "structural",
            EvidenceMethod.NONE: "unknown",
        }[outcome.evidence_method]
        evidence_status = "unknown" if outcome.local_postcondition is LocalPostconditionStatus.UNKNOWN else "observed"

        def evidence(source_id: str) -> PublicFeedSource:
            return PublicEvidenceSummary(
                source_id,
                cast(
                    Literal["structural", "visual", "frame_change", "mixed", "unknown"],
                    evidence_kind,
                ),
                cast(Literal["observed", "partial", "unknown", "failed", "stale"], evidence_status),
                (
                    "The visible frame changed; its meaning was not semantically interpreted."
                    if evidence_kind == "frame_change"
                    else "Evidence was recorded for the interface action."
                ),
                evidence_refs=refs,
            )

        return activity, evidence

    completion = result.execution_receipts.completion if result.execution_receipts is not None else None
    status, label = {
        ExecutionCompletion.COMPLETE: ("completed", "The interface action was completed."),
        ExecutionCompletion.PARTIAL: ("uncertain", "The interface action completed only partially."),
        ExecutionCompletion.UNKNOWN: ("uncertain", "The interface action result is uncertain."),
        ExecutionCompletion.CANCELLED: ("failed", "The interface action was cancelled."),
        None: ("failed", "The interface action was not executed."),
    }[completion]
    return (
        lambda source_id: PublicRuntimeActivity(
            source_id,
            status,  # type: ignore[arg-type]
            label,
        ),
        None,
    )


def _control_feed_sources(
    event_type: str,
    outcome: PublicControlOutcome | None,
) -> tuple[Callable[[str], PublicFeedSource], ...]:
    status, label = {
        "RUN_STARTED": ("started", "Runtime is continuing the task."),
        "CONTROL_REQUESTED": ("started", "A control change was requested."),
        "RUN_PAUSED": ("completed", "The task is paused."),
        "RUN_RESUMED": ("started", "The task resumed."),
        "USER_CONTROL_GRANTED": ("completed", "Control was handed to you."),
        "USER_CONTROL_REVOKED": ("started", "User control was returned for a fresh check."),
        "USER_CONTROL_RETURNED": ("completed", "The Agent has control again."),
        "USER_CONTROL_RETURN_FAILED": (
            "failed",
            "Control could not be returned because currentness was unavailable.",
        ),
        "CONTROL_FAILED": ("failed", "The requested control change failed."),
    }.get(event_type, ("", ""))
    if not status:
        return ()
    if outcome is not None and outcome.message:
        label = outcome.message
    return (
        lambda source_id: PublicRuntimeActivity(
            source_id,
            status,  # type: ignore[arg-type]
            label,
        ),
    )


def _public_status(status: RunStatus) -> PublicSessionStatus:
    return {
        RunStatus.RUNNING: PublicSessionStatus.RUNNING,
        RunStatus.PAUSED: PublicSessionStatus.PAUSED,
        RunStatus.WAITING_USER: PublicSessionStatus.WAITING_USER,
        RunStatus.WAITING_CONFIRMATION: PublicSessionStatus.WAITING_CONFIRMATION,
        RunStatus.DONE: PublicSessionStatus.DONE,
        RunStatus.BLOCKED: PublicSessionStatus.BLOCKED,
        RunStatus.CANCELLED: PublicSessionStatus.CANCELLED,
        RunStatus.FAILED: PublicSessionStatus.FAILED,
    }[status]


def _completion(state: RunState | None, status: PublicSessionStatus) -> PublicCompletion | None:
    if state is None or status not in {
        PublicSessionStatus.DONE,
        PublicSessionStatus.BLOCKED,
        PublicSessionStatus.CANCELLED,
        PublicSessionStatus.FAILED,
    }:
        return None
    if status is PublicSessionStatus.CANCELLED:
        return PublicCompletion(
            "cancelled",
            "user_cancelled",
            "Runtime cancelled the task at a safe execution boundary.",
        )
    evaluation = state.current_task_evaluation
    outcome = evaluation.outcome if evaluation is not None else None
    if evaluation is not None and outcome is not None and outcome.kind is TaskOutcomeKind.TERMINAL_SUCCESS:
        last_decision = state.last_step.decision if state.last_step is not None else None
        message = last_decision.content if isinstance(last_decision, FinalResponse) else evaluation.reason
        artifact = state.last_step.public_artifact if state.last_step is not None else None
        return PublicCompletion("success", outcome.code, message, outcome.evidence_refs, artifact)
    if evaluation is not None and outcome is not None and outcome.kind is TaskOutcomeKind.TERMINAL_FAILURE:
        return PublicCompletion("failure", outcome.code, evaluation.reason, outcome.evidence_refs)
    failure = state.runtime_failure
    if failure is not None:
        return PublicCompletion("failure", failure.code, "Runtime could not complete the task.")
    control = state.control_termination
    if control is not None:
        return PublicCompletion("blocked", str(control.kind), "Runtime stopped before completion.")
    return PublicCompletion(
        "blocked",
        "runtime_blocked",
        "The task stopped before completion.",
    )

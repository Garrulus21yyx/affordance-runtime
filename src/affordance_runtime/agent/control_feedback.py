"""Closed control-feedback algebra and bounded repair/no-gain policy."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.public_semantic_digest import (
    issue_digest as make_issue_digest,
)
from affordance_runtime.world.public_semantic_digest import (
    public_action_contract_digest,
    public_subject_semantics,
    public_world_semantic_digest,
    semantic_scope_digest,
    task_progress_fingerprint,
)

if TYPE_CHECKING:
    from affordance_runtime.agent.decisions import SelectAction
    from affordance_runtime.agent.state import AgentLoopState
    from affordance_runtime.task.frontier import ObjectiveAdmissionIssue
    from affordance_runtime.task.frontier_contracts import ObjectiveOperation
    from affordance_runtime.world.action_paging import InternalActionPage
    from affordance_runtime.world.admission_issue import AdmissionIssue
    from affordance_runtime.world.contracts import ActionSpace


class ControlFeedbackKind(StrEnum):
    REPAIRABLE_REJECTION = "repairable_rejection"
    NO_INFORMATION_GAIN = "no_information_gain"
    STRATEGY_TRANSITION_REQUIRED = "strategy_transition_required"


class ControlFeedbackSource(StrEnum):
    OBJECTIVE_ADMISSION = "objective_admission"
    ACTION_ADMISSION = "action_admission"
    ACTION_PAGE = "action_page"
    POLICY_OBSERVATION = "policy_observation"
    ACTION_EVALUATION = "action_evaluation"
    PROGRESS_EVENT = "progress_event"


class NextDecisionDisposition(StrEnum):
    CORRECT_OR_REPLAN = "correct_or_replan"
    CHANGE_STRATEGY = "change_strategy"


_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_PUBLIC_PATHS = frozenset({
    "action_id",
    "actions",
    "destination_id",
    "observation",
    "parameters",
    "parameters.value",
    "objective_operation.active_objective_id",
    "objective_operation.intended_requirement_ids",
    "objective_operation.kind",
    "objective_operation.predicate.expected.fact_ref",
    "objective_operation.predicate.target_id",
    "objective_operation.replaces_objective_id",
})
_PUBLIC_PATH = re.compile(
    r"parameters(?:\.[A-Za-z][A-Za-z0-9_-]{0,63})*|action_id|actions|destination_id|observation|objective_operation(?:\.[A-Za-z][A-Za-z0-9_-]{0,63})*"
)
_PRIVATE_PARTS = frozenset({
    "password", "secret", "token", "credential", "authorization", "api", "key",
    "selector", "coordinate", "bbox", "point", "href", "method", "backend", "executor",
})


@dataclass(frozen=True)
class RelatedDecisionSnapshot:
    kind: str
    action_id: str = ""
    target_id: str = ""
    destination_id: str = ""
    parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind != "select_action":
            raise ValueError("related decision snapshot kind is unsupported")
        if not self.action_id or len(self.action_id) > 240:
            raise ValueError("related decision requires a bounded action id")
        object.__setattr__(self, "parameters", freeze_json(self.parameters or {}))


@dataclass(frozen=True)
class RelatedObjectiveOperationSnapshot:
    kind: str
    active_objective_id: str = ""
    replaces_objective_id: str = ""
    intended_requirement_ids: tuple[str, ...] = ()
    predicate: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in {"none", "propose", "retain", "replace"}:
            raise ValueError("related objective operation kind is unsupported")
        object.__setattr__(
            self, "intended_requirement_ids", tuple(self.intended_requirement_ids),
        )
        object.__setattr__(self, "predicate", freeze_json(self.predicate))


@dataclass(frozen=True)
class ContractViolationSnapshot:
    contract_owner: str
    code: str
    field_paths: tuple[str, ...]
    expected: Mapping[str, object]
    actual: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.contract_owner not in {
            "current_action_page", "current_action_space", "task_frontier",
        }:
            raise ValueError("feedback violation owner is unsupported")
        if _CODE.fullmatch(self.code) is None:
            raise ValueError("feedback violation code is invalid")
        paths = tuple(sorted(set(self.field_paths)))
        if not paths or any(not _public_path(path) for path in paths):
            raise ValueError("feedback violation paths are invalid")
        object.__setattr__(self, "field_paths", paths)
        object.__setattr__(self, "expected", freeze_json(self.expected))
        object.__setattr__(self, "actual", freeze_json(self.actual))


@dataclass(frozen=True)
class SemanticEffectSnapshot:
    dispatch: str
    expected_effects: tuple[str, ...]
    observed_effect: str
    world_changed: bool
    action_space_changed: bool
    task_progress_changed: bool
    changed_public_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.dispatch not in {"not_sent", "sent", "sent_unknown"}:
            raise ValueError("semantic effect dispatch is unsupported")
        if self.observed_effect not in {
            "effect_confirmed", "no_effect_confirmed", "unknown", "rejected"
        }:
            raise ValueError("observed semantic effect is unsupported")
        for value in (self.world_changed, self.action_space_changed, self.task_progress_changed):
            if type(value) is not bool:
                raise TypeError("semantic effect delta flags must be boolean")
        object.__setattr__(self, "expected_effects", tuple(self.expected_effects))
        object.__setattr__(self, "changed_public_fields", tuple(self.changed_public_fields))


@dataclass(frozen=True)
class RecoveryConstraints:
    must_change_fields: tuple[str, ...] = ()
    repeat_previous_decision_allowed: bool = False
    retry_allowed: bool = False
    rollback_available: bool = False
    strategy_change_required: bool = False
    offered_action_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(not _public_path(path) for path in self.must_change_fields):
            raise ValueError("recovery change fields are invalid")
        flags = (
            self.repeat_previous_decision_allowed,
            self.retry_allowed,
            self.rollback_available,
            self.strategy_change_required,
        )
        if any(type(value) is not bool for value in flags):
            raise TypeError("recovery flags must be boolean")
        object.__setattr__(self, "must_change_fields", tuple(self.must_change_fields))
        object.__setattr__(self, "offered_action_ids", tuple(self.offered_action_ids[:32]))


@dataclass(frozen=True)
class ControlFeedback:
    kind: ControlFeedbackKind
    code: str
    source: ControlFeedbackSource
    next_decision_disposition: NextDecisionDisposition
    strategy_transition_required: bool
    public_subject_id: str | None = None
    public_field_paths: tuple[str, ...] = ()
    scope_digest: str = ""
    issue_digest: str = ""
    request_digest: str = ""
    result_digest: str = ""
    related_decision: RelatedDecisionSnapshot | None = None
    related_objective_operation: RelatedObjectiveOperationSnapshot | None = None
    violation: ContractViolationSnapshot | None = None
    semantic_effect: SemanticEffectSnapshot | None = None
    recovery: RecoveryConstraints | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ControlFeedbackKind):
            raise TypeError("control feedback kind must be typed")
        if not isinstance(self.source, ControlFeedbackSource):
            raise TypeError("control feedback source must be typed")
        if not isinstance(self.next_decision_disposition, NextDecisionDisposition):
            raise TypeError("control feedback disposition must be typed")
        if type(self.strategy_transition_required) is not bool:
            raise TypeError("strategy-transition flag must be exact bool")
        if not isinstance(self.code, str) or _CODE.fullmatch(self.code) is None:
            raise ValueError("control feedback code must be a bounded identifier")
        if self.public_subject_id is not None and (
            not isinstance(self.public_subject_id, str)
            or not self.public_subject_id.strip()
            or len(self.public_subject_id) > 240
        ):
            raise ValueError("public feedback subject is invalid")
        paths = tuple(sorted(set(self.public_field_paths)))
        if len(paths) > 6 or any(not _public_path(path) for path in paths):
            raise ValueError("control feedback field paths are not public and bounded")
        object.__setattr__(self, "public_field_paths", paths)
        for value in (self.scope_digest, self.issue_digest):
            if _DIGEST.fullmatch(value) is None:
                raise ValueError("control feedback requires canonical internal digests")
        for value in (self.request_digest, self.result_digest):
            if value and _DIGEST.fullmatch(value) is None:
                raise ValueError("control feedback request/result digest is invalid")
        self._validate_matrix()

    @property
    def consumes_issue_budget(self) -> bool:
        return self.kind is not ControlFeedbackKind.STRATEGY_TRANSITION_REQUIRED

    def _validate_matrix(self) -> None:
        expected = {
            ControlFeedbackKind.REPAIRABLE_REJECTION: (
                frozenset({
                    ControlFeedbackSource.ACTION_ADMISSION,
                    ControlFeedbackSource.OBJECTIVE_ADMISSION,
                }),
                NextDecisionDisposition.CORRECT_OR_REPLAN,
                False,
                False,
            ),
            ControlFeedbackKind.NO_INFORMATION_GAIN: (
                frozenset({
                    ControlFeedbackSource.ACTION_PAGE,
                    ControlFeedbackSource.POLICY_OBSERVATION,
                }),
                NextDecisionDisposition.CHANGE_STRATEGY,
                True,
                True,
            ),
            ControlFeedbackKind.STRATEGY_TRANSITION_REQUIRED: (
                frozenset({
                    ControlFeedbackSource.ACTION_EVALUATION,
                    ControlFeedbackSource.PROGRESS_EVENT,
                }),
                NextDecisionDisposition.CHANGE_STRATEGY,
                True,
                False,
            ),
        }[self.kind]
        sources, disposition, transition, requires_result = expected
        if (
            self.source not in sources
            or self.next_decision_disposition is not disposition
            or self.strategy_transition_required is not transition
            or (requires_result and (not self.request_digest or not self.result_digest))
            or (self.kind is not ControlFeedbackKind.NO_INFORMATION_GAIN and (
                self.request_digest or self.result_digest
            ))
        ):
            raise ValueError("control feedback kind/source/disposition matrix is invalid")
        if self.kind is ControlFeedbackKind.REPAIRABLE_REJECTION and (
            (self.related_decision is None and self.related_objective_operation is None)
            or self.violation is None
            or self.recovery is None
            or self.semantic_effect is not None
        ):
            raise ValueError("repairable rejection requires decision, violation, and recovery snapshots")
        if (
            self.source is ControlFeedbackSource.OBJECTIVE_ADMISSION
            and self.code == "objective_already_satisfied"
            and (
                self.recovery is None
                or self.recovery.must_change_fields != ("objective_operation.predicate",)
                or self.recovery.retry_allowed
                or not self.recovery.strategy_change_required
            )
        ):
            raise ValueError("already-satisfied objective feedback must require predicate replacement")
        if self.kind is ControlFeedbackKind.NO_INFORMATION_GAIN and self.recovery is None:
            raise ValueError("no-information-gain feedback requires recovery constraints")
        if self.kind is ControlFeedbackKind.STRATEGY_TRANSITION_REQUIRED and (
            self.source is ControlFeedbackSource.ACTION_EVALUATION
            and (self.related_decision is None or self.semantic_effect is None or self.recovery is None)
        ):
            raise ValueError("action-effect feedback requires decision, effect, and recovery snapshots")


def objective_repair_feedback(
    state: AgentLoopState,
    action_space: ActionSpace,
    page: InternalActionPage,
    *,
    decision: SelectAction | None,
    operation: ObjectiveOperation,
    issue: ObjectiveAdmissionIssue,
) -> ControlFeedback:
    from affordance_runtime.task.frontier_contracts import (
        ProposeObjective,
        ReplaceObjective,
        RetainObjective,
        predicate_public_value,
    )

    scope = current_semantic_scope(state, action_space, page)
    proposal = operation if isinstance(operation, ProposeObjective | ReplaceObjective) else None
    predicate = predicate_public_value(proposal.predicate) if proposal is not None else {}
    digest = make_issue_digest(
        scope_digest=scope,
        kind=ControlFeedbackKind.REPAIRABLE_REJECTION.value,
        source=ControlFeedbackSource.OBJECTIVE_ADMISSION.value,
        code=issue.code.value,
        subject_semantics=predicate,
        public_field_paths=issue.field_paths,
    )
    already_satisfied = issue.code.value == "objective_already_satisfied"
    option = action_space.find(decision.action_id) if decision is not None else None
    return ControlFeedback(
        ControlFeedbackKind.REPAIRABLE_REJECTION,
        issue.code.value,
        ControlFeedbackSource.OBJECTIVE_ADMISSION,
        NextDecisionDisposition.CORRECT_OR_REPLAN,
        False,
        public_field_paths=issue.field_paths,
        scope_digest=scope,
        issue_digest=digest,
        related_objective_operation=RelatedObjectiveOperationSnapshot(
            operation.kind.value,
            operation.active_objective_id
            if isinstance(operation, RetainObjective)
            else "",
            operation.replaces_objective_id
            if isinstance(operation, ReplaceObjective)
            else "",
            proposal.intended_requirement_ids if proposal is not None else (),
            predicate,
        ),
        related_decision=(
            _selection_snapshot(decision, option.target_id if option is not None else None)
            if decision is not None
            else None
        ),
        violation=ContractViolationSnapshot(
            "task_frontier",
            issue.code.value,
            issue.field_paths,
            issue.expected,
            issue.actual,
        ),
        recovery=RecoveryConstraints(
            must_change_fields=issue.field_paths,
            repeat_previous_decision_allowed=False,
            retry_allowed=not already_satisfied,
            strategy_change_required=already_satisfied,
            offered_action_ids=page.visible_action_ids,
        ),
    )


class FeedbackBudgetDisposition(StrEnum):
    DELIVER = "deliver"
    TERMINATE = "terminate"
    STRATEGY = "strategy"


@dataclass(frozen=True)
class FeedbackBudgetDecision:
    disposition: FeedbackBudgetDisposition
    issue_digests: tuple[str, ...]


def apply_feedback_budget(
    current_scope_digest: str,
    consumed_issue_digests: tuple[str, ...],
    feedback: ControlFeedback,
) -> FeedbackBudgetDecision:
    """Apply the frozen two-distinct-issue budget without reconstructing history."""

    if feedback.kind is ControlFeedbackKind.STRATEGY_TRANSITION_REQUIRED:
        return FeedbackBudgetDecision(FeedbackBudgetDisposition.STRATEGY, consumed_issue_digests)
    prior = consumed_issue_digests if current_scope_digest == feedback.scope_digest else ()
    if feedback.issue_digest in prior or len(prior) >= 2:
        return FeedbackBudgetDecision(FeedbackBudgetDisposition.TERMINATE, prior)
    updated = (*prior, feedback.issue_digest)
    return FeedbackBudgetDecision(FeedbackBudgetDisposition.DELIVER, updated)


def current_semantic_scope(
    state: AgentLoopState,
    action_space: ActionSpace,
    page: InternalActionPage | None = None,
) -> str:
    """Return the control epoch; ``page`` is compatibility-only and ignored."""

    return semantic_scope_digest(
        state.task_revision,
        public_world_semantic_digest(state.current_observation),
        public_action_contract_digest(state.current_observation, action_space),
        task_progress_fingerprint(state.current_task_evaluation),
    )


def repair_feedback(
    state: AgentLoopState,
    action_space: ActionSpace,
    page: InternalActionPage,
    *,
    decision: SelectAction,
    issue: AdmissionIssue,
    public_subject_id: str | None = None,
) -> ControlFeedback:
    scope = current_semantic_scope(state, action_space, page)
    subject = public_subject_semantics(
        state.current_observation, public_subject_id or "",
    )
    digest = make_issue_digest(
        scope_digest=scope,
        kind=ControlFeedbackKind.REPAIRABLE_REJECTION.value,
        source=ControlFeedbackSource.ACTION_ADMISSION.value,
        code=issue.code.value,
        subject_semantics=subject,
        public_field_paths=issue.public_field_paths,
    )
    return ControlFeedback(
        ControlFeedbackKind.REPAIRABLE_REJECTION,
        issue.code.value,
        ControlFeedbackSource.ACTION_ADMISSION,
        NextDecisionDisposition.CORRECT_OR_REPLAN,
        False,
        public_subject_id,
        issue.public_field_paths,
        scope,
        digest,
        related_decision=_selection_snapshot(
            decision, public_subject_id, issue.public_field_paths,
        ),
        violation=ContractViolationSnapshot(
            issue.contract_owner.value,
            issue.code.value,
            issue.public_field_paths,
            issue.expected,
            issue.actual,
        ),
        recovery=RecoveryConstraints(
            must_change_fields=issue.public_field_paths,
            repeat_previous_decision_allowed=False,
            retry_allowed=True,
            offered_action_ids=page.visible_action_ids,
        ),
    )


def no_gain_feedback(
    state: AgentLoopState,
    action_space: ActionSpace,
    page: InternalActionPage,
    *,
    source: ControlFeedbackSource,
    code: str,
    request_digest: str,
    result_digest: str,
    public_subject_id: str | None = None,
    public_field_paths: tuple[str, ...] = (),
) -> ControlFeedback:
    scope = current_semantic_scope(state, action_space, page)
    subject = public_subject_semantics(
        state.current_observation, public_subject_id or "",
    )
    digest = make_issue_digest(
        scope_digest=scope,
        kind=ControlFeedbackKind.NO_INFORMATION_GAIN.value,
        source=source.value,
        code=code,
        subject_semantics=subject,
        public_field_paths=public_field_paths,
        request_digest=request_digest,
        result_digest=result_digest,
    )
    return ControlFeedback(
        ControlFeedbackKind.NO_INFORMATION_GAIN,
        code,
        source,
        NextDecisionDisposition.CHANGE_STRATEGY,
        True,
        public_subject_id,
        public_field_paths,
        scope,
        digest,
        request_digest,
        result_digest,
        recovery=RecoveryConstraints(
            repeat_previous_decision_allowed=False,
            retry_allowed=False,
            rollback_available=False,
            strategy_change_required=True,
            offered_action_ids=page.visible_action_ids,
        ),
    )


def strategy_feedback(
    state: AgentLoopState,
    action_space: ActionSpace,
    page: InternalActionPage,
    *,
    source: ControlFeedbackSource,
    code: str,
    public_subject_id: str | None = None,
    related_decision: RelatedDecisionSnapshot | None = None,
    semantic_effect: SemanticEffectSnapshot | None = None,
    recovery: RecoveryConstraints | None = None,
) -> ControlFeedback:
    scope = current_semantic_scope(state, action_space, page)
    subject = public_subject_semantics(
        state.current_observation, public_subject_id or "",
    )
    digest = make_issue_digest(
        scope_digest=scope,
        kind=ControlFeedbackKind.STRATEGY_TRANSITION_REQUIRED.value,
        source=source.value,
        code=code,
        subject_semantics=subject,
        public_field_paths=(),
    )
    return ControlFeedback(
        ControlFeedbackKind.STRATEGY_TRANSITION_REQUIRED,
        code,
        source,
        NextDecisionDisposition.CHANGE_STRATEGY,
        True,
        public_subject_id,
        (),
        scope,
        digest,
        related_decision=related_decision,
        semantic_effect=semantic_effect,
        recovery=recovery,
    )


def selection_snapshot(
    decision: SelectAction,
    public_subject_id: str | None = None,
) -> RelatedDecisionSnapshot:
    return _selection_snapshot(decision, public_subject_id)


def _selection_snapshot(
    decision: SelectAction,
    public_subject_id: str | None,
    redact_fields: tuple[str, ...] = (),
) -> RelatedDecisionSnapshot:
    return RelatedDecisionSnapshot(
        "select_action",
        decision.action_id,
        public_subject_id or "",
        decision.destination_id,
        _safe_parameters(decision.parameters, redact_fields),
    )


def _safe_parameters(
    value: Mapping[str, object],
    redact_fields: tuple[str, ...] = (),
) -> Mapping[str, object]:
    result: dict[str, object] = {}
    redact_all = "parameters" in redact_fields
    redacted_names = {
        path.removeprefix("parameters.")
        for path in redact_fields
        if path.startswith("parameters.")
    }
    for key, item in list(value.items())[:12]:
        name = str(key)
        parts = {part.casefold() for part in re.split(r"[_-]", name)}
        if redact_all or name in redacted_names or parts & _PRIVATE_PARTS:
            result[name] = "[REDACTED]"
        elif isinstance(item, str):
            result[name] = item[:240]
        elif item is None or isinstance(item, bool | int | float):
            result[name] = item
        else:
            result[name] = "[STRUCTURED]"
    return result


def _public_path(path: str) -> bool:
    if path in _PUBLIC_PATHS:
        return True
    if _PUBLIC_PATH.fullmatch(path) is None:
        return False
    parts = {part.casefold() for part in re.split(r"[._-]", path)}
    return not bool(parts & _PRIVATE_PARTS)


def route_feedback(state, scope, feedback: ControlFeedback):
    """Record one source fact and apply the bounded policy to authoritative state."""

    from affordance_runtime.agent.control_outcome import Continue, Terminate
    from affordance_runtime.agent.result_code import AgentFailureCode
    from affordance_runtime.agent.state import AgentLoopStatus

    decision = apply_feedback_budget(
        state.control_feedback_scope_digest,
        state.consumed_control_issue_digests,
        feedback,
    )
    scope.record_control_feedback(feedback)
    if decision.disposition is FeedbackBudgetDisposition.TERMINATE:
        state.record_control_repetition()
        scope.set_reason("no_progress_control_repetition")
        return Terminate(
            AgentLoopStatus.BLOCKED,
            "no_progress_control_repetition",
            "bounded control feedback was exhausted",
            failure_code=AgentFailureCode.NO_PROGRESS_CONTROL_REPETITION,
        )
    state.install_control_feedback(feedback, decision.issue_digests)
    return Continue(feedback.code)

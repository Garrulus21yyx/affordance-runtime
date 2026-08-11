"""Closed control-feedback algebra and bounded repair/no-gain policy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from affordance_runtime.world.public_semantic_digest import (
    issue_digest as make_issue_digest,
)
from affordance_runtime.world.public_semantic_digest import (
    public_action_page_digest,
    public_subject_semantics,
    public_world_semantic_digest,
    semantic_scope_digest,
    task_progress_fingerprint,
)

if TYPE_CHECKING:
    from affordance_runtime.agent.state import AgentLoopState
    from affordance_runtime.world.action_paging import InternalActionPage
    from affordance_runtime.world.contracts import ActionSpace


class ControlFeedbackKind(StrEnum):
    REPAIRABLE_REJECTION = "repairable_rejection"
    NO_INFORMATION_GAIN = "no_information_gain"
    STRATEGY_TRANSITION_REQUIRED = "strategy_transition_required"


class ControlFeedbackSource(StrEnum):
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
})


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
        if len(paths) > 6 or any(path not in _PUBLIC_PATHS for path in paths):
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
                frozenset({ControlFeedbackSource.ACTION_ADMISSION}),
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
    page: InternalActionPage,
) -> str:
    return semantic_scope_digest(
        state.task_revision,
        public_world_semantic_digest(state.current_observation),
        public_action_page_digest(state.current_observation, action_space, page),
        task_progress_fingerprint(state.current_task_evaluation),
    )


def repair_feedback(
    state: AgentLoopState,
    action_space: ActionSpace,
    page: InternalActionPage,
    *,
    code: str,
    public_field_paths: tuple[str, ...],
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
        code=code,
        subject_semantics=subject,
        public_field_paths=public_field_paths,
    )
    return ControlFeedback(
        ControlFeedbackKind.REPAIRABLE_REJECTION,
        code,
        ControlFeedbackSource.ACTION_ADMISSION,
        NextDecisionDisposition.CORRECT_OR_REPLAN,
        False,
        public_subject_id,
        public_field_paths,
        scope,
        digest,
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
    )


def strategy_feedback(
    state: AgentLoopState,
    action_space: ActionSpace,
    page: InternalActionPage,
    *,
    source: ControlFeedbackSource,
    code: str,
    public_subject_id: str | None = None,
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
    )


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

"""Pure orchestration for Runtime-owned 0/1/N semantic action choice."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.action_choice_catalog import (
    ActionChoiceCatalog,
    ActionChoiceCatalogBuilder,
)
from affordance_runtime.action_selection import ActionSelectionValidator
from affordance_runtime.active_step_scope import ActiveStepScope
from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.choice_contracts import (
    ActionChoiceFailure,
    ActionSelection,
    AskUser,
    ChoiceOutcomeSummary,
    ChoicePage,
    ChoicePlannerResponse,
    ChoicePlanningBudget,
    ChoicePlanningRequest,
    DeferChoice,
    ReportPlanIssue,
    RequestNextChoicePage,
    SelectChoice,
)
from affordance_runtime.choice_presentation import ChoicePresentationProjector
from affordance_runtime.simplified_runtime_contracts import StepActivityStatus, StepSpec
from affordance_runtime.step_choice_planner import StepChoicePlanner
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.unified_observation import UnifiedObservation


class StepChoiceFlowKind(StrEnum):
    SELECTED = "selected"
    ASK_USER = "ask_user"
    DEFER = "defer"
    PLAN_ISSUE = "plan_issue"
    FAILED = "failed"


@dataclass(frozen=True)
class StepChoiceFlowResult:
    kind: StepChoiceFlowKind
    catalog: ActionChoiceCatalog | None = None
    page: ChoicePage | None = None
    selection: ActionSelection | None = None
    response: ChoicePlannerResponse | None = None
    failure_reason: str = ""
    selection_source: str = ""


@dataclass(frozen=True)
class StepChoiceFlow:
    planner: StepChoicePlanner | None
    catalog_builder: ActionChoiceCatalogBuilder = field(default_factory=ActionChoiceCatalogBuilder)
    presentation_projector: ChoicePresentationProjector = field(default_factory=ChoicePresentationProjector)
    selection_validator: ActionSelectionValidator = field(default_factory=ActionSelectionValidator)
    paging_enabled: bool = False

    def choose(
        self,
        *,
        task_spec: TaskSpec,
        plan_revision: int,
        state_version: int,
        step: StepSpec,
        observation: UnifiedObservation,
        capabilities: frozenset[str],
        recent_outcomes: tuple[ChoiceOutcomeSummary, ...] = (),
        budget: ChoicePlanningBudget = ChoicePlanningBudget(),
    ) -> StepChoiceFlowResult:
        scope = ActiveStepScope.from_active_step(
            task_revision=task_spec.revision,
            evaluated_at_state_version=state_version,
            snapshot_id=observation.epoch_id,
            step=step,
            activity_status=StepActivityStatus.ACTIVE,
        )
        catalog_or_failure = self.catalog_builder.build(
            task_revision=task_spec.revision,
            task_spec=task_spec,
            plan_revision=plan_revision,
            state_version=state_version,
            step=step,
            scope=scope,
            observation=observation,
            capabilities=capabilities,
        )
        if isinstance(catalog_or_failure, ActionChoiceFailure):
            return StepChoiceFlowResult(
                StepChoiceFlowKind.FAILED,
                failure_reason=catalog_or_failure.reason_code,
            )
        catalog = catalog_or_failure
        if catalog.count == 1:
            return StepChoiceFlowResult(
                StepChoiceFlowKind.SELECTED,
                catalog=catalog,
                selection=self.selection_validator.select_unique(catalog),
                selection_source="runtime_unique_choice",
            )
        page = self.presentation_projector.project(catalog)
        if page.truncated and not self.paging_enabled:
            return StepChoiceFlowResult(
                StepChoiceFlowKind.FAILED,
                catalog=catalog,
                page=page,
                failure_reason="CHOICE_SPACE_TOO_LARGE",
            )
        if self.planner is None:
            return StepChoiceFlowResult(
                StepChoiceFlowKind.FAILED,
                catalog=catalog,
                page=page,
                failure_reason="step choice planner is not configured",
            )
        request = ChoicePlanningRequest(
            task_spec.revision,
            plan_revision,
            step.step_id,
            catalog.ref,
            page,
            recent_outcomes,
            budget,
        )
        response = self.planner.select(request)
        response = resolve_awaitable(response) if inspect.isawaitable(response) else response
        if isinstance(response, SelectChoice):
            return StepChoiceFlowResult(
                StepChoiceFlowKind.SELECTED,
                catalog=catalog,
                page=page,
                selection=self.selection_validator.validate(response, catalog, page),
                response=response,
                selection_source="step_choice_planner",
            )
        if isinstance(response, AskUser):
            return StepChoiceFlowResult(StepChoiceFlowKind.ASK_USER, catalog=catalog, page=page, response=response)
        if isinstance(response, DeferChoice):
            return StepChoiceFlowResult(StepChoiceFlowKind.DEFER, catalog=catalog, page=page, response=response)
        if isinstance(response, ReportPlanIssue):
            return StepChoiceFlowResult(
                StepChoiceFlowKind.PLAN_ISSUE,
                catalog=catalog,
                page=page,
                response=response,
            )
        if isinstance(response, RequestNextChoicePage):
            return StepChoiceFlowResult(
                StepChoiceFlowKind.FAILED,
                catalog=catalog,
                page=page,
                response=response,
                failure_reason=(
                    "choice paging is not enabled"
                    if not self.paging_enabled
                    else "choice paging requires another bounded planning turn"
                ),
            )
        return StepChoiceFlowResult(
            StepChoiceFlowKind.FAILED,
            catalog=catalog,
            page=page,
            response=response,
            failure_reason="unsupported closed choice decision",
        )


def recent_choice_outcomes(index: object) -> tuple[ChoiceOutcomeSummary, ...]:
    """Project the bounded Runtime outcome index into the choice horizon."""

    records = getattr(index, "records", ())
    return tuple(
        ChoiceOutcomeSummary(
            action_kind=item.key.action_kind,
            target_id=item.key.target_id,
            verification_passed=item.verification_passed,
            effect_satisfied=item.effect_satisfied,
        )
        for item in records[-8:]
    )

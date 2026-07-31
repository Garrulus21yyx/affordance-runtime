import asyncio
from dataclasses import dataclass, replace
from typing import Any, Sequence, TypeVar

import pytest
from pydantic import BaseModel, ValidationError

from affordance_runtime.action_choice import ActionChoice, ChoicePlanningRequest
from affordance_runtime.adapters.dom import AuthoredInteractiveExtension, DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot, _bounded_control_value
from affordance_runtime.compatibility_planner_algorithms import (
    _ascending_numeric_item_operation,
    _calendar_date_operation,
    _calendar_event_gesture_operation,
    _compiled_calendar_event_operation,
    _copy_text_constraints,
    _explicit_observed_color_operation,
    _explicit_observed_svg_item_operation,
    _explicit_point_target_operation,
    _forward_recipient_constraints,
    _hierarchical_target_operation,
    _ordinal_collection_operation,
    _owned_collection_action_operation,
    _partitioned_drag_operation,
    _quantity_order_operation,
    _remaining_requested_selection_values,
    _restrict_action_kinds_to_objective,
    _restrict_targets_to_objective,
    _scroll_progress_constraints,
    _slider_progress_constraints,
    _table_value_entry_constraints,
    _target_discovery_constraints,
)
from affordance_runtime.compatibility_planner_algorithms import (
    historical_compatibility_semantic_compiler_registry as default_semantic_compiler_registry,
)
from affordance_runtime.contracts import Observation
from affordance_runtime.generalist_planner import (
    COMPATIBILITY_PLANNER_PROMPT_VERSION,
    GENERALIST_PLANNER_PROMPT_VERSION,
    AffordanceSummary,
    GeneralistLMPlanner,
    GeneralistPlannerProfile,
    PlannerContext,
    PlannerProposalCandidate,
    _candidate_prebind_issue,
    _initial_candidate_schema,
    _repair_candidate_schema,
    _repair_constraints,
    build_planner_context,
)
from affordance_runtime.interaction_grounding import GroundingResult, GroundingStatus
from affordance_runtime.model_port import ModelCallRecord, ModelConfig, ModelMessage, StructuredModelError
from affordance_runtime.planner_context import _bounded_affordances, _compact_mapping
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.planning_contracts import PlannerProposalResponse, PlannerUnsupportedResponse
from affordance_runtime.planning_request import (
    PlannerAffordanceView,
    PlannerObservationView,
    PlannerStepProjectionStatus,
    PlannerStepView,
    PlannerTaskView,
    PlanningRequest,
    PlanningRequestIdentity,
    RuntimeBudgetView,
)
from affordance_runtime.planning_request_builder import PlanningRequestBuilder
from affordance_runtime.runtime import RunRequest
from affordance_runtime.semantic_compilers import SemanticCompilerRegistry
from affordance_runtime.semantics import CriterionRelation, EvidencePolicy, EvidenceStrength
from affordance_runtime.simplified_runtime_contracts import (
    ElementIntent,
    SourceReference,
    StateCriterion,
    StepActivityStatus,
    StepProgressView,
    StepSpec,
    TaskPlanView,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    EvidenceKind,
    EvidenceRequirement,
    OperationClass,
    SemanticValueConstraint,
    SemanticValueRelation,
    SourcedTaskClaim,
    TaskClaimKind,
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
    TaskObligationValueSource,
    TaskSpec,
)
from affordance_runtime.task_planning import (
    PlanProgress,
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanSource,
)
from affordance_runtime.unified_grounding import (
    CandidateDescriptor,
    SemanticEntityResolver,
    candidate_fingerprints,
    candidate_from_affordance,
)
from runtime_test_support import make_interaction

T = TypeVar("T", bound=BaseModel)


def _compatibility_planner(model: Any, **kwargs: Any) -> GeneralistLMPlanner:
    return GeneralistLMPlanner(
        model,
        planner_profile=GeneralistPlannerProfile.HISTORICAL_COMPATIBILITY,
        **kwargs,
    )


def _request_source() -> SourceReference:
    return SourceReference(source_id="source:user", source_unit_id="unit:1")


def _request_policy() -> EvidencePolicy:
    return EvidencePolicy(
        minimum_strength=EvidenceStrength.INDEPENDENT,
        allowed_source_kinds=("dom_state",),
    )


def _request_with_active_step(
    *,
    criterion: StateCriterion | tuple[StateCriterion, ...],
    affordance: PlannerAffordanceView | tuple[PlannerAffordanceView, ...],
    active_step_action_family: str = "",
    permitted_action_kinds: tuple[str, ...] = (
        PlannerActionKind.TYPE_TEXT.value,
        PlannerActionKind.PRESS_KEY.value,
    ),
) -> PlanningRequest:
    criteria = criterion if isinstance(criterion, tuple) else (criterion,)
    affordances = affordance if isinstance(affordance, tuple) else (affordance,)
    step = StepSpec(
        step_id="step:current",
        objective="Complete the current step",
        interaction=ElementIntent(
            getattr(criteria[0], "subject", "semantic:current"),
            (_request_source(),),
        ),
        completion_criteria=criteria,
        source_refs=(_request_source(),),
    )
    plan = TaskPlanView(
        plan_id="plan:1",
        plan_version=1,
        task_spec_identity="task:identity",
        task_revision=1,
        steps=(step,),
        active_step_id=step.step_id,
    )
    progress = StepProgressView(
        plan_id=plan.plan_id,
        plan_version=plan.plan_version,
        active_step_id=step.step_id,
        activity_status=StepActivityStatus.ACTIVE,
    )
    return PlanningRequest(
        identity=PlanningRequestIdentity(
            task_spec_identity="task:identity",
            task_revision=1,
            evaluated_at_state_version=7,
            snapshot_id="snapshot:1",
            page_revision="page:1",
            environment_revision="env:1",
        ),
        task=PlannerTaskView(
            task_spec_identity="task:identity",
            task_revision=1,
            objective="Complete the current step",
            constraints=(),
            capabilities=(),
            task_completion_criterion=None,
            task_completion_projection_status="pending",
        ),
        step=PlannerStepView(
            plan=plan,
            progress=progress,
            active_step=step,
            activity_status=StepActivityStatus.ACTIVE,
            projection_status=PlannerStepProjectionStatus.PROJECTED,
            active_step_action_family=active_step_action_family,
            compatibility_active_step_objective=step.objective,
        ),
        observation=PlannerObservationView(
            snapshot_id="snapshot:1",
            page_revision="page:1",
            environment_revision="env:1",
            observed_text="",
            affordances=affordances,
            artifact_refs=(),
        ),
        remaining_budget=RuntimeBudgetView(
            steps=3,
            observations=3,
            recoveries=1,
            effectful_actions=3,
            model_calls=1,
        ),
        permitted_action_kinds=permitted_action_kinds,
    )


def _request_without_active_step() -> PlanningRequest:
    return PlanningRequest(
        identity=PlanningRequestIdentity(
            task_spec_identity="task:identity",
            task_revision=1,
            evaluated_at_state_version=7,
            snapshot_id="snapshot:1",
            page_revision="page:1",
            environment_revision="env:1",
        ),
        task=PlannerTaskView(
            task_spec_identity="task:identity",
            task_revision=1,
            objective="Click the current target",
            constraints=(),
            capabilities=(),
            task_completion_criterion=None,
            task_completion_projection_status="pending",
        ),
        step=PlannerStepView(
            plan=None,
            progress=None,
            active_step=None,
            activity_status=StepActivityStatus.NO_PLAN,
            projection_status=PlannerStepProjectionStatus.NO_PLAN,
        ),
        observation=PlannerObservationView(
            snapshot_id="snapshot:1",
            page_revision="page:1",
            environment_revision="env:1",
            observed_text="",
            affordances=(
                PlannerAffordanceView(
                    target_id="semantic:target",
                    surface="dom",
                    role="button",
                    label="Target",
                    supported_actions=("activate",),
                    state={"enabled": True, "visible": True},
                ),
            ),
            artifact_refs=(),
        ),
        remaining_budget=RuntimeBudgetView(
            steps=3,
            observations=3,
            recoveries=1,
            effectful_actions=3,
            model_calls=1,
        ),
        permitted_action_kinds=(PlannerActionKind.ACTIVATE.value,),
    )


@dataclass
class NoCallModel:
    provider: str = "fixed"
    model: str = "no-call"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del messages, output_schema, config
        raise AssertionError("model should not be called for a unique runtime action choice")


def test_strict_planner_auto_selects_unique_exact_text_actionchoice() -> None:
    request = _request_with_active_step(
        criterion=StateCriterion(
            criterion_id="criterion:name",
            source_refs=(_request_source(),),
            subject="semantic:name",
            relation=CriterionRelation.EQUALS,
            expected_value="Alice",
            evidence_policy=_request_policy(),
        ),
        affordance=PlannerAffordanceView(
            target_id="semantic:name",
            surface="dom",
            role="textbox",
            label="Name",
            supported_actions=("type_text",),
            state={"value": ""},
        ),
    )
    planner = GeneralistLMPlanner(NoCallModel())

    response = asyncio.run(planner.propose(request))

    assert isinstance(response, PlannerProposalResponse)
    assert response.proposal.action_kind == PlannerActionKind.TYPE_TEXT
    assert response.proposal.target_affordance_id == "semantic:name"
    assert response.proposal.parameters == {"text": "Alice"}
    assert response.proposal.expected_effects == ("criterion:name",)
    assert response.proposal.evidence_requirements == ("dom_state",)
    assert response.proposal_provenance is not None
    assert response.proposal_provenance.producer_id == "runtime-action-choice"
    assert response.diagnostics.model_stage == "action_choice_build"
    assert response.diagnostics.action_choice_count == 1
    assert response.diagnostics.selection_source == "runtime_unique_choice"
    assert planner.model_call_count == 0


def test_strict_planner_auto_selects_unique_slider_actionchoice() -> None:
    request = _request_with_active_step(
        criterion=StateCriterion(
            criterion_id="criterion:slider",
            source_refs=(_request_source(),),
            subject="semantic:slider",
            relation=CriterionRelation.EQUALS,
            expected_value=7,
            evidence_policy=_request_policy(),
        ),
        affordance=PlannerAffordanceView(
            target_id="semantic:slider",
            surface="dom",
            role="slider",
            label="Volume",
            supported_actions=("press_key",),
            state={"value": 5},
        ),
    )
    planner = GeneralistLMPlanner(NoCallModel())

    response = asyncio.run(planner.propose(request))

    assert isinstance(response, PlannerProposalResponse)
    assert response.proposal.action_kind == PlannerActionKind.PRESS_KEY
    assert response.proposal.target_affordance_id == "semantic:slider"
    assert response.proposal.parameters == {"key": "ArrowRight"}
    assert response.proposal_provenance is not None
    assert response.proposal_provenance.producer_id == "runtime-action-choice"
    assert planner.model_call_count == 0


def test_strict_planner_returns_no_choice_failure_without_model_call() -> None:
    request = _request_with_active_step(
        criterion=StateCriterion(
            criterion_id="criterion:date",
            source_refs=(_request_source(),),
            subject="semantic:date",
            relation=CriterionRelation.EQUALS,
            expected_value="01/18/2019",
            evidence_policy=_request_policy(),
        ),
        affordance=PlannerAffordanceView(
            target_id="semantic:date",
            surface="dom",
            role="date",
            label="Date",
            supported_actions=("open_picker",),
            state={"value": ""},
        ),
    )
    planner = GeneralistLMPlanner(NoCallModel())

    response = asyncio.run(planner.propose(request))

    assert isinstance(response, PlannerUnsupportedResponse)
    assert response.reason_code == "no_feasible_action_choice"
    assert response.diagnostics.model_stage == "action_choice_build"
    assert response.diagnostics.action_choice_count == 0
    assert response.diagnostics.selection_source == "none"
    assert planner.model_call_count == 0


def test_strict_planner_without_active_step_returns_typed_failure_without_model_call() -> None:
    @dataclass
    class NoActiveStepModel:
        provider: str = "fixed"
        model: str = "strict-no-active-step"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self,
            messages: Sequence[ModelMessage],
            output_schema: type[T],
            config: ModelConfig,
        ) -> T:
            del messages, output_schema, config
            raise AssertionError("strict planner must not call model without active step")

    model = NoActiveStepModel()
    response = asyncio.run(GeneralistLMPlanner(model).propose(_request_without_active_step()))

    assert isinstance(response, PlannerUnsupportedResponse)
    assert response.reason_code == "no_active_step_action_choice"


def test_strict_planner_filters_ask_user_and_finish_before_model_schema() -> None:
    @dataclass
    class NoActionModel:
        provider: str = "fixed"
        model: str = "strict-no-action-authority"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self,
            messages: Sequence[ModelMessage],
            output_schema: type[T],
            config: ModelConfig,
        ) -> T:
            del messages, output_schema, config
            raise AssertionError("strict planner must not call model for finish/ask_user authority")

    request = replace(
        _request_without_active_step(),
        permitted_action_kinds=(
            PlannerActionKind.ASK_USER.value,
            PlannerActionKind.FINISH.value,
        ),
    )

    response = asyncio.run(GeneralistLMPlanner(NoActionModel()).propose(request))

    assert isinstance(response, PlannerUnsupportedResponse)
    assert response.reason_code == "no_active_step_action_choice"


def test_strict_planner_reports_typed_failure_when_choice_target_unresolved() -> None:
    @dataclass
    class ActivateModel:
        provider: str = "fixed"
        model: str = "legacy-fallback"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self,
            messages: Sequence[ModelMessage],
            output_schema: type[T],
            config: ModelConfig,
        ) -> T:
            del messages, config
            return output_schema.model_validate(
                {
                    "action_kind": "activate",
                    "target_affordance_id": "semantic:target",
                    "reason": "legacy compatibility target binding",
                }
            )

    request = _request_with_active_step(
        criterion=StateCriterion(
            criterion_id="criterion:legacy-target",
            source_refs=(_request_source(),),
            subject="target",
            relation=CriterionRelation.HAS_CHANGED,
            expected_value=None,
            evidence_policy=_request_policy(),
        ),
        affordance=PlannerAffordanceView(
            target_id="semantic:target",
            surface="dom",
            role="button",
            label="Different",
            supported_actions=("activate",),
            state={"enabled": True, "visible": True},
        ),
        active_step_action_family="activate",
        permitted_action_kinds=(PlannerActionKind.ACTIVATE.value,),
    )
    model = ActivateModel()
    planner = GeneralistLMPlanner(model)

    response = asyncio.run(planner.propose(request))

    assert isinstance(response, PlannerUnsupportedResponse)
    assert response.reason_code == "interaction_target_absent"
    assert planner.model_call_count == 0


def test_strict_planner_uses_one_typed_interaction_for_multiple_completion_criteria() -> None:
    @dataclass
    class ChoiceModel:
        provider: str = "fixed"
        model: str = "choice-selector"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None
        output_schema_fields: tuple[str, ...] = ()

        async def generate_structured(
            self,
            messages: Sequence[ModelMessage],
            output_schema: type[T],
            config: ModelConfig,
        ) -> T:
            del config
            self.output_schema_fields = tuple(output_schema.model_fields)
            assert "action_kind" not in self.output_schema_fields
            assert "target_affordance_id" not in self.output_schema_fields
            assert "parameters" not in self.output_schema_fields
            assert "expected_effects" not in self.output_schema_fields
            assert "evidence_requirements" not in self.output_schema_fields
            payload = __import__("json").loads(messages[1].content)
            return output_schema.model_validate(
                {"choice_id": payload["choices"][1]["choice_id"]}
            )

    request = _request_with_active_step(
        criterion=(
            StateCriterion(
                criterion_id="criterion:first",
                source_refs=(_request_source(),),
                subject="semantic:first",
                relation=CriterionRelation.EQUALS,
                expected_value="Alice",
                evidence_policy=_request_policy(),
            ),
            StateCriterion(
                criterion_id="criterion:second",
                source_refs=(_request_source(),),
                subject="semantic:second",
                relation=CriterionRelation.EQUALS,
                expected_value="Alice",
                evidence_policy=_request_policy(),
            ),
        ),
        affordance=(
            PlannerAffordanceView(
                target_id="semantic:first",
                surface="dom",
                role="textbox",
                label="First",
                supported_actions=("type_text",),
                state={"value": ""},
            ),
            PlannerAffordanceView(
                target_id="semantic:second",
                surface="dom",
                role="textbox",
                label="Second",
                supported_actions=("type_text",),
                state={"value": ""},
            ),
        ),
    )
    model = ChoiceModel()
    planner = GeneralistLMPlanner(model)

    response = asyncio.run(planner.propose(request))

    assert isinstance(response, PlannerProposalResponse)
    assert response.proposal.action_kind == PlannerActionKind.TYPE_TEXT
    assert response.proposal.target_affordance_id == "semantic:first"
    assert response.proposal.parameters == {"text": "Alice"}
    assert response.proposal_provenance is not None
    assert response.proposal_provenance.producer_id == "runtime-action-choice"
    assert planner.model_call_count == 0


def test_generalist_choice_selector_rejects_unknown_choice_id() -> None:
    @dataclass
    class UnknownChoiceModel:
        provider: str = "fixed"
        model: str = "choice-selector"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self,
            messages: Sequence[ModelMessage],
            output_schema: type[T],
            config: ModelConfig,
        ) -> T:
            del messages, config
            return output_schema.model_validate({"choice_id": "choice:missing"})

    choices = (
        ActionChoice(
            choice_id="choice:one",
            task_revision=1,
            state_version=7,
            snapshot_id="snapshot:1",
            active_step_id="step:current",
            action_kind=PlannerActionKind.TYPE_TEXT,
            target_id="semantic:first",
            parameters={"text": "Alice"},
            criterion_ids=("criterion:first",),
        ),
        ActionChoice(
            choice_id="choice:second",
            task_revision=1,
            state_version=7,
            snapshot_id="snapshot:1",
            active_step_id="step:current",
            action_kind=PlannerActionKind.TYPE_TEXT,
            target_id="semantic:second",
            parameters={"text": "Alice"},
            criterion_ids=("criterion:second",),
        ),
    )
    request = ChoicePlanningRequest(
        task_revision=1,
        state_version=7,
        snapshot_id="snapshot:1",
        active_step_id="step:current",
        grounding=GroundingResult(GroundingStatus.RESOLVED),
        choices=choices,
    )

    with pytest.raises(ValueError, match="unknown choice"):
        asyncio.run(GeneralistLMPlanner(UnknownChoiceModel()).select(request))


def test_strict_planner_returns_typed_failure_for_unknown_actionchoice_selection() -> None:
    @dataclass
    class UnknownChoiceModel:
        provider: str = "fixed"
        model: str = "choice-selector"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self,
            messages: Sequence[ModelMessage],
            output_schema: type[T],
            config: ModelConfig,
        ) -> T:
            del messages, config
            return output_schema.model_validate({"choice_id": "choice:missing"})

    request = _request_with_active_step(
        criterion=(
            StateCriterion(
                criterion_id="criterion:first",
                source_refs=(_request_source(),),
                subject="semantic:first",
                relation=CriterionRelation.EQUALS,
                expected_value="Alice",
                evidence_policy=_request_policy(),
            ),
            StateCriterion(
                criterion_id="criterion:second",
                source_refs=(_request_source(),),
                subject="semantic:first",
                relation=CriterionRelation.IS_COMPLETED,
                evidence_policy=_request_policy(),
            ),
        ),
        affordance=(
            PlannerAffordanceView(
                target_id="semantic:first",
                surface="dom",
                role="textbox",
                label="First",
                supported_actions=("type_text", "activate"),
                state={"value": ""},
            ),
        ),
    )

    response = asyncio.run(GeneralistLMPlanner(UnknownChoiceModel()).propose(request))

    assert isinstance(response, PlannerUnsupportedResponse)
    assert response.reason_code == "invalid_action_choice_selection"


def _assert_strict_semantic_resolver_retired(decision: Any) -> None:
    assert decision.proposal is None
    assert decision.reason in {
        "no_feasible_action_choice",
        "no_strict_model_action_choice",
        "no_active_step_action_choice",
        "action_choice_target_unresolved",
    }


_AUTHORED_EXTENSION = AuthoredInteractiveExtension(
    marker_attribute="data-runtime-interactive",
    backend_handle_attribute="data-runtime-handle",
)


def _authored_dom_adapter() -> DomAdapter:
    return DomAdapter(extension=_AUTHORED_EXTENSION)


def test_generalist_exact_point_binding_preserves_coordinate_signs() -> None:
    context = PlannerContext(
        task_spec={"objective": "Click on the grid coordinate (2,-2)."},
        active_subgoal="",
        observed_text="",
        affordances=tuple(
            AffordanceSummary(
                id=target_id,
                surface="visual",
                role="point",
                label=label,
                action="point_activate",
                confidence=1.0,
                state={},
            )
            for target_id, label in (
                ("semantic:negative", "(-2,-2)"),
                ("semantic:positive", "(2,-2)"),
            )
        ),
        permitted_action_kinds=("point_activate", "ask_user"),
        selected_artifact_refs=(),
        granted_capabilities=(),
        approval_handling="none",
        remaining_budgets={},
        pending_evidence_obligations=(),
        latest_outcome={},
        recent_proposals=(),
        verified_effects=(),
        satisfied_action_targets={},
        recovery_summary={},
        accepted_knowledge=(),
        task_revision=1,
        state_version=1,
        snapshot_id="snap-1",
    )

    assert _explicit_point_target_operation(context) == "semantic:positive"


def test_generalist_binds_one_authored_observed_colour_named_by_the_objective() -> None:
    context = PlannerContext(
        task_spec={"objective": "Click on the olive colored box."},
        active_subgoal="",
        observed_text="",
        affordances=tuple(
            AffordanceSummary(
                id=f"semantic:{color}",
                surface="dom",
                role="button",
                label=color,
                action="activate",
                confidence=0.99,
                state={"observed_color": color},
            )
            for color in ("olive", "yellow", "orange")
        ),
        permitted_action_kinds=("activate", "ask_user"),
        selected_artifact_refs=(),
        granted_capabilities=(),
        approval_handling="none",
        remaining_budgets={},
        pending_evidence_obligations=(),
        latest_outcome={},
        recent_proposals=(),
        verified_effects=(),
        satisfied_action_targets={},
        recovery_summary={},
        accepted_knowledge=(),
        task_revision=1,
        state_version=1,
        snapshot_id="snap-1",
    )

    assert _explicit_observed_color_operation(context) == "semantic:olive"


def test_generalist_binds_rendered_svg_item_from_size_colour_and_type() -> None:
    context = PlannerContext(
        task_spec={"objective": "Click on a small black 8"},
        active_subgoal="",
        observed_text="",
        affordances=(
            AffordanceSummary(
                id="semantic:large-black-8",
                surface="svg",
                role="point",
                label="large black 8 digit",
                action="point_activate",
                confidence=0.99,
                state={
                    "observed_color": "black",
                    "relative_size": "large",
                    "observed_item_type": "digit",
                    "observed_item_text": "8",
                },
            ),
            AffordanceSummary(
                id="semantic:small-black-8",
                surface="svg",
                role="point",
                label="small black 8 digit",
                action="point_activate",
                confidence=0.99,
                state={
                    "observed_color": "black",
                    "relative_size": "small",
                    "observed_item_type": "digit",
                    "observed_item_text": "8",
                },
            ),
        ),
        permitted_action_kinds=("ask_user", "point_activate"),
        selected_artifact_refs=(),
        granted_capabilities=(),
        approval_handling="none",
        remaining_budgets={},
        pending_evidence_obligations=(),
        latest_outcome={},
        recent_proposals=(),
        verified_effects=(),
        satisfied_action_targets={},
        recovery_summary={},
        accepted_knowledge=(),
        task_revision=1,
        state_version=1,
        snapshot_id="snap-1",
    )

    assert _explicit_observed_svg_item_operation(context) == "semantic:small-black-8"
    assert (
        _explicit_observed_svg_item_operation(
            context.model_copy(update={"task_spec": {"objective": "Click on a large digit"}})
        )
        == "semantic:large-black-8"
    )


def test_generalist_selects_lowest_current_svg_number_for_ascending_sequence() -> None:
    context = PlannerContext(
        task_spec={"objective": "Click on the numbers in ascending order."},
        active_subgoal="",
        observed_text="",
        affordances=tuple(
            AffordanceSummary(
                id=f"semantic:number-{number}",
                surface="svg",
                role="point",
                label=f"number {number}",
                action="point_activate",
                confidence=0.99,
                state={"observed_item_type": "digit", "observed_item_text": str(number)},
            )
            for number in (4, 2, 5)
        ),
        permitted_action_kinds=("ask_user", "point_activate"),
        selected_artifact_refs=(),
        granted_capabilities=(),
        approval_handling="none",
        remaining_budgets={},
        pending_evidence_obligations=(),
        latest_outcome={},
        recent_proposals=(),
        verified_effects=(),
        satisfied_action_targets={},
        recovery_summary={},
        accepted_knowledge=(),
        task_revision=1,
        state_version=1,
        snapshot_id="snap-1",
    )

    assert _ascending_numeric_item_operation(context) == "semantic:number-2"


def test_generalist_compiles_named_and_typed_item_quantities() -> None:
    def quantity(target_id: str, name: str, current: int, *item_types: str) -> AffordanceSummary:
        return AffordanceSummary(
            id=target_id,
            surface="dom",
            role="button",
            label=f"increase {name} quantity",
            action="activate",
            confidence=0.99,
            state={
                "item_name": name,
                "item_types": list(item_types),
                "current_quantity": current,
                "quantity_delta": 1,
            },
        )

    affordances = (
        quantity("thai", "Spicy Thai Peanut Chicken", 1, "meat", "peanuts"),
        quantity("ice", "Ice cream sundae", 0, "dairy", "peanuts"),
        AffordanceSummary(
            id="order",
            surface="dom",
            role="button",
            label="Order!",
            action="activate",
            confidence=0.99,
            state={},
        ),
    )
    context = PlannerContext(
        task_spec={"objective": "Order one of each item: Spicy Thai Peanut Chicken, Ice cream sundae"},
        active_subgoal="",
        observed_text="",
        affordances=affordances,
        permitted_action_kinds=("activate", "ask_user"),
        selected_artifact_refs=(),
        granted_capabilities=(),
        approval_handling="none",
        remaining_budgets={},
        pending_evidence_obligations=(),
        latest_outcome={},
        recent_proposals=(),
        verified_effects=(),
        satisfied_action_targets={},
        recovery_summary={},
        accepted_knowledge=(),
        task_revision=1,
        state_version=1,
        snapshot_id="snap-1",
    )

    assert _quantity_order_operation(context) == "ice"
    complete = context.model_copy(
        update={
            "affordances": (affordances[0], quantity("ice", "Ice cream sundae", 1, "dairy", "peanuts"), affordances[2])
        }
    )
    assert _quantity_order_operation(complete) == "order"
    typed = context.model_copy(update={"task_spec": {"objective": "Order 2 items that are peanuts"}})
    assert _quantity_order_operation(typed) == "thai"


def test_generalist_compiles_calendar_duration_into_distinct_semantic_range_endpoints() -> None:
    def slot(index: int, endpoint: str) -> AffordanceSummary:
        return AffordanceSummary(
            id=f"slot-{index}-{endpoint}",
            surface="dom",
            role="time_slot" if endpoint == "start" else "time_slot_end",
            label=f"slot {index} {endpoint}",
            action="drag" if endpoint == "start" else "drop",
            confidence=0.99,
            state={
                "calendar_slot_index": index,
                "calendar_endpoint": endpoint,
                "range_selectable": True,
                "accepts_drop": endpoint == "end",
            },
        )

    affordances = tuple(slot(index, endpoint) for index in range(16, 33) for endpoint in ("start", "end"))
    context = PlannerContext(
        task_spec={"objective": 'Create a 30 mins event named "Food", between 8AM and 12PM.'},
        active_subgoal="",
        observed_text="",
        affordances=affordances,
        permitted_action_kinds=("drag", "ask_user"),
        selected_artifact_refs=(),
        granted_capabilities=(),
        approval_handling="none",
        remaining_budgets={},
        pending_evidence_obligations=(),
        latest_outcome={},
        recent_proposals=(),
        verified_effects=(),
        satisfied_action_targets={},
        recovery_summary={},
        accepted_knowledge=(),
        task_revision=1,
        state_version=1,
        snapshot_id="snap-1",
    )

    assert _calendar_event_gesture_operation(context) == ("slot-16-start", "slot-16-end")
    assert _compiled_calendar_event_operation(context) == (
        PlannerActionKind.DRAG,
        "slot-16-start",
        "slot-16-end",
        {},
    )
    ninety_minutes = context.model_copy(
        update={"task_spec": {"objective": 'Create a 1.5 hours event named "Gym", between 12PM and 4PM.'}}
    )
    assert _calendar_event_gesture_operation(ninety_minutes) == (
        "slot-24-start",
        "slot-26-end",
    )


def test_generalist_compiles_calendar_event_name_after_range_selection() -> None:
    range_source = AffordanceSummary(
        id="slot-24-start",
        surface="dom",
        role="time_slot",
        label="12:00pm calendar slot",
        action="drag",
        confidence=0.99,
        state={"calendar_slot_index": 24, "calendar_endpoint": "start", "range_selectable": True},
    )
    name_input = AffordanceSummary(
        id="event-name",
        surface="dom",
        role="textbox",
        label="Event name",
        action="type",
        confidence=0.99,
        state={"control_value": ""},
    )
    context = PlannerContext(
        task_spec={"objective": 'Create a 90 mins event named "Gym", between 12PM and 4PM.'},
        active_subgoal="",
        observed_text="",
        affordances=(range_source, name_input),
        permitted_action_kinds=("drag", "type_text", "activate", "ask_user"),
        selected_artifact_refs=(),
        granted_capabilities=(),
        approval_handling="none",
        remaining_budgets={},
        pending_evidence_obligations=(),
        latest_outcome={},
        recent_proposals=(),
        verified_effects=(),
        satisfied_action_targets={},
        recovery_summary={},
        accepted_knowledge=(),
        task_revision=1,
        state_version=2,
        snapshot_id="snap-2",
    )

    assert _compiled_calendar_event_operation(context) == (
        PlannerActionKind.TYPE_TEXT,
        "event-name",
        "",
        {"text": "Gym"},
    )
    create = AffordanceSummary(
        id="create",
        surface="dom",
        role="button",
        label="Create",
        action="click",
        confidence=0.99,
        state={},
    )
    filled = context.model_copy(
        update={
            "affordances": (
                range_source,
                name_input.model_copy(update={"state": {"control_value": "Gym"}}),
                create,
            )
        }
    )
    assert _compiled_calendar_event_operation(filled) == (
        PlannerActionKind.ACTIVATE,
        "create",
        "",
        {},
    )


def test_generalist_compiles_owner_scoped_collection_action_and_menu_disclosure() -> None:
    def control(
        target_id: str,
        action: str,
        owner: str,
        position: int,
        *,
        selected: bool = False,
    ) -> AffordanceSummary:
        return AffordanceSummary(
            id=target_id,
            surface="dom",
            role="button",
            label=action,
            action="activate",
            confidence=0.99,
            state={
                "collection_action": action,
                "collection_owner": owner,
                "collection_position": position,
                "toggle_selected": selected,
            },
        )

    def context(objective: str, affordances: tuple[AffordanceSummary, ...]) -> PlannerContext:
        return PlannerContext(
            task_spec={"objective": objective},
            active_subgoal="",
            observed_text="",
            affordances=affordances,
            permitted_action_kinds=("activate", "ask_user"),
            selected_artifact_refs=(),
            granted_capabilities=(),
            approval_handling="none",
            remaining_budgets={},
            pending_evidence_obligations=(),
            latest_outcome={},
            recent_proposals=(),
            verified_effects=(),
            satisfied_action_targets={},
            recovery_summary={},
            accepted_knowledge=(),
            task_revision=1,
            state_version=1,
            snapshot_id="snap-1",
        )

    direct = context(
        'For the user @alice, click on the "Like" button.',
        (
            control("alice-like", "Like", "@alice", 3),
            control("bob-like", "Like", "@bob", 1),
        ),
    )
    assert _owned_collection_action_operation(direct) == "alice-like"

    disclosure = context(
        'For the user @alice, click on the "Share via DM" button.',
        (control("alice-more", "More", "@alice", 3),),
    )
    assert _owned_collection_action_operation(disclosure) == "alice-more"
    disclosed = disclosure.model_copy(
        update={
            "affordances": (
                control("alice-more", "More", "@alice", 3),
                control("alice-share", "Share via DM", "@alice", 3),
            )
        }
    )
    assert _owned_collection_action_operation(disclosed) == "alice-share"


def test_generalist_compiles_bounded_owner_collection_toggles_before_submit() -> None:
    def control(target_id: str, owner: str, position: int, *, selected: bool) -> AffordanceSummary:
        return AffordanceSummary(
            id=target_id,
            surface="dom",
            role="button",
            label="Like",
            action="activate",
            confidence=0.99,
            state={
                "collection_action": "Like",
                "collection_owner": owner,
                "collection_position": position,
                "toggle_selected": selected,
            },
        )

    submit = AffordanceSummary(
        id="submit",
        surface="dom",
        role="button",
        label="Submit",
        action="activate",
        confidence=0.99,
        state={},
    )
    base = PlannerContext(
        task_spec={"objective": 'Click the "Like" button on 2 posts by @alice and then click Submit.'},
        active_subgoal="",
        observed_text="",
        affordances=(
            control("alice-1", "@alice", 1, selected=False),
            control("bob-2", "@bob", 2, selected=False),
            control("alice-3", "@alice", 3, selected=False),
            submit,
        ),
        permitted_action_kinds=("activate", "ask_user"),
        selected_artifact_refs=(),
        granted_capabilities=(),
        approval_handling="none",
        remaining_budgets={},
        pending_evidence_obligations=(),
        latest_outcome={},
        recent_proposals=(),
        verified_effects=(),
        satisfied_action_targets={},
        recovery_summary={},
        accepted_knowledge=(),
        task_revision=1,
        state_version=1,
        snapshot_id="snap-1",
    )

    assert _owned_collection_action_operation(base) == "alice-1"
    one_selected = base.model_copy(
        update={
            "affordances": (
                control("alice-1", "@alice", 1, selected=True),
                control("bob-2", "@bob", 2, selected=False),
                control("alice-3", "@alice", 3, selected=False),
                submit,
            )
        }
    )
    assert _owned_collection_action_operation(one_selected) == "alice-3"
    complete = one_selected.model_copy(
        update={
            "affordances": (
                control("alice-1", "@alice", 1, selected=True),
                control("bob-2", "@bob", 2, selected=False),
                control("alice-3", "@alice", 3, selected=True),
                submit,
            )
        }
    )
    assert _owned_collection_action_operation(complete) == "submit"


def test_generalist_compact_state_retains_complete_quantity_semantics() -> None:
    compact = _compact_mapping(
        {
            "container_context": "- +",
            "current_quantity": 2,
            "element_tag": "span",
            "enabled": True,
            "focused": False,
            "grounding_source_count": 1,
            "group_context": "Peanut bowl - +",
            "item_name": "Peanut bowl",
            "item_types": ["peanuts", "vegan"],
            "quantity_delta": 1,
            "repeatable": True,
            "visible": True,
        }
    )

    assert compact["item_types"] == ["peanuts", "vegan"]
    assert compact["quantity_delta"] == 1
    assert compact["repeatable"] is True


def test_bounded_affordances_do_not_let_repeated_container_prose_hide_dynamic_controls() -> None:
    objective = 'Create a 90 mins event named "Gym", between 4PM and 8PM.'

    def calendar_endpoint(index: int, endpoint: str) -> AffordanceSummary:
        return AffordanceSummary(
            id=f"slot-{index}-{endpoint}",
            surface="dom",
            role="time_slot" if endpoint == "start" else "time_slot_end",
            label=f"slot {index} {endpoint}",
            action="drag" if endpoint == "start" else "drop",
            confidence=0.99,
            state={
                "calendar_slot_index": index,
                "calendar_endpoint": endpoint,
                "range_selectable": True,
                "container_context": objective,
                "context_text": objective,
                "group_context": objective,
            },
        )

    slots = [calendar_endpoint(index, endpoint) for index in range(48) for endpoint in ("start", "end")]
    event_name = AffordanceSummary(
        id="event-name",
        surface="dom",
        role="textbox",
        label="Event name",
        action="type",
        confidence=0.1,
        state={"control_value": ""},
    )
    create = AffordanceSummary(
        id="create",
        surface="dom",
        role="button",
        label="Create",
        action="click",
        confidence=0.1,
        state={},
    )

    bounded = _bounded_affordances([*slots, event_name, create], objective, (), 80)

    assert event_name in bounded
    assert create in bounded
    assert calendar_endpoint(32, "start") in bounded
    assert calendar_endpoint(34, "end") in bounded


def test_generalist_compiles_labelled_items_into_explicit_left_and_right_drop_bins() -> None:
    def summary(
        target_id: str,
        label: str,
        *,
        role: str = "draggable",
        action: str = "drag",
        accepts_drop: bool = False,
    ) -> AffordanceSummary:
        return AffordanceSummary(
            id=target_id,
            surface="svg",
            role=role,
            label=label,
            action=action,
            confidence=1.0,
            state={"accepts_drop": accepts_drop},
        )

    context = PlannerContext(
        task_spec={"objective": "Drag all circles into the left box, and everything else into the right box."},
        active_subgoal="",
        observed_text="",
        affordances=(
            summary("green-triangle", "green triangle"),
            summary("black-circle", "black circle"),
            summary("left", "left box", role="drop_target", accepts_drop=True),
            summary("right", "right box", role="drop_target", accepts_drop=True),
            summary("submit", "Submit", role="button", action="activate"),
        ),
        permitted_action_kinds=("activate", "ask_user", "drag"),
        selected_artifact_refs=(),
        granted_capabilities=(),
        approval_handling="none",
        remaining_budgets={},
        pending_evidence_obligations=(),
        latest_outcome={},
        recent_proposals=(),
        verified_effects=(),
        satisfied_action_targets={},
        recovery_summary={},
        accepted_knowledge=(),
        task_revision=1,
        state_version=1,
        snapshot_id="snap-1",
    )

    assert _partitioned_drag_operation(context) == (
        PlannerActionKind.DRAG,
        "green-triangle",
        "right",
    )
    assert _partitioned_drag_operation(
        context.model_copy(update={"satisfied_action_targets": {"drag": ("green-triangle",)}})
    ) == (PlannerActionKind.DRAG, "black-circle", "left")
    assert _partitioned_drag_operation(
        context.model_copy(update={"satisfied_action_targets": {"drag": ("green-triangle", "black-circle")}})
    ) == (PlannerActionKind.ACTIVATE, "submit", "")


def test_generalist_compiles_readonly_calendar_month_day_and_submit() -> None:
    def context(affordances: tuple[AffordanceSummary, ...]) -> PlannerContext:
        return PlannerContext(
            task_spec={"objective": "Select 03/17/2016 as the date and hit submit."},
            active_subgoal="",
            observed_text="",
            affordances=affordances,
            permitted_action_kinds=("activate", "ask_user"),
            selected_artifact_refs=(),
            granted_capabilities=(),
            approval_handling="none",
            remaining_budgets={},
            pending_evidence_obligations=(),
            latest_outcome={},
            recent_proposals=(),
            verified_effects=(),
            satisfied_action_targets={},
            recovery_summary={},
            accepted_knowledge=(),
            task_revision=1,
            state_version=1,
            snapshot_id="snap-1",
        )

    picker = AffordanceSummary(
        id="picker",
        surface="dom",
        role="picker",
        label="datepicker",
        action="activate",
        confidence=1.0,
        state={"readonly": True, "control_value": ""},
    )
    submit = AffordanceSummary(
        id="submit",
        surface="dom",
        role="button",
        label="Submit",
        action="activate",
        confidence=1.0,
        state={},
    )
    prev = AffordanceSummary(
        id="prev",
        surface="dom",
        role="link",
        label="Prev",
        action="activate",
        confidence=1.0,
        state={"group_context": "Prev Next December 2016"},
    )
    day = AffordanceSummary(
        id="day-17",
        surface="dom",
        role="link",
        label="17",
        action="activate",
        confidence=1.0,
        # The first calendar cell may carry only the containing calendar text;
        # later cells can additionally receive a row-level group context.
        state={"container_context": "Prev Next March 2016 1 2 3 17"},
    )

    assert _calendar_date_operation(context((picker, submit))) == "picker"
    assert _calendar_date_operation(context((picker, submit, prev))) == "prev"
    march_prev = prev.model_copy(update={"state": {"group_context": "Prev Next March 2016"}})
    assert _calendar_date_operation(context((picker, submit, march_prev, day))) == "day-17"
    selected = picker.model_copy(update={"state": {"readonly": True, "control_value": "03/17/2016"}})
    assert _calendar_date_operation(context((selected, submit))) == "submit"

    october_first = day.model_copy(
        update={
            "id": "day-1",
            "label": "1",
            "state": {"container_context": "Prev Next October 2016 Su Mo Tu We Th Fr Sa 1 2 3"},
        }
    )
    october_prev = prev.model_copy(update={"state": {"group_context": "Prev Next October 2016"}})
    october_context = context((picker, submit, october_prev, october_first)).model_copy(
        update={"task_spec": {"objective": "Select 10/01/2016 as the date and hit submit."}}
    )
    assert _calendar_date_operation(october_context) == "day-1"


def test_only_compatibility_binding_rewrites_explicit_lowercase_task_grammar() -> None:
    model = _authored_dom_adapter().transduce(
        "<input><button>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    state = StateKernel("task-lower", "lowercase")
    state.remember_observation(observation)
    task = TaskSpec(
        task_id="task-lower",
        revision=1,
        objective='Type "CHEREE" in all lower case letters in the text input and press Submit.',
        operation_class=OperationClass.READ_ONLY,
        targets=("text",),
        success_criteria=("submitted",),
        source_request_ref="test",
    )
    context = build_planner_context(RunRequest(task_spec=task), state, BrowserSnapshot(observation, model))

    candidate = PlannerProposalCandidate(
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id="dom_input_1",
        parameters={"text": "cherée"},
    )

    assert candidate.bind(context).parameters == {"text": "cherée"}
    assert candidate.bind(context, compatibility_rewrites=True).parameters == {"text": "cheree"}


def test_generalist_opens_tightest_visible_ancestor_of_hidden_quoted_target() -> None:
    model = _authored_dom_adapter().transduce(
        '<ul><li><span data-runtime-interactive="1">Leonie</span></li>'
        '<li><span data-runtime-interactive="1">Sergio</span>'
        '<ul style="display:none"><li><span>Nathalie</span></li></ul></li></ul>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    state = StateKernel("task-tree", "tree")
    state.remember_observation(observation)
    task = TaskSpec(
        task_id="task-tree",
        revision=1,
        objective='Find and click on the folder or file named "Nathalie".',
        operation_class=OperationClass.READ_ONLY,
        targets=("tree",),
        success_criteria=("target opened",),
        source_request_ref="test",
    )
    context = build_planner_context(RunRequest(task_spec=task), state, BrowserSnapshot(observation, model))

    proposal = PlannerProposalCandidate(
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id="dom_span_1",
    ).bind(context, compilation=default_semantic_compiler_registry().compile(context))

    assert proposal.target_affordance_id == "dom_span_2"


@dataclass
class ProposalModel:
    provider: str = "fixed"
    model: str = "fixed-v1"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None
    context: dict[str, object] | None = None
    system_prompt: str = ""
    output_schema_name: str = ""

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        self.system_prompt = messages[0].content
        self.context = __import__("json").loads(messages[1].content)
        self.output_schema_name = output_schema.__name__
        assert config.prompt_version in {
            GENERALIST_PLANNER_PROMPT_VERSION,
            COMPATIBILITY_PLANNER_PROMPT_VERSION,
        }
        payload: dict[str, object] = {
            "action_kind": PlannerActionKind.ACTIVATE,
            "target_affordance_id": "dom_button_1",
            "parameters": {},
        }
        if "subgoal" in output_schema.model_fields:
            payload["subgoal"] = "Save the selected theme"
        if "expected_effects" in output_schema.model_fields:
            payload["expected_effects"] = ["theme is saved"]
        if "evidence_requirements" in output_schema.model_fields:
            payload["evidence_requirements"] = ["saved theme evidence"]
        return output_schema.model_validate(payload)


@dataclass
class EmptyClarificationModel:
    provider: str = "fixed"
    model: str = "empty-clarification"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del messages, config
        return output_schema.model_validate({"action_kind": "ask_user"})


def test_generalist_propose_uses_immutable_request_context_and_admission() -> None:
    model = _authored_dom_adapter().transduce(
        '<button id="submit">Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    source = model.affordances[0]
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
    )
    candidate = candidate_from_affordance(
        source,
        observation,
        semantic_target_id="submit-target",
        compatible_executor="browsergym",
    )
    target = SemanticEntityResolver().resolve(
        (
            CandidateDescriptor(
                "button",
                "settings submission",
                "activate",
                "settings",
                candidate,
            ),
        )
    )[0]
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
        target_fingerprints=candidate_fingerprints((target,)),
    )
    snapshot = BrowserSnapshot(
        observation,
        model,
        grounding_candidates=target.grounding_candidates,
        unified_affordances=(target,),
    )
    state = StateKernel("task-1", "submit settings")
    state.remember_observation(observation)
    plan = TaskPlan(
        plan_id="plan-request",
        task_id="task-1",
        task_revision=2,
        plan_version=1,
        based_on_state_version=state.version,
        generated_by=TaskPlanSource.LLM,
        subgoals=(
            SubgoalSpec(
                subgoal_id="field:value",
                objective="field equals dark",
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.TYPE_TEXT,
                outcome=SubgoalOutcome(
                    subject="field",
                    relation=SubgoalOutcomeRelation.EQUALS,
                    value="dark",
                ),
                interaction=ElementIntent("field", (_request_source(),)),
            ),
            SubgoalSpec(
                subgoal_id="settings:submitted",
                objective="settings submission is completed",
                depends_on=("field:value",),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.ACTIVATE,
                outcome=SubgoalOutcome(
                    subject="settings submission",
                    relation=SubgoalOutcomeRelation.IS_COMPLETED,
                ),
                interaction=ElementIntent(
                    "settings submission", (_request_source(),), role="button"
                ),
            ),
        ),
    )
    state.task_plan = plan
    state.task_progress = PlanProgress(
        active_subgoal_id="settings:submitted",
        completed_subgoal_ids=["field:value"],
        evidence_by_subgoal={},
    )
    task_spec = TaskSpec(
        task_id="task-1",
        revision=2,
        objective="Set the field to dark and submit settings",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("settings",),
        success_criteria=("settings submitted",),
        source_request_ref="request-1",
        source_claims=(
            SourcedTaskClaim(
                claim_id="claim:field",
                kind=TaskClaimKind.EFFECT,
                statement="field equals dark",
                source_ref="request-1",
                source_unit_ids=("unit:field",),
            ),
            SourcedTaskClaim(
                claim_id="claim:submit",
                kind=TaskClaimKind.EFFECT,
                statement="settings submission is completed",
                source_ref="request-1",
                source_unit_ids=("unit:submit",),
            ),
        ),
        obligations=(
            TaskObligationSpec(
                obligation_id="field:value",
                kind=TaskObligationKind.EFFECT,
                subject="field",
                relation=TaskObligationRelation.EQUALS,
                value_source=TaskObligationValueSource.LITERAL,
                expected_value="dark",
                claim_ids=("claim:field",),
                evidence_requirements=("field state evidence",),
                typed_evidence_requirements=(
                    EvidenceRequirement(
                        kind=EvidenceKind.DOM_STATE,
                        subject="field",
                        relation=TaskObligationRelation.EQUALS,
                        value_ref="dark",
                        minimum_strength="independent",
                        source_constraints=("post_action_observation",),
                    ),
                ),
            ),
            TaskObligationSpec(
                obligation_id="settings:submitted",
                kind=TaskObligationKind.EFFECT,
                subject="settings submission",
                relation=TaskObligationRelation.IS_COMPLETED,
                value_source=TaskObligationValueSource.NONE,
                depends_on=("field:value",),
                claim_ids=("claim:submit",),
                evidence_requirements=("submit completion evidence",),
                terminal=True,
                typed_evidence_requirements=(
                    EvidenceRequirement(
                        kind=EvidenceKind.DOM_STATE,
                        subject="settings submission",
                        relation=TaskObligationRelation.IS_COMPLETED,
                        minimum_strength="independent",
                        source_constraints=("post_action_observation",),
                    ),
                ),
            ),
        ),
    )

    @dataclass
    class RecordingRequestBuilder:
        inner: PlanningRequestBuilder = PlanningRequestBuilder()
        built: PlanningRequest | None = None

        def build(
            self,
            envelope: RunRequest,
            state: StateKernel,
            snapshot: BrowserSnapshot,
        ) -> PlanningRequest:
            self.built = self.inner.build(envelope, state, snapshot)
            return self.built

    @dataclass
    class RequestOnlyContextBuilder:
        received: PlanningRequest | None = None

        def build(
            self,
            request: PlanningRequest,
            state: StateKernel | None = None,
            snapshot: BrowserSnapshot | None = None,
        ) -> PlannerContext:
            assert state is None
            assert snapshot is None
            self.received = request
            return GeneralistLMPlanner(
                ProposalModel(),
            )._context_builder().build(request)

    @dataclass
    class AskUserModel(ProposalModel):
        async def generate_structured(
            self,
            messages: Sequence[ModelMessage],
            output_schema: type[T],
            config: ModelConfig,
        ) -> T:
            self.context = __import__("json").loads(messages[1].content)
            return output_schema.model_validate({"action_kind": "ask_user"})

    request_builder = RecordingRequestBuilder()
    context_builder = RequestOnlyContextBuilder()
    model_port = AskUserModel()

    decision = asyncio.run(
        GeneralistLMPlanner(
            model_port,
            planning_request_builder=request_builder,  # type: ignore[arg-type]
            context_builder=context_builder,  # type: ignore[arg-type]
        ).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert request_builder.built is not None
    assert context_builder.received is request_builder.built
    assert model_port.context is None
    assert decision.proposal is None
    assert decision.reason == "no_active_step_action_choice"
    assert decision.planner_context["action_choice_failure"]["reason_code"] == "no_active_step_action_choice"  # type: ignore[index]
    assert "terminal_readiness" not in decision.planner_context


def test_generalist_context_is_bounded_semantic_and_authority_separated() -> None:
    model = _authored_dom_adapter().transduce(
        '<button id="save" data-runtime-handle="secret-backend-handle">Save</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Save theme")
    state.transition("observing")
    state.remember_observation(observation)
    state.transition("planning")
    task_spec = TaskSpec(
        task_id="task-1",
        revision=3,
        objective="Save theme",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("theme",),
        success_criteria=("theme saved",),
        requested_capabilities=("settings.write", "profile.admin"),
        source_request_ref="request-1",
    )
    fixed = ProposalModel()

    decision = asyncio.run(
        GeneralistLMPlanner(fixed).propose_legacy(
            RunRequest(task_spec=task_spec, capabilities=["settings.write"]),
            state,
            snapshot,
        )
    )

    assert decision.proposal is None
    assert decision.reason == "no_active_step_action_choice"
    assert fixed.context is None
    assert decision.planner_context["planner_profile"] == "strict-generalist"

    repaired_model = ProposalModel()
    repaired_planner = GeneralistLMPlanner(repaired_model)
    assert repaired_planner.repair_planner_schema() is not None
    repaired_decision = asyncio.run(
        repaired_planner.propose_legacy(
            RunRequest(task_spec=task_spec, capabilities=["settings.write"]),
            state,
            snapshot,
        )
    )
    assert repaired_decision.proposal is None
    assert repaired_model.context is None
    assert fixed.output_schema_name == ""
    assert repaired_model.output_schema_name == ""

    compatibility_model = ProposalModel()
    compatibility = asyncio.run(
        GeneralistLMPlanner(
            compatibility_model,
            planner_profile=GeneralistPlannerProfile.HISTORICAL_COMPATIBILITY,
            semantic_compilers=SemanticCompilerRegistry.disabled(),
        ).propose_legacy(
            RunRequest(task_spec=task_spec, capabilities=["settings.write"]),
            state,
            snapshot,
        )
    )
    assert compatibility.planner_context["prompt_version"] == COMPATIBILITY_PLANNER_PROMPT_VERSION
    assert compatibility.proposal_provenance is not None
    assert compatibility.proposal_provenance.source.value == "model"
    assert compatibility.proposal_provenance.profile_id == "historical-compatibility"
    assert compatibility_model.context is not None
    affordance = compatibility_model.context["affordances"][0]  # type: ignore[index]
    assert affordance["id"] == "dom_button_1"
    assert "locator" not in affordance
    assert "secret-backend-handle" not in str(compatibility_model.context)
    assert compatibility_model.context["granted_capabilities"] == ["settings.write"]
    assert compatibility_model.context["permitted_action_kinds"] == ["activate", "ask_user", "finish"]
    assert compatibility_model.context["task_spec"]["requested_capabilities"] == [  # type: ignore[index]
        "settings.write",
        "profile.admin",
    ]
    assert "autocomplete" in compatibility_model.system_prompt.casefold()


@pytest.mark.parametrize("verified_prerequisite", [False, True])
def test_strict_planner_uses_active_step_admission_without_terminal_readiness(
    verified_prerequisite: bool,
) -> None:
    affordance_model = _authored_dom_adapter().transduce(
        '<button data-runtime-handle="submit">settings submission</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-2",
    )
    source = affordance_model.affordances[0]
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-2",
        page_revision=affordance_model.page_revision,
    )
    candidate = candidate_from_affordance(
        source,
        observation,
        semantic_target_id="pending",
        compatible_executor="browsergym",
    )
    target = SemanticEntityResolver().resolve(
        (
            CandidateDescriptor(
                "button",
                "settings submission",
                "activate",
                "settings",
                candidate,
            ),
        )
    )[0]
    observation = replace(
        observation,
        target_fingerprints=candidate_fingerprints((target,)),
    )
    snapshot = BrowserSnapshot(
        observation,
        affordance_model,
        grounding_candidates=target.grounding_candidates,
        unified_affordances=(target,),
    )
    plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=2,
        plan_version=1,
        based_on_state_version=1,
        generated_by=TaskPlanSource.LLM,
        subgoals=(
            SubgoalSpec(
                subgoal_id="field:value",
                objective="field equals dark",
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.TYPE_TEXT,
                outcome=SubgoalOutcome(
                    subject="field",
                    relation=SubgoalOutcomeRelation.EQUALS,
                    value="dark",
                ),
                interaction=ElementIntent("field", (_request_source(),)),
            ),
            SubgoalSpec(
                subgoal_id="settings:submitted",
                objective="settings submission is completed",
                depends_on=("field:value",),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.ACTIVATE,
                outcome=SubgoalOutcome(
                    subject="settings submission",
                    relation=SubgoalOutcomeRelation.IS_COMPLETED,
                ),
                interaction=ElementIntent(
                    "settings submission", (_request_source(),), role="button"
                ),
            ),
        ),
    )
    state = StateKernel("task-1", "submit settings")
    state.task_plan = plan
    state.task_progress = PlanProgress(
        active_subgoal_id="settings:submitted",
        completed_subgoal_ids=["field:value"],
        evidence_by_subgoal=(
            {"field:value": ["artifact:verification"]}
            if verified_prerequisite
            else {}
        ),
    )
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=2,
        objective="Set the field to dark and submit settings",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("settings",),
        success_criteria=("settings submitted",),
        source_request_ref="request-1",
        source_claims=(
            SourcedTaskClaim(
                claim_id="claim:field",
                kind=TaskClaimKind.EFFECT,
                statement="field equals dark",
                source_ref="request-1",
                source_unit_ids=("unit:field",),
            ),
            SourcedTaskClaim(
                claim_id="claim:submit",
                kind=TaskClaimKind.EFFECT,
                statement="settings submission is completed",
                source_ref="request-1",
                source_unit_ids=("unit:submit",),
            ),
        ),
        obligations=(
            TaskObligationSpec(
                obligation_id="field:value",
                kind=TaskObligationKind.EFFECT,
                subject="field",
                relation=TaskObligationRelation.EQUALS,
                value_source=TaskObligationValueSource.LITERAL,
                expected_value="dark",
                claim_ids=("claim:field",),
                evidence_requirements=("field state evidence",),
                typed_evidence_requirements=(
                    EvidenceRequirement(
                        kind=EvidenceKind.DOM_STATE,
                        subject="field",
                        relation=TaskObligationRelation.EQUALS,
                        value_ref="dark",
                        minimum_strength="independent",
                        source_constraints=("post_action_observation",),
                    ),
                ),
            ),
            TaskObligationSpec(
                obligation_id="settings:submitted",
                kind=TaskObligationKind.EFFECT,
                subject="settings submission",
                relation=TaskObligationRelation.IS_COMPLETED,
                value_source=TaskObligationValueSource.NONE,
                depends_on=("field:value",),
                claim_ids=("claim:submit",),
                evidence_requirements=("submit completion evidence",),
                terminal=True,
                typed_evidence_requirements=(
                    EvidenceRequirement(
                        kind=EvidenceKind.DOM_STATE,
                        subject="settings submission",
                        relation=TaskObligationRelation.IS_COMPLETED,
                        minimum_strength="independent",
                        source_constraints=("post_action_observation",),
                    ),
                ),
            ),
        ),
    )

    @dataclass
    class ReadinessModel:
        provider: str = "fixed"
        model: str = "readiness"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None
        context: dict[str, object] | None = None

        async def generate_structured(
            self,
            messages: Sequence[ModelMessage],
            output_schema: type[T],
            config: ModelConfig,
        ) -> T:
            del config
            self.context = __import__("json").loads(messages[1].content)
            return output_schema.model_validate({"action_kind": "ask_user"})

    model = ReadinessModel()
    decision = asyncio.run(
        GeneralistLMPlanner(model).propose_legacy(
            RunRequest(task_spec=task_spec),
            state,
            snapshot,
        )
    )

    assert "terminal_readiness" not in decision.planner_context
    if verified_prerequisite:
        assert decision.proposal is not None
        assert model.context is None
        assert decision.proposal.action_kind == PlannerActionKind.ACTIVATE
        assert decision.proposal.target_affordance_id == target.semantic_target_id
        assert decision.proposal_provenance is not None
        assert decision.proposal_provenance.producer_id == "runtime-action-choice"
    else:
        assert decision.proposal is None
        assert model.context is None
        assert decision.reason == "no_active_step_action_choice"


def test_generalist_rebinds_runtime_identity_and_accepts_singular_effect_aliases() -> None:
    model = _authored_dom_adapter().transduce(
        '<button id="save">Save</button>', environment_revision="rev-1", snapshot_id="snapshot-1"
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Save theme")
    state.transition("observing")
    state.remember_observation(observation)
    state.transition("planning")
    task_spec = TaskSpec(
        task_id="task-1",
        revision=3,
        objective="Save theme",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("theme",),
        success_criteria=("theme saved",),
        source_request_ref="request-1",
    )

    @dataclass
    class CandidateModel:
        provider: str = "fixed"
        model: str = "candidate-v1"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            assert issubclass(output_schema, PlannerProposalCandidate)
            return output_schema.model_validate(
                {
                    "action_kind": "activate",
                    "target_affordance_id": "dom_button_1",
                    "expected_effect": "theme is saved",
                    "evidence_need": "saved theme evidence",
                }
            )

    decision = asyncio.run(
        _compatibility_planner(CandidateModel()).propose_legacy(
            RunRequest(task_spec=task_spec),
            state,
            snapshot,
        )
    )

    assert decision.proposal is not None
    assert decision.proposal.proposal_id == f"generalist-3-{state.version}"
    assert decision.proposal.based_on_task_revision == 3
    assert decision.proposal.based_on_state_version == state.version
    assert decision.proposal.snapshot_id == "snapshot-1"
    assert decision.proposal.expected_effects == ("theme is saved",)
    assert decision.proposal.evidence_requirements == ("saved theme evidence",)
    with pytest.raises(ValidationError):
        PlannerProposalCandidate.model_validate(
            {"proposal_id": "model-controlled-id", "action_kind": "activate", "target_affordance_id": "dom_button_1"}
        )


def test_generalist_redacts_invalid_candidate_payloads() -> None:
    model = _authored_dom_adapter().transduce(
        '<input id="name"><input id="email">', environment_revision="rev-1", snapshot_id="snapshot-1"
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Enter name")
    state.transition("observing")
    state.remember_observation(observation)
    state.transition("planning")
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Enter name",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("name",),
        success_criteria=("name saved",),
        source_request_ref="request-1",
    )

    @dataclass
    class InvalidCandidateModel:
        provider: str = "fixed"
        model: str = "invalid-candidate"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            return output_schema.model_validate(
                {"action_kind": "type_text", "parameters": {"text": "private-value"}}
            )

    with pytest.raises(StructuredModelError) as exc_info:
        asyncio.run(
            _compatibility_planner(InvalidCandidateModel()).propose_legacy(
                RunRequest(task_spec=task_spec),
                state,
                snapshot,
            )
        )

    assert str(exc_info.value) == "structured output validation failed"
    assert "private-value" not in str(exc_info.value)


def test_generalist_repairs_one_invalid_candidate_on_the_same_snapshot() -> None:
    model = _authored_dom_adapter().transduce(
        '<input id="name"><input id="email">', environment_revision="rev-1", snapshot_id="snapshot-1"
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Enter name")
    state.transition("observing")
    state.remember_observation(observation)
    state.transition("planning")
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Enter name",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("name",),
        success_criteria=("name saved",),
        source_request_ref="request-1",
    )

    @dataclass
    class RepairingCandidateModel:
        provider: str = "fixed"
        model: str = "repairing-candidate"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None
        calls: int = 0

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del config
            self.calls += 1
            if self.calls == 1:
                return output_schema.model_validate({"action_kind": "type_text", "parameters": {"text": "Ada"}})
            assert "validation_error_types" in messages[-1].content
            return output_schema.model_validate(
                {"action_kind": "type_text", "target_affordance_id": "dom_input_1", "parameters": {"text": "Ada"}}
            )

    repair_model = RepairingCandidateModel()
    decision = asyncio.run(
        _compatibility_planner(repair_model).propose_legacy(
            RunRequest(task_spec=task_spec),
            state,
            snapshot,
        )
    )

    assert repair_model.calls == 2
    assert decision.proposal is not None
    assert decision.proposal.target_affordance_id == "dom_input_1"
    assert decision.proposal.parameters == {"text": "Ada"}


def test_drag_repair_schema_requires_a_semantic_destination() -> None:
    schema = _repair_candidate_schema(
        ["drag"],
        {"drag": ["source"]},
        require_drag_destination=True,
        drag_destination_ids=("destination",),
    )

    with pytest.raises(ValidationError):
        schema.model_validate({"action_kind": "drag", "target_affordance_id": "source"})
    with pytest.raises(ValidationError):
        schema.model_validate(
            {
                "action_kind": "drag",
                "target_affordance_id": "destination",
                "destination_affordance_id": "source",
            }
        )
    candidate = schema.model_validate(
        {
            "action_kind": "drag",
            "target_affordance_id": "source",
            "destination_affordance_id": "destination",
        }
    )

    assert candidate.destination_affordance_id == "destination"


def test_generalist_compiles_explicit_one_position_drag_to_adjacent_semantic_targets() -> None:
    model = _authored_dom_adapter().transduce(
        '<li class="ui-sortable-handle">Lesly</li>'
        '<li class="ui-sortable-handle">Marianna</li>'
        '<li class="ui-sortable-handle">Lyssa</li>'
        '<li class="ui-sortable-handle">Toby</li>'
        '<li class="ui-sortable-handle">Carissa</li>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    state = StateKernel("task-drag", "Drag Lyssa down by one position")
    state.remember_observation(observation)
    task = TaskSpec(
        task_id="task-drag",
        revision=1,
        objective="Drag Lyssa down by one position.",
        operation_class=OperationClass.READ_ONLY,
        targets=("sortable",),
        success_criteria=("Lyssa moved down one position",),
        source_request_ref="test",
    )
    context = build_planner_context(
        RunRequest(task_spec=task),
        state,
        BrowserSnapshot(observation, model),
    )

    proposal = PlannerProposalCandidate(
        action_kind=PlannerActionKind.DRAG,
        target_affordance_id="dom_li_3",
        destination_affordance_id="dom_li_2",
    ).bind(context, compilation=default_semantic_compiler_registry().compile(context))

    assert proposal.target_affordance_id == "dom_li_3"
    assert proposal.destination_affordance_id == "dom_li_4"

    fourth_context = context.model_copy(
        update={
            "task_spec": {
                **context.task_spec,
                "objective": "Drag Marianna to the 4th position.",
            }
        }
    )
    fourth = PlannerProposalCandidate(
        action_kind=PlannerActionKind.DRAG,
        target_affordance_id="dom_li_2",
        destination_affordance_id="dom_li_3",
    ).bind(
        fourth_context,
        compilation=default_semantic_compiler_registry().compile(fourth_context),
    )
    assert fourth.target_affordance_id == "dom_li_2"
    assert fourth.destination_affordance_id == "dom_li_4"


def test_generalist_compiles_an_already_sorted_numeric_list_to_submit() -> None:
    model = _authored_dom_adapter().transduce(
        '<li class="ui-sortable-handle">-59</li>'
        '<li class="ui-sortable-handle">-14</li>'
        '<li class="ui-sortable-handle">70</li>'
        '<li class="ui-sortable-handle">70</li>'
        "<button>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    state = StateKernel("task-sort", "Sort numbers")
    state.remember_observation(observation)
    task = TaskSpec(
        task_id="task-sort",
        revision=1,
        objective="Sort the numbers in increasing order, starting with the lowest number at the top.",
        operation_class=OperationClass.READ_ONLY,
        targets=("sortable",),
        success_criteria=("numbers sorted",),
        source_request_ref="test",
    )
    context = build_planner_context(
        RunRequest(task_spec=task),
        state,
        BrowserSnapshot(observation, model),
    )

    proposal = PlannerProposalCandidate(
        action_kind=PlannerActionKind.DRAG,
        target_affordance_id="dom_li_1",
        destination_affordance_id="dom_li_2",
    ).bind(context, compilation=default_semantic_compiler_registry().compile(context))

    assert proposal.action_kind == PlannerActionKind.ACTIVATE
    assert proposal.target_affordance_id == "dom_button_1"
    assert proposal.destination_affordance_id == ""


def test_generalist_compiles_smaller_inside_larger_to_distinct_semantic_endpoints() -> None:
    model = _authored_dom_adapter().transduce(
        '<div draggable="true">small red box</div><div draggable="true">larger blue box</div>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    state = StateKernel("task-box", "Drag box")
    state.remember_observation(observation)
    task = TaskSpec(
        task_id="task-box",
        revision=1,
        objective="Drag the smaller box completely inside the larger box.",
        operation_class=OperationClass.READ_ONLY,
        targets=("boxes",),
        success_criteria=("small box is inside large box",),
        source_request_ref="test",
    )
    context = build_planner_context(
        RunRequest(task_spec=task),
        state,
        BrowserSnapshot(observation, model),
    )

    proposal = PlannerProposalCandidate(
        action_kind=PlannerActionKind.DRAG,
        target_affordance_id="dom_div_1",
        destination_affordance_id="dom_div_1",
    ).bind(context, compilation=default_semantic_compiler_registry().compile(context))

    assert proposal.target_affordance_id == "dom_div_1"
    assert proposal.destination_affordance_id == "dom_div_2"


def test_generalist_compiles_size_relation_from_observed_geometry_semantics() -> None:
    model = _authored_dom_adapter().transduce(
        '<div draggable="true">s</div><div draggable="true">L</div><button>Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    model = replace(
        model,
        affordances=[
            replace(
                item,
                state={**item.state, "relative_size": "smallest" if index == 0 else "largest"},
            )
            for index, item in enumerate(model.affordances)
        ],
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    state = StateKernel("task-box", "Drag box")
    state.remember_observation(observation)
    task = TaskSpec(
        task_id="task-box",
        revision=1,
        objective="Drag the smaller box completely inside the larger box.",
        operation_class=OperationClass.READ_ONLY,
        targets=("boxes",),
        success_criteria=("small box is inside large box",),
        source_request_ref="test",
    )
    context = build_planner_context(
        RunRequest(task_spec=task),
        state,
        BrowserSnapshot(observation, model),
    )

    proposal = PlannerProposalCandidate(
        action_kind=PlannerActionKind.DRAG,
        target_affordance_id="dom_div_2",
        destination_affordance_id="dom_div_1",
    ).bind(context, compilation=default_semantic_compiler_registry().compile(context))

    assert proposal.target_affordance_id == "dom_div_1"
    assert proposal.destination_affordance_id == "dom_div_2"

    state.record_action_progress(
        '{"action_kind":"drag","destination":"dom_div_2","parameters":{},"target":"dom_div_1"}',
        "rev-1",
        verification_passed=True,
        post_page_revision=model.page_revision,
    )
    completed_context = build_planner_context(
        RunRequest(task_spec=task),
        state,
        BrowserSnapshot(observation, model),
    )
    terminal = PlannerProposalCandidate(
        action_kind=PlannerActionKind.DRAG,
        target_affordance_id="dom_div_1",
        destination_affordance_id="dom_div_2",
    ).bind(
        completed_context,
        compilation=default_semantic_compiler_registry().compile(completed_context),
    )

    assert terminal.action_kind == PlannerActionKind.ACTIVATE
    assert terminal.target_affordance_id == "dom_button_1"
    assert terminal.destination_affordance_id == ""

    already_contained = replace(
        model,
        affordances=[
            replace(item, state={**item.state, "inside_largest": True}) if item.id == "dom_div_1" else item
            for item in model.affordances
        ],
    )
    fresh_state = StateKernel("task-box-contained", "Drag box")
    fresh_state.remember_observation(observation)
    contained_context = build_planner_context(
        RunRequest(task_spec=task),
        fresh_state,
        BrowserSnapshot(observation, already_contained),
    )
    contained_terminal = PlannerProposalCandidate(
        action_kind=PlannerActionKind.DRAG,
        target_affordance_id="dom_div_1",
        destination_affordance_id="dom_div_2",
    ).bind(
        contained_context,
        compilation=default_semantic_compiler_registry().compile(contained_context),
    )

    assert contained_terminal.action_kind == PlannerActionKind.ACTIVATE
    assert contained_terminal.target_affordance_id == "dom_button_1"


def test_generalist_derives_terminal_flags_from_action_kind_at_binding() -> None:
    model = _authored_dom_adapter().transduce(
        '<input id="answer">',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    state = StateKernel("task-flags", "Enter answer")
    state.remember_observation(observation)
    task = TaskSpec(
        task_id="task-flags",
        revision=1,
        objective="Enter answer",
        operation_class=OperationClass.READ_ONLY,
        targets=("answer",),
        success_criteria=("answer entered",),
        source_request_ref="test",
    )
    context = build_planner_context(
        RunRequest(task_spec=task),
        state,
        BrowserSnapshot(observation, model),
    )

    effectful = PlannerProposalCandidate(
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id="dom_input_1",
        parameters={"text": "answer"},
        done=True,
        requires_clarification=True,
    ).bind(context)
    terminal = PlannerProposalCandidate(
        action_kind=PlannerActionKind.FINISH,
        done=False,
    ).bind(context)

    assert effectful.done is False
    assert effectful.requires_clarification is False
    assert terminal.done is True


def test_generalist_binds_a_missing_target_only_when_one_compatible_affordance_exists() -> None:
    model = _authored_dom_adapter().transduce(
        '<input id="name">', environment_revision="rev-1", snapshot_id="snapshot-1"
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Enter name")
    state.transition("observing")
    state.remember_observation(observation)
    state.transition("planning")
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Enter name",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("name",),
        success_criteria=("name saved",),
        source_request_ref="request-1",
    )

    @dataclass
    class SingletonCandidateModel:
        provider: str = "fixed"
        model: str = "singleton-candidate"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            return output_schema.model_validate({"action_kind": "type_text", "parameters": {"text": "Ada"}})

    decision = asyncio.run(
        _compatibility_planner(SingletonCandidateModel()).propose_legacy(
            RunRequest(task_spec=task_spec),
            state,
            snapshot,
        )
    )

    assert decision.proposal is not None
    assert decision.proposal.target_affordance_id == "dom_input_1"


def test_generalist_normalizes_select_target_id_to_current_visible_option_label() -> None:
    model = _authored_dom_adapter().transduce(
        '<select><option value="earth">Earth</option></select>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Choose Earth")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Choose Earth",
        operation_class=OperationClass.READ_ONLY,
        targets=("Earth",),
        success_criteria=("Earth selected",),
        source_request_ref="request-1",
    )

    class SelectModel(ProposalModel):
        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            return output_schema.model_validate(
                {
                    "action_kind": "select_option",
                    "target_affordance_id": "dom_select_1",
                    "parameters": {"option": "dom_select_1"},
                }
            )

    decision = asyncio.run(
        _compatibility_planner(SelectModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert decision.proposal is not None
    assert decision.proposal.parameters == {"option": "earth"}


def test_generalist_fills_a_missing_select_option_only_from_one_objective_match() -> None:
    model = _authored_dom_adapter().transduce(
        "<select><option>Earth</option><option>Mars</option></select><button>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Choose Mars and click Submit")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Choose Mars and click Submit",
        operation_class=OperationClass.READ_ONLY,
        targets=("Mars",),
        success_criteria=("Mars selected",),
        source_request_ref="request-1",
    )

    class MissingOptionModel(ProposalModel):
        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            return output_schema.model_validate(
                {"action_kind": "select_option", "target_affordance_id": "dom_select_1"}
            )

    decision = asyncio.run(
        _compatibility_planner(MissingOptionModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert decision.proposal is not None
    assert decision.proposal.parameters == {"option": "Mars"}


def test_generalist_repair_schema_enforces_the_narrowed_action_target_pair() -> None:
    schema = _repair_candidate_schema(["activate"], {"activate": ["dom_button_1"]})

    candidate = schema.model_validate(
        {"action_kind": "activate", "target_affordance_id": "dom_button_1", "parameters": {}}
    )

    assert candidate.action_kind == PlannerActionKind.ACTIVATE
    with pytest.raises(ValidationError):
        schema.model_validate({"action_kind": "select_option", "target_affordance_id": "dom_button_1"})
    with pytest.raises(ValidationError):
        schema.model_validate({"action_kind": "activate"})
    with pytest.raises(ValidationError):
        schema.model_validate(
            {"action_kind": "activate", "target_affordance_id": "dom_button_1", "parameters": {"x": 1}}
        )


def test_generalist_repair_schema_fails_safe_when_constraints_exhaust_targets() -> None:
    schema = _repair_candidate_schema(["point_activate"], {"point_activate": []})

    candidate = schema.model_validate({"action_kind": "ask_user", "target_affordance_id": ""})

    assert candidate.action_kind == PlannerActionKind.ASK_USER
    with pytest.raises(ValidationError):
        schema.model_validate({"action_kind": "point_activate", "target_affordance_id": ""})


def test_generalist_initial_schema_fails_safe_when_constraints_exhaust_actions() -> None:
    schema = _initial_candidate_schema([])

    assert schema.model_validate({"action_kind": "ask_user"}).action_kind == PlannerActionKind.ASK_USER
    with pytest.raises(ValidationError):
        schema.model_validate({"action_kind": "activate"})


def test_generalist_repairs_a_numeric_slider_key_only_toward_the_target() -> None:
    model = _authored_dom_adapter().transduce(
        '<span class="ui-slider-handle" role="slider" tabindex="0">5</span>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    slider = replace(
        model.affordances[0],
        state={"context_text": "5 Submit", "enabled": True, "visible": True},
    )
    model = replace(model, affordances=[slider])
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Select 4 with the slider")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Select 4 with the slider",
        operation_class=OperationClass.READ_ONLY,
        targets=("slider",),
        success_criteria=("slider value is 4",),
        source_request_ref="request-1",
    )

    @dataclass
    class SliderRepairModel:
        provider: str = "fixed"
        model: str = "slider-repair"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None
        calls: int = 0

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del config
            self.calls += 1
            candidate = {
                "action_kind": "press_key",
                "target_affordance_id": "dom_span_1",
                "parameters": {"key": "ArrowRight"},
            }
            del messages
            with pytest.raises(ValidationError):
                output_schema.model_validate(candidate)
            candidate["parameters"] = {"key": "ArrowLeft"}
            return output_schema.model_validate(candidate)

    repair_model = SliderRepairModel()
    decision = asyncio.run(
        _compatibility_planner(repair_model).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert repair_model.calls == 0
    assert decision.proposal is not None
    assert decision.proposal.parameters == {"key": "ArrowLeft"}
    assert decision.planner_context["semantic_compiler"]["compiler_id"] == "typed-incremental-control-v1"


def test_generalist_exposes_submit_when_slider_context_reaches_target() -> None:
    model = _authored_dom_adapter().transduce(
        '<span class="ui-slider-handle" role="slider" tabindex="0">4</span><button>Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    slider = replace(
        model.affordances[0],
        state={"context_text": "4 Submit", "enabled": True, "visible": True},
    )
    model = replace(model, affordances=[slider, model.affordances[1]])
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Select 4 with the slider and hit Submit")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Select 4 with the slider and hit Submit",
        operation_class=OperationClass.READ_ONLY,
        targets=("slider",),
        success_criteria=("submitted",),
        source_request_ref="request-1",
    )

    decision = asyncio.run(
        _compatibility_planner(ProposalModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert decision.proposal is not None
    assert decision.proposal.action_kind == PlannerActionKind.ACTIVATE
    assert decision.proposal.target_affordance_id == "dom_button_1"


@pytest.mark.parametrize(
    ("current", "objective", "expected_key"),
    [
        ("13 Submit", "Select 68 with the slider and hit Submit.", "PageUp"),
        ("79 Submit", "Select 26 with the slider and hit Submit.", "PageDown"),
    ],
)
def test_generalist_uses_page_key_for_large_slider_distance(
    current: str,
    objective: str,
    expected_key: str,
) -> None:
    model = _authored_dom_adapter().transduce(
        '<span class="ui-slider-handle" role="slider" tabindex="0"></span>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    slider = replace(
        model.affordances[0],
        state={"context_text": current, "enabled": True, "visible": True},
    )
    model = replace(model, affordances=[slider])
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", objective)
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("slider",),
        success_criteria=("slider target reached",),
        source_request_ref="request-1",
    )
    context = GeneralistLMPlanner(ProposalModel()).build_context(RunRequest(task_spec=task_spec), state, snapshot)

    permitted, targets, key = _slider_progress_constraints(
        context,
        ["press_key"],
        {"press_key": ["dom_span_1"]},
    )

    assert permitted == ["press_key"]
    assert targets == {"press_key": ["dom_span_1"]}
    assert key == expected_key


def test_generalist_extracts_slider_target_when_objective_contains_checkbox_ordinal() -> None:
    model = _authored_dom_adapter().transduce(
        '<span class="ui-slider-handle" role="slider" tabindex="0">-9</span>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    slider = replace(model.affordances[0], state={"context_text": "-9", "enabled": True, "visible": True})
    model = replace(model, affordances=[slider])
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    objective = "Select -3 with the slider, click the 1st checkbox, then hit Submit."
    state = StateKernel("task-1", objective)
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("slider",),
        success_criteria=("slider value is -3",),
        source_request_ref="request-1",
    )

    @dataclass
    class SliderRepairModel:
        provider: str = "fixed"
        model: str = "slider-repair"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None
        calls: int = 0

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            self.calls += 1
            candidate = {
                "action_kind": "press_key",
                "target_affordance_id": "dom_span_1",
                "parameters": {"key": "ArrowLeft"},
            }
            with pytest.raises(ValidationError):
                output_schema.model_validate(candidate)
            candidate["parameters"] = {"key": "ArrowRight"}
            return output_schema.model_validate(candidate)

    repair_model = SliderRepairModel()
    decision = asyncio.run(
        _compatibility_planner(repair_model).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert repair_model.calls == 0
    assert decision.proposal is not None
    assert decision.proposal.parameters == {"key": "ArrowRight"}
    assert decision.planner_context["semantic_compiler"]["compiler_id"] == "typed-incremental-control-v1"


def test_generalist_binds_copy_paste_to_exact_source_value_and_destination() -> None:
    model = _authored_dom_adapter().transduce(
        "<textarea>Trim-sensitive text </textarea><input type='text'><button>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    affordances = []
    for item in model.affordances:
        state = dict(item.state)
        if state["element_tag"] == "textarea":
            state["control_value"] = "Trim-sensitive text "
        elif state["element_tag"] == "input":
            state["control_value"] = ""
        affordances.append(replace(item, state=state))
    model = replace(model, affordances=affordances)
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    objective = "Copy the text in the textarea below, paste it into the textbox and press Submit."
    state = StateKernel("task-1", objective)
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("textbox",),
        success_criteria=("submitted",),
        source_request_ref="request-1",
    )

    @dataclass
    class CopyModel:
        provider: str = "fixed"
        model: str = "copy"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            with pytest.raises(ValidationError):
                output_schema.model_validate(
                    {
                        "action_kind": "type_text",
                        "target_affordance_id": "dom_textarea_1",
                        "parameters": {"text": "Trim-sensitive text"},
                    }
                )
            return output_schema.model_validate(
                {
                    "action_kind": "type_text",
                    "target_affordance_id": "dom_input_1",
                    "parameters": {"text": "Trim-sensitive text "},
                }
            )

    planner = _compatibility_planner(CopyModel())
    decision = asyncio.run(planner.propose_legacy(RunRequest(task_spec=task_spec), state, snapshot))

    assert decision.proposal is not None
    assert decision.proposal.target_affordance_id == "dom_input_1"
    assert decision.proposal.parameters == {"text": "Trim-sensitive text "}

    context = planner.build_context(RunRequest(task_spec=task_spec), state, snapshot)
    satisfied_context = context.model_copy(update={"satisfied_action_targets": {"type_text": ("dom_input_1",)}})
    permitted, targets, value = _copy_text_constraints(
        satisfied_context,
        ["activate", "type_text"],
        {"activate": ["dom_button_1"], "type_text": ["dom_textarea_1", "dom_input_1"]},
    )

    assert permitted == ["activate"]
    assert targets == {"activate": ["dom_button_1"]}
    assert value == ""

    scroll_summary = context.affordances[0].model_copy(
        update={
            "id": "dom_textarea_1_scroll",
            "role": "scroll_region",
            "action": "press",
            "state": {
                "scrollable": True,
                "scroll_top": 20,
                "scroll_height": 300,
                "client_height": 100,
            },
        }
    )
    non_scroll_context = satisfied_context.model_copy(
        update={"affordances": (*satisfied_context.affordances, scroll_summary)}
    )
    permitted, targets, key = _scroll_progress_constraints(
        non_scroll_context,
        ["activate", "press_key"],
        {
            "activate": ["dom_button_1"],
            "press_key": ["dom_textarea_1_scroll"],
        },
    )

    assert permitted == ["activate"]
    assert targets == {"activate": ["dom_button_1"]}
    assert key == ""


def test_generalist_binds_ordinal_copy_source_and_exposes_only_submit_after_destination_matches() -> None:
    model = _authored_dom_adapter().transduce(
        "<textarea>first</textarea><textarea>second</textarea><textarea>third exact </textarea>"
        "<input type='text'><button>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    source_values = iter(("first", "second", "third exact "))
    affordances = []
    for item in model.affordances:
        state = dict(item.state)
        if state.get("element_tag") == "textarea":
            state["control_value"] = next(source_values)
        elif state.get("element_tag") == "input":
            state["control_value"] = ""
        affordances.append(replace(item, state=state))
    model = replace(model, affordances=affordances)
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    objective = "Copy the text from the 3rd text area below and paste it into the text input, then press Submit."
    state = StateKernel("task-ordinal-copy", objective)
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-ordinal-copy",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("third text area", "text input"),
        success_criteria=("submitted",),
        source_request_ref="test",
    )
    context = build_planner_context(RunRequest(task_spec=task_spec), state, BrowserSnapshot(observation, model))
    permitted, targets, value = _copy_text_constraints(
        context,
        ["activate", "press_key", "type_text"],
        {
            "activate": ["dom_button_1"],
            "press_key": [],
            "type_text": ["dom_textarea_1", "dom_textarea_2", "dom_textarea_3", "dom_input_1"],
        },
    )

    assert permitted == ["type_text"]
    assert targets == {"type_text": ["dom_input_1"]}
    assert value == "third exact "

    completed = context.model_copy(
        update={
            "affordances": tuple(
                item.model_copy(update={"state": {**item.state, "control_value": "third exact "}})
                if item.id == "dom_input_1"
                else item
                for item in context.affordances
            )
        }
    )
    permitted, targets = _restrict_action_kinds_to_objective(
        completed,
        ["activate", "press_key", "type_text"],
        {
            "activate": ["dom_button_1"],
            "press_key": ["dom_textarea_1_scroll", "dom_textarea_2_scroll", "dom_textarea_3_scroll"],
            "type_text": ["dom_textarea_1", "dom_textarea_2", "dom_textarea_3", "dom_input_1"],
        },
    )

    assert permitted == ["activate"]
    assert targets == {"activate": ["dom_button_1"]}


def test_generalist_ordinal_copy_takes_priority_over_scroll_progress() -> None:
    model = _authored_dom_adapter().transduce(
        "<textarea>first</textarea><textarea>second</textarea><textarea>third exact </textarea>"
        "<input type='text'><button>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    source_values = iter(("first", "second", "third exact "))
    affordances = []
    for item in model.affordances:
        state = dict(item.state)
        if state.get("element_tag") == "textarea":
            state.update(
                {
                    "control_value": next(source_values),
                    "scroll_top": 0,
                    "scroll_height": 200,
                    "client_height": 50,
                }
            )
        elif state.get("element_tag") == "input":
            state["control_value"] = ""
        affordances.append(replace(item, state=state))
    model = replace(model, affordances=affordances)
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    objective = "Copy the text from the 3rd text area below and paste it into the text input, then press Submit."
    state = StateKernel("task-ordinal-copy", objective)
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-ordinal-copy",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("third text area", "text input"),
        success_criteria=("submitted",),
        source_request_ref="test",
    )

    @dataclass
    class CopyModel:
        provider: str = "fixed"
        model: str = "copy"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, output_schema, config
            raise AssertionError("exact copy transfer must bypass the language model")

    decision = asyncio.run(
        _compatibility_planner(CopyModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert decision.proposal is not None
    assert decision.proposal.action_kind == PlannerActionKind.TYPE_TEXT
    assert decision.proposal.target_affordance_id == "dom_input_1"
    assert decision.proposal.parameters == {"text": "third exact "}


def test_generalist_binds_table_field_to_adjacent_value_and_then_submit() -> None:
    model = _authored_dom_adapter().transduce(
        '<table><tr><td data-runtime-handle="header" data-runtime-interactive="1">Gender</td>'
        '<td data-runtime-handle="value" data-runtime-interactive="1">Male</td></tr></table>'
        '<input data-runtime-handle="target" type="text"><button data-runtime-handle="submit">Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    objective = "Enter the value of Gender into the text field and press Submit."
    state = StateKernel("task-1", objective)
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("text field",),
        success_criteria=("submitted",),
        source_request_ref="request-1",
    )
    context = GeneralistLMPlanner(ProposalModel()).build_context(RunRequest(task_spec=task_spec), state, snapshot)
    compatible = {
        "activate": ["dom_td_1", "dom_td_2", "dom_button_1"],
        "type_text": ["dom_input_1"],
    }

    permitted, targets, constrained, value = _table_value_entry_constraints(
        context,
        ["activate", "type_text"],
        compatible,
    )

    assert permitted == ["type_text"]
    assert targets == {"type_text": ["dom_input_1"]}
    assert constrained is True
    assert value == "Male"

    satisfied = context.model_copy(update={"satisfied_action_targets": {"type_text": ("dom_input_1",)}})
    permitted, targets, constrained, value = _table_value_entry_constraints(
        satisfied,
        ["activate", "type_text"],
        compatible,
    )

    assert permitted == ["activate"]
    assert targets == {"activate": ["dom_button_1"]}
    assert constrained is True
    assert value == ""


def test_generalist_binds_one_isolated_visible_value_for_deictic_text_entry() -> None:
    model = _authored_dom_adapter().transduce(
        "<input type='text'><button>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
        metadata={"visible_text": "LO4e\n Submit"},
    )
    snapshot = BrowserSnapshot(observation, model)
    objective = "Type the text below into the text field and press Submit."
    state = StateKernel("task-1", objective)
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("text field",),
        success_criteria=("submitted",),
        source_request_ref="request-1",
    )

    @dataclass
    class VisibleTextModel:
        provider: str = "fixed"
        model: str = "visible-text"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            with pytest.raises(ValidationError):
                output_schema.model_validate(
                    {
                        "action_kind": "type_text",
                        "target_affordance_id": "dom_input_1",
                        "parameters": {"text": "text-transform"},
                    }
                )
            return output_schema.model_validate(
                {
                    "action_kind": "type_text",
                    "target_affordance_id": "dom_input_1",
                    "parameters": {"text": "LO4e"},
                }
            )

    decision = asyncio.run(
        _compatibility_planner(VisibleTextModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert decision.proposal is not None
    assert decision.proposal.parameters == {"text": "LO4e"}


def test_generalist_keeps_long_text_suffix_and_writes_only_the_destination() -> None:
    source_value = ("alpha beta gamma " * 40) + "finalword."
    model = _authored_dom_adapter().transduce(
        f"<textarea>{source_value}</textarea><input type='text'><button>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    affordances = []
    for item in model.affordances:
        state = dict(item.state)
        if state["element_tag"] == "textarea":
            state["control_value"] = _bounded_control_value(source_value)
            state["control_value_prefix"] = source_value[:240]
            state["control_value_suffix"] = source_value[-240:]
        elif state["element_tag"] == "input":
            state["control_value"] = ""
        affordances.append(replace(item, state=state))
    model = replace(model, affordances=affordances)
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    objective = "Find the last word in the text area, enter it into the text field and hit Submit."
    state = StateKernel("task-1", objective)
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("text field",),
        success_criteria=("submitted",),
        source_request_ref="request-1",
    )

    @dataclass
    class RelationalTextModel:
        provider: str = "fixed"
        model: str = "relational-text"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del config
            context = __import__("json").loads(messages[1].content)
            source = next(item for item in context["affordances"] if item["id"] == "dom_textarea_1")
            assert len(source["state"]["control_value"]) <= 240
            assert source["state"]["control_value"].endswith("finalword.")
            assert source["state"]["control_value_suffix"].endswith("finalword.")
            with pytest.raises(ValidationError):
                output_schema.model_validate(
                    {
                        "action_kind": "type_text",
                        "target_affordance_id": "dom_textarea_1",
                        "parameters": {"text": "finalword"},
                    }
                )
            return output_schema.model_validate(
                {
                    "action_kind": "type_text",
                    "target_affordance_id": "dom_input_1",
                    "parameters": {"text": "finalword"},
                }
            )

    decision = asyncio.run(
        _compatibility_planner(RelationalTextModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert decision.proposal is not None
    assert decision.proposal.target_affordance_id == "dom_input_1"
    assert decision.proposal.parameters == {"text": "finalword"}


@pytest.mark.parametrize(
    ("objective", "scroll_top", "required_key"),
    [
        ("Scroll the textarea to the top of the text hit submit.", 120, "Control+Home"),
        ("Scroll the textarea to the bottom of the text hit submit.", 120, "Control+End"),
    ],
)
def test_generalist_binds_textarea_scroll_to_exact_boundary_key(
    objective: str,
    scroll_top: int,
    required_key: str,
) -> None:
    model = _authored_dom_adapter().transduce(
        "<textarea data-runtime-handle='source'>Long text</textarea><button data-runtime-handle='submit'>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    source = model.affordances[0]
    scroll_region = replace(
        source,
        id=f"{source.id}_scroll",
        role="scroll_region",
        action="press",
        state={
            "enabled": True,
            "visible": True,
            "element_tag": "textarea",
            "scrollable": True,
            "scroll_top": scroll_top,
            "scroll_height": 300,
            "client_height": 100,
        },
    )
    model = replace(model, affordances=[*model.affordances, scroll_region])
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", objective)
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("textarea",),
        success_criteria=("submitted",),
        source_request_ref="request-1",
    )

    @dataclass
    class ScrollModel:
        provider: str = "fixed"
        model: str = "scroll"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            for invalid in (
                {
                    "action_kind": "type_text",
                    "target_affordance_id": "dom_textarea_1",
                    "parameters": {"text": "Long text"},
                },
                {
                    "action_kind": "press_key",
                    "target_affordance_id": "dom_textarea_1_scroll",
                    "parameters": {"key": "ArrowDown"},
                },
            ):
                with pytest.raises(ValidationError):
                    output_schema.model_validate(invalid)
            return output_schema.model_validate(
                {
                    "action_kind": "press_key",
                    "target_affordance_id": "dom_textarea_1_scroll",
                    "parameters": {"key": required_key},
                }
            )

    decision = asyncio.run(
        _compatibility_planner(ScrollModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert decision.proposal is not None
    assert decision.proposal.target_affordance_id == "dom_textarea_1_scroll"
    assert decision.proposal.parameters == {"key": required_key}


@pytest.mark.parametrize(
    ("objective", "scroll_top"),
    [
        ("Scroll the textarea to the top of the text hit submit.", 0),
        ("Scroll the textarea to the bottom of the text hit submit.", 198),
    ],
)
def test_generalist_exposes_submit_after_textarea_reaches_scroll_boundary(
    objective: str,
    scroll_top: int,
) -> None:
    model = _authored_dom_adapter().transduce(
        "<textarea data-runtime-handle='source'>Long text</textarea><button data-runtime-handle='submit'>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    source = model.affordances[0]
    scroll_region = replace(
        source,
        id=f"{source.id}_scroll",
        role="scroll_region",
        action="press",
        state={
            "enabled": True,
            "visible": True,
            "element_tag": "textarea",
            "scrollable": True,
            "scroll_top": scroll_top,
            "scroll_height": 300,
            "client_height": 100,
        },
    )
    model = replace(model, affordances=[*model.affordances, scroll_region])
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", objective)
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective=objective,
        operation_class=OperationClass.READ_ONLY,
        targets=("textarea",),
        success_criteria=("submitted",),
        source_request_ref="request-1",
    )

    @dataclass
    class SubmitModel:
        provider: str = "fixed"
        model: str = "submit"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            for action_kind in ("type_text", "press_key"):
                with pytest.raises(ValidationError):
                    output_schema.model_validate(
                        {
                            "action_kind": action_kind,
                            "target_affordance_id": "dom_textarea_1",
                        }
                    )
            return output_schema.model_validate(
                {
                    "action_kind": "activate",
                    "target_affordance_id": "dom_button_1",
                }
            )

    decision = asyncio.run(
        _compatibility_planner(SubmitModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert decision.proposal is not None
    assert decision.proposal.action_kind == PlannerActionKind.ACTIVATE
    assert decision.proposal.target_affordance_id == "dom_button_1"


def test_only_compatibility_repair_forces_autocomplete_prefix_task_grammar() -> None:
    model = _authored_dom_adapter().transduce(
        '<input id="tags" class="ui-autocomplete-input">',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", 'Enter an item that starts with "Com"')
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective='Enter an item that starts with "Com"',
        operation_class=OperationClass.READ_ONLY,
        targets=("item",),
        success_criteria=("matching item entered",),
        source_request_ref="request-1",
    )

    @dataclass
    class AutocompleteRepairModel:
        provider: str = "fixed"
        model: str = "autocomplete-repair"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None
        calls: int = 0

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del config
            self.calls += 1
            candidate = {
                "action_kind": "type_text",
                "target_affordance_id": "dom_input_1",
                "parameters": {"text": "Computer"},
            }
            if self.calls == 1:
                return output_schema.model_validate(candidate)
            assert "proposal_autocomplete_requires_prefix" in messages[-1].content
            with pytest.raises(ValidationError):
                output_schema.model_validate(candidate)
            candidate["parameters"] = {"text": "Com"}
            return output_schema.model_validate(candidate)

    repair_model = AutocompleteRepairModel()
    strict = asyncio.run(GeneralistLMPlanner(repair_model).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot))

    assert repair_model.calls == 0
    assert strict.proposal is None
    assert strict.reason == "no_active_step_action_choice"

    repair_model = AutocompleteRepairModel()
    decision = asyncio.run(
        GeneralistLMPlanner(
            repair_model,
            planner_profile=GeneralistPlannerProfile.HISTORICAL_COMPATIBILITY,
            semantic_compilers=SemanticCompilerRegistry.disabled(),
        ).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert repair_model.calls == 2
    assert decision.proposal is not None
    assert decision.proposal.parameters == {"text": "Com"}


def test_strict_taskspec_prefix_is_enforced_by_initial_candidate_schema() -> None:
    model = _authored_dom_adapter().transduce(
        '<input id="tags" class="ui-autocomplete-input">',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Enter an item starting with Com")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Enter an item starting with Com",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("item",),
        semantic_value_constraints=(
            SemanticValueConstraint(
                relation=SemanticValueRelation.PREFIX,
                value="Com",
                target="item",
                source_ref="request-1",
            ),
        ),
        success_criteria=("matching item entered",),
        source_request_ref="request-1",
    )

    @dataclass
    class PrefixSchemaModel:
        provider: str = "fixed"
        model: str = "prefix-schema"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            return output_schema.model_validate(
                {
                    "action_kind": "type_text",
                    "target_affordance_id": "dom_input_1",
                    "parameters": {"text": "Com"},
                }
            )

    decision = asyncio.run(
        _compatibility_planner(PrefixSchemaModel()).propose_legacy(
            RunRequest(task_spec=task_spec), state, snapshot
        )
    )

    assert decision.proposal is not None
    assert decision.proposal.parameters == {"text": "Com"}


def test_strict_planner_does_not_guess_exact_value_when_no_actionchoice_exists() -> None:
    model = _authored_dom_adapter().transduce(
        '<input id="tt" type="date"><button>Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Enter 01/18/2019 as the date and hit submit.")
    state.remember_observation(observation)
    state.task_plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=1,
        plan_version=1,
        based_on_state_version=state.version,
        generated_by=TaskPlanSource.RULE,
        subgoals=(
            SubgoalSpec(
                subgoal_id="date-field:value",
                objective="date_field equals 01/18/2019",
                interaction=make_interaction('date_field'),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.TYPE_TEXT,
                outcome=SubgoalOutcome(
                    subject="date_field",
                    relation=SubgoalOutcomeRelation.EQUALS,
                    value="01/18/2019",
                ),
            ),
        ),
    )
    state.task_progress = PlanProgress(active_subgoal_id="date-field:value")
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Enter 01/18/2019 as the date and hit submit.",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("date_field",),
        semantic_value_constraints=(
            SemanticValueConstraint(
                relation=SemanticValueRelation.EXACT,
                value="01/18/2019",
                target="date_field",
                source_ref="request-1",
            ),
        ),
        success_criteria=("date_field = '01/18/2019'",),
        source_request_ref="request-1",
    )

    @dataclass
    class EmptyClarificationModel:
        provider: str = "fixed"
        model: str = "empty-clarification"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            return output_schema.model_validate({"action_kind": "ask_user"})

    decision = asyncio.run(
        GeneralistLMPlanner(EmptyClarificationModel()).propose_legacy(
            RunRequest(task_spec=task_spec),
            state,
            snapshot,
        )
    )

    _assert_strict_semantic_resolver_retired(decision)


def test_strict_planner_does_not_guess_unique_requested_button_without_actionchoice() -> None:
    model = _authored_dom_adapter().transduce(
        "<button>No</button><button>OK</button><button>Submit</button><input>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Click on the 'No' button.")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Click on the 'No' button.",
        operation_class=OperationClass.NAVIGATION,
        targets=("button[text()='No']",),
        success_criteria=("Clicked on the 'No' button.",),
        source_request_ref="request-1",
    )

    decision = asyncio.run(
        GeneralistLMPlanner(EmptyClarificationModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    _assert_strict_semantic_resolver_retired(decision)


def test_strict_planner_does_not_guess_selected_option_submit_without_actionchoice() -> None:
    model = _authored_dom_adapter().transduce(
        '<select><option selected>Ertha</option><option>Merridie</option></select><button>Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    model = replace(
        model,
        affordances=[
            replace(item, state={**item.state, "selected_options": ["Ertha"]})
            if item.id == "dom_select_1"
            else item
            for item in model.affordances
        ],
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Select Ertha from the list and click Submit.")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Select Ertha from the list and click Submit.",
        operation_class=OperationClass.NAVIGATION,
        targets=("Ertha",),
        success_criteria=("Ertha is selected from the list and Submit is clicked.",),
        source_request_ref="request-1",
    )

    decision = asyncio.run(
        GeneralistLMPlanner(EmptyClarificationModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    _assert_strict_semantic_resolver_retired(decision)


def test_strict_planner_does_not_guess_target_derived_text_value_without_actionchoice() -> None:
    model = _authored_dom_adapter().transduce(
        "<input id='tt' type='text'><button>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Enter 'Myron' into the text field and press Submit.")
    state.remember_observation(observation)
    state.task_plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=1,
        plan_version=1,
        based_on_state_version=state.version,
        generated_by=TaskPlanSource.RULE,
        subgoals=(
            SubgoalSpec(
                subgoal_id="text-field:changed",
                objective="text_field:Myron has changed",
                interaction=make_interaction('text_field:Myron'),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.TYPE_TEXT,
                outcome=SubgoalOutcome(
                    subject="text_field:Myron",
                    relation=SubgoalOutcomeRelation.HAS_CHANGED,
                ),
            ),
        ),
    )
    state.task_progress = PlanProgress(active_subgoal_id="text-field:changed")
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Enter 'Myron' into the text field and press Submit.",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("text_field:Myron",),
        success_criteria=("Text field contains 'Myron' and is focused.",),
        source_request_ref="request-1",
    )

    decision = asyncio.run(
        GeneralistLMPlanner(EmptyClarificationModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    _assert_strict_semantic_resolver_retired(decision)


def test_strict_planner_does_not_guess_slider_press_key_without_actionchoice() -> None:
    model = _authored_dom_adapter().transduce(
        '<span class="ui-slider-handle" role="slider" tabindex="0">0</span><button>Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    slider = replace(
        model.affordances[0],
        state={"context_text": "0 Submit", "enabled": True, "visible": True},
    )
    model = replace(model, affordances=[slider, model.affordances[1]])
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Select 7 with the slider, click the 3rd checkbox, then hit Submit.")
    state.remember_observation(observation)
    state.task_plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=1,
        plan_version=1,
        based_on_state_version=state.version,
        generated_by=TaskPlanSource.RULE,
        subgoals=(
            SubgoalSpec(
                subgoal_id="slider-value:changed",
                objective="slider_value_7 has changed",
                interaction=make_interaction('slider_value_7'),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.PRESS_KEY,
                outcome=SubgoalOutcome(
                    subject="slider_value_7",
                    relation=SubgoalOutcomeRelation.HAS_CHANGED,
                ),
            ),
        ),
    )
    state.task_progress = PlanProgress(active_subgoal_id="slider-value:changed")
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Select 7 with the slider, click the 3rd checkbox, then hit Submit.",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("slider_value_7",),
        success_criteria=("slider_value_7_selected",),
        source_request_ref="request-1",
    )

    decision = asyncio.run(
        GeneralistLMPlanner(EmptyClarificationModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    _assert_strict_semantic_resolver_retired(decision)


def test_strict_planner_does_not_override_explanatory_slider_clarification_without_actionchoice() -> None:
    @dataclass
    class SliderClarificationModel:
        provider: str = "fixed"
        model: str = "slider-clarification"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self,
            messages: Sequence[ModelMessage],
            output_schema: type[T],
            config: ModelConfig,
        ) -> T:
            del messages, config
            return output_schema.model_validate(
                {
                    "action_kind": "ask_user",
                    "reason": "The slider value is -7 instead of the required -3.",
                }
            )

    model = _authored_dom_adapter().transduce(
        '<span class="ui-slider-handle" role="slider" tabindex="0">-7</span><button>Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    slider = replace(
        model.affordances[0],
        state={"context_text": "-7", "enabled": True, "visible": True},
    )
    model = replace(model, affordances=[slider, model.affordances[1]])
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Select -3 with the slider, click the 1st checkbox, then hit Submit.")
    state.remember_observation(observation)
    state.task_plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=1,
        plan_version=1,
        based_on_state_version=state.version,
        generated_by=TaskPlanSource.RULE,
        subgoals=(
            SubgoalSpec(
                subgoal_id="slider-value:changed",
                objective="slider_value has changed",
                interaction=make_interaction('slider_value'),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.PRESS_KEY,
                outcome=SubgoalOutcome(
                    subject="slider_value",
                    relation=SubgoalOutcomeRelation.HAS_CHANGED,
                ),
            ),
        ),
    )
    state.task_progress = PlanProgress(active_subgoal_id="slider-value:changed")
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Select -3 with the slider, click the 1st checkbox, then hit Submit.",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("slider_value",),
        success_criteria=("slider_value = -3",),
        source_request_ref="request-1",
    )

    decision = asyncio.run(
        GeneralistLMPlanner(SliderClarificationModel()).propose_legacy(
            RunRequest(task_spec=task_spec),
            state,
            snapshot,
        )
    )

    _assert_strict_semantic_resolver_retired(decision)


def test_strict_planner_advances_from_verified_slider_to_requested_checkbox() -> None:
    model = _authored_dom_adapter().transduce(
        (
            '<span class="ui-slider-handle" role="slider" tabindex="0">7</span>'
            '<input id="one" type="checkbox">'
            '<input id="two" type="checkbox">'
            '<input id="three" type="checkbox">'
            "<button>Submit</button>"
        ),
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    slider = replace(
        model.affordances[0],
        state={"context_text": "7 Submit", "enabled": True, "visible": True},
    )
    model = replace(model, affordances=[slider, *model.affordances[1:]])
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Select 7 with the slider, click the 3rd checkbox, then hit Submit.")
    state.remember_observation(observation)
    state.task_plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=1,
        plan_version=1,
        based_on_state_version=state.version,
        generated_by=TaskPlanSource.RULE,
        subgoals=(
            SubgoalSpec(
                subgoal_id="slider-value:changed",
                objective="slider_value_7 has changed",
                interaction=make_interaction('slider_value_7'),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.PRESS_KEY,
                outcome=SubgoalOutcome(
                    subject="slider_value_7",
                    relation=SubgoalOutcomeRelation.HAS_CHANGED,
                ),
            ),
        ),
    )
    state.task_progress = PlanProgress(active_subgoal_id="slider-value:changed")
    state.record_planner_proposal(
        {
            "proposal_id": "previous",
            "action_kind": "press_key",
            "target_affordance_id": "dom_span_1",
            "expected_effects": ["slider_value_7 has changed"],
        }
    )
    from affordance_runtime.verification import VerificationReport, VerificationStatus

    state.latest_verification = VerificationReport(VerificationStatus.PASSED)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Select 7 with the slider, click the 3rd checkbox, then hit Submit.",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("slider_value_7", "checkbox_3_state", "submit_button_state"),
        success_criteria=("slider_value_7_selected", "checkbox_3_checked", "submit_button_clicked"),
        source_request_ref="request-1",
    )

    decision = asyncio.run(
        GeneralistLMPlanner(EmptyClarificationModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    _assert_strict_semantic_resolver_retired(decision)


def test_strict_planner_stops_negative_slider_at_target_before_checkbox() -> None:
    model = _authored_dom_adapter().transduce(
        (
            '<span class="ui-slider-handle" role="slider" tabindex="0">-3</span>'
            '<input id="one" type="checkbox">'
            '<input id="two" type="checkbox">'
            '<input id="three" type="checkbox">'
            "<button>Submit</button>"
        ),
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    slider = replace(
        model.affordances[0],
        state={"context_text": "-3 Submit", "enabled": True, "visible": True},
    )
    model = replace(model, affordances=[slider, *model.affordances[1:]])
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Select -3 with the slider, click the 1st checkbox, then hit Submit.")
    state.remember_observation(observation)
    state.task_plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=1,
        plan_version=1,
        based_on_state_version=state.version,
        generated_by=TaskPlanSource.RULE,
        subgoals=(
            SubgoalSpec(
                subgoal_id="slider-value:changed",
                objective="slider_value has changed",
                interaction=make_interaction('slider_value'),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.PRESS_KEY,
                outcome=SubgoalOutcome(
                    subject="slider_value",
                    relation=SubgoalOutcomeRelation.HAS_CHANGED,
                ),
            ),
        ),
    )
    state.task_progress = PlanProgress(active_subgoal_id="slider-value:changed")
    state.record_planner_proposal(
        {
            "proposal_id": "previous",
            "action_kind": "press_key",
            "target_affordance_id": "dom_span_1",
            "expected_effects": ["slider_value has changed"],
        }
    )
    from affordance_runtime.verification import VerificationReport, VerificationStatus

    state.latest_verification = VerificationReport(VerificationStatus.PASSED)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Select -3 with the slider, click the 1st checkbox, then hit Submit.",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("slider_value", "checkbox_1_state", "submit_button"),
        success_criteria=("slider_value = -3", "checkbox_1_state = checked", "submit_button is interactable"),
        source_request_ref="request-1",
    )

    decision = asyncio.run(
        GeneralistLMPlanner(EmptyClarificationModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    _assert_strict_semantic_resolver_retired(decision)


def test_strict_planner_advances_from_completed_checkbox_to_terminal_submit() -> None:
    model = _authored_dom_adapter().transduce(
        (
            '<span class="ui-slider-handle" role="slider" tabindex="0">7</span>'
            '<input id="one" type="checkbox">'
            '<input id="two" type="checkbox">'
            '<input id="three" type="checkbox" checked>'
            "<button>Submit</button>"
        ),
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    slider = replace(
        model.affordances[0],
        state={"context_text": "7 Submit", "enabled": True, "visible": True},
    )
    checked = replace(
        model.affordances[3],
        state={**model.affordances[3].state, "checked": True},
    )
    model = replace(
        model,
        affordances=[slider, model.affordances[1], model.affordances[2], checked, model.affordances[4]],
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Select 7 with the slider, click the 3rd checkbox, then hit Submit.")
    state.remember_observation(observation)
    state.task_plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=1,
        plan_version=1,
        based_on_state_version=state.version,
        generated_by=TaskPlanSource.RULE,
        subgoals=(
            SubgoalSpec(
                subgoal_id="checkbox:checked",
                objective="checkbox_3_state has changed",
                interaction=make_interaction('checkbox_3_state'),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.ACTIVATE,
                outcome=SubgoalOutcome(
                    subject="checkbox_3_state",
                    relation=SubgoalOutcomeRelation.HAS_CHANGED,
                ),
            ),
        ),
    )
    state.task_progress = PlanProgress(active_subgoal_id="checkbox:checked")
    state.record_planner_proposal(
        {
            "proposal_id": "previous",
            "action_kind": "activate",
            "target_affordance_id": "dom_input_3",
            "expected_effects": ["checkbox_3_state has changed"],
        }
    )
    from affordance_runtime.verification import VerificationReport, VerificationStatus

    state.latest_verification = VerificationReport(VerificationStatus.PASSED)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Select 7 with the slider, click the 3rd checkbox, then hit Submit.",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("slider_value_7", "checkbox_3_state", "submit_button_state"),
        success_criteria=("slider_value_7_selected", "checkbox_3_checked", "submit_button_clicked"),
        source_request_ref="request-1",
    )

    decision = asyncio.run(
        GeneralistLMPlanner(EmptyClarificationModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    _assert_strict_semantic_resolver_retired(decision)


def test_strict_planner_submits_after_checked_checkbox_without_verified_effect_text() -> None:
    model = _authored_dom_adapter().transduce(
        (
            '<span class="ui-slider-handle" role="slider" tabindex="0">-3</span>'
            '<input id="one" type="checkbox" checked>'
            '<input id="two" type="checkbox">'
            '<input id="three" type="checkbox">'
            "<button>Submit</button>"
        ),
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    slider = replace(
        model.affordances[0],
        state={"context_text": "-3", "enabled": True, "visible": True},
    )
    checked = replace(
        model.affordances[1],
        state={**model.affordances[1].state, "checked": True},
    )
    model = replace(model, affordances=[slider, checked, *model.affordances[2:]])
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Select -3 with the slider, click the 1st checkbox, then hit Submit.")
    state.remember_observation(observation)
    state.task_plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=1,
        plan_version=1,
        based_on_state_version=state.version,
        generated_by=TaskPlanSource.RULE,
        subgoals=(
            SubgoalSpec(
                subgoal_id="submit",
                objective="submit_button is completed",
                interaction=make_interaction('submit_button'),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.ACTIVATE,
                outcome=SubgoalOutcome(
                    subject="submit_button",
                    relation=SubgoalOutcomeRelation.IS_COMPLETED,
                ),
            ),
        ),
    )
    state.task_progress = PlanProgress(active_subgoal_id="submit")
    state.record_planner_proposal(
        {
            "proposal_id": "previous-checkbox",
            "action_kind": "activate",
            "target_affordance_id": "dom_input_1",
            "expected_effects": [],
        }
    )
    from affordance_runtime.verification import VerificationReport, VerificationStatus

    state.latest_verification = VerificationReport(VerificationStatus.PASSED)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Select -3 with the slider, click the 1st checkbox, then hit Submit.",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("slider_value", "checkbox_1_state", "submit_button"),
        success_criteria=("slider_value = -3", "checkbox_1_state = checked", "submit_button is interactable"),
        source_request_ref="request-1",
    )

    decision = asyncio.run(
        GeneralistLMPlanner(EmptyClarificationModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    _assert_strict_semantic_resolver_retired(decision)


def test_strict_planner_submits_after_verified_checkbox_even_when_active_subgoal_is_stale() -> None:
    model = _authored_dom_adapter().transduce(
        (
            '<span class="ui-slider-handle" role="slider" tabindex="0">7</span>'
            '<input id="one" type="checkbox">'
            '<input id="two" type="checkbox">'
            '<input id="three" type="checkbox" checked>'
            "<button>Submit</button>"
        ),
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    slider = replace(
        model.affordances[0],
        state={"context_text": "7 Submit", "enabled": True, "visible": True},
    )
    checked = replace(
        model.affordances[3],
        state={**model.affordances[3].state, "checked": True},
    )
    model = replace(
        model,
        affordances=[slider, model.affordances[1], model.affordances[2], checked, model.affordances[4]],
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Select 7 with the slider, click the 3rd checkbox, then hit Submit.")
    state.remember_observation(observation)
    state.task_plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=1,
        plan_version=1,
        based_on_state_version=state.version,
        generated_by=TaskPlanSource.RULE,
        subgoals=(
            SubgoalSpec(
                subgoal_id="slider-value:changed",
                objective="slider_value_7 has changed",
                interaction=make_interaction('slider_value_7'),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.PRESS_KEY,
                outcome=SubgoalOutcome(
                    subject="slider_value_7",
                    relation=SubgoalOutcomeRelation.HAS_CHANGED,
                ),
            ),
        ),
    )
    state.task_progress = PlanProgress(active_subgoal_id="slider-value:changed")
    state.record_planner_proposal(
        {
            "proposal_id": "previous",
            "action_kind": "activate",
            "target_affordance_id": "dom_input_3",
            "expected_effects": ["checkbox-3 checked"],
        }
    )
    from affordance_runtime.verification import VerificationReport, VerificationStatus

    state.latest_verification = VerificationReport(VerificationStatus.PASSED)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Select 7 with the slider, click the 3rd checkbox, then hit Submit.",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("slider_value_7", "checkbox_3_state", "submit_button_state"),
        success_criteria=("slider_value_7_selected", "checkbox_3_checked", "submit_button_clicked"),
        source_request_ref="request-1",
    )

    decision = asyncio.run(
        GeneralistLMPlanner(EmptyClarificationModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    _assert_strict_semantic_resolver_retired(decision)


def test_strict_planner_no_longer_guesses_page_text_when_no_actionchoice_exists() -> None:
    model = _authored_dom_adapter().transduce(
        '<div>LO4e</div><input id="tt" type="text"><button>Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
        metadata={"visible_text": "LO4e\n Submit"},
    )
    snapshot = BrowserSnapshot(observation, model)
    objective = "Type the text below into the text field and press Submit."
    state = StateKernel("task-1", objective)
    state.remember_observation(observation)
    state.task_plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=1,
        plan_version=1,
        based_on_state_version=state.version,
        generated_by=TaskPlanSource.RULE,
        subgoals=(
            SubgoalSpec(
                subgoal_id="text-field:changed",
                objective="text_field has changed",
                interaction=make_interaction('text_field'),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.TYPE_TEXT,
                outcome=SubgoalOutcome(
                    subject="text_field",
                    relation=SubgoalOutcomeRelation.HAS_CHANGED,
                ),
            ),
        ),
    )
    state.task_progress = PlanProgress(active_subgoal_id="text-field:changed")
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective=objective,
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("text_field",),
        success_criteria=("text_field has changed",),
        source_request_ref="request-1",
    )

    @dataclass
    class EmptyClarificationModel:
        provider: str = "fixed"
        model: str = "empty-clarification"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            return output_schema.model_validate({"action_kind": "ask_user"})

    decision = asyncio.run(
        GeneralistLMPlanner(EmptyClarificationModel()).propose_legacy(
            RunRequest(task_spec=task_spec),
            state,
            snapshot,
        )
    )

    _assert_strict_semantic_resolver_retired(decision)


def test_strict_planner_does_not_submit_after_verified_page_text_without_actionchoice() -> None:
    model = _authored_dom_adapter().transduce(
        '<div>LO4e</div><input id="tt" type="text"><button>Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    filled_model = replace(
        model,
        affordances=[
            replace(item, state={**item.state, "control_value": "LO4e"})
            if item.id == "dom_input_1"
            else item
            for item in model.affordances
        ],
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
        metadata={"visible_text": "LO4e\n Submit"},
    )
    snapshot = BrowserSnapshot(observation, filled_model)
    objective = "Type the text below into the text field and press Submit."
    state = StateKernel("task-1", objective)
    state.remember_observation(observation)
    state.task_plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=1,
        plan_version=1,
        based_on_state_version=state.version,
        generated_by=TaskPlanSource.RULE,
        subgoals=(
            SubgoalSpec(
                subgoal_id="text-field:changed",
                objective="text_field has changed",
                interaction=make_interaction('text_field'),
                operation_class=OperationClass.REVERSIBLE_WRITE,
                action_family=TaskPlanActionFamily.TYPE_TEXT,
                outcome=SubgoalOutcome(
                    subject="text_field",
                    relation=SubgoalOutcomeRelation.HAS_CHANGED,
                ),
            ),
        ),
    )
    state.task_progress = PlanProgress(active_subgoal_id="text-field:changed")
    state.record_planner_proposal(
        {
            "proposal_id": "previous",
            "action_kind": "type_text",
            "target_affordance_id": "dom_input_1",
            "expected_effects": ["text_field has changed"],
        }
    )
    state.record_action_progress(
        '{"action_kind":"type_text","target":"dom_input_1","parameters":{"text":"LO4e"}}',
        "rev-1",
        verification_passed=True,
        post_page_revision=model.page_revision,
    )
    from affordance_runtime.verification import VerificationReport, VerificationStatus

    state.latest_verification = VerificationReport(VerificationStatus.PASSED)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective=objective,
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("text_field",),
        success_criteria=("submitted",),
        source_request_ref="request-1",
    )

    @dataclass
    class BlockingClarificationModel:
        provider: str = "fixed"
        model: str = "blocking-clarification"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            return output_schema.model_validate({"action_kind": "ask_user", "reason": "text mismatch"})

    decision = asyncio.run(
        GeneralistLMPlanner(BlockingClarificationModel()).propose_legacy(
            RunRequest(task_spec=task_spec),
            state,
            snapshot,
        )
    )

    _assert_strict_semantic_resolver_retired(decision)


def test_satisfied_prefix_control_value_leaves_submit_available() -> None:
    model = _authored_dom_adapter().transduce(
        '<input id="tags" class="ui-autocomplete-input" value="Comoros"><button>Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Enter an item starting with Com")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Enter an item starting with Com",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("item",),
        semantic_value_constraints=(
            SemanticValueConstraint(
                relation=SemanticValueRelation.PREFIX,
                value="Com",
                target="item",
                source_ref="request-1",
            ),
        ),
        success_criteria=("matching item entered",),
        source_request_ref="request-1",
    )

    @dataclass
    class SubmitModel:
        provider: str = "fixed"
        model: str = "submit-after-prefix"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            return output_schema.model_validate(
                {
                    "action_kind": "activate",
                    "target_affordance_id": "dom_button_1",
                    "parameters": {},
                }
            )

    decision = asyncio.run(
        GeneralistLMPlanner(
            SubmitModel(),
            planner_profile=GeneralistPlannerProfile.HISTORICAL_COMPATIBILITY,
            semantic_compilers=SemanticCompilerRegistry.disabled(),
        ).propose_legacy(
            RunRequest(task_spec=task_spec), state, snapshot
        )
    )

    assert decision.proposal is not None
    assert decision.proposal.action_kind == PlannerActionKind.ACTIVATE
    assert decision.proposal.target_affordance_id == "dom_button_1"


def test_strict_global_ordinal_schema_selects_the_required_page_transition() -> None:
    model = _authored_dom_adapter().transduce(
        '<div id="results"><a data-result="0">A</a><a data-result="1">B</a>'
        '<a data-result="2">C</a></div><ul id="pages" class="pagination">'
        '<li class="page-item active"><a>1</a></li>'
        '<li class="page-item"><a>2</a></li>'
        '<li class="page-item"><a>3</a></li></ul>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Click the 4th search result")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Click the 4th search result",
        operation_class=OperationClass.READ_ONLY,
        targets=("search result",),
        success_criteria=("the fourth result is activated",),
        source_request_ref="request-1",
    )

    @dataclass
    class PageTransitionModel:
        provider: str = "fixed"
        model: str = "ordinal-page-transition"
        endpoint_class: str = "test"
        last_call: ModelCallRecord | None = None

        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            with pytest.raises(ValidationError):
                output_schema.model_validate(
                    {
                        "action_kind": "activate",
                        "target_affordance_id": "dom_a_1",
                        "parameters": {},
                    }
                )
            return output_schema.model_validate(
                {
                    "action_kind": "activate",
                    "target_affordance_id": "dom_a_5",
                    "parameters": {},
                }
            )

    decision = asyncio.run(
        _compatibility_planner(PageTransitionModel()).propose_legacy(
            RunRequest(task_spec=task_spec), state, snapshot
        )
    )

    assert decision.proposal is not None
    assert decision.proposal.target_affordance_id == "dom_a_5"


def test_generalist_initial_schema_excludes_unjustified_clarification() -> None:
    schema = _initial_candidate_schema(["activate"])

    assert schema.model_validate({"action_kind": "activate"}).action_kind == PlannerActionKind.ACTIVATE
    with pytest.raises(ValidationError):
        schema.model_validate({"action_kind": "ask_user"})


def test_generalist_repair_excludes_siblings_after_one_ordinal_control_is_satisfied() -> None:
    model = _authored_dom_adapter().transduce(
        '<input type="checkbox"><input type="checkbox"><input type="checkbox"><button>Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Click the 3rd checkbox, then Submit")
    state.remember_observation(observation)
    state.latest_progress_guard = {
        "reason": "effect_already_satisfied",
        "signature": '{"action_kind":"activate","parameters":{},"target":"dom_input_3"}',
        "environment_revision": "rev-1",
    }
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Click the 3rd checkbox, then Submit",
        operation_class=OperationClass.READ_ONLY,
        targets=("3rd checkbox",),
        success_criteria=("submitted",),
        source_request_ref="request-1",
    )
    context = GeneralistLMPlanner(ProposalModel()).build_context(RunRequest(task_spec=task_spec), state, snapshot)
    candidate = PlannerProposalCandidate(
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id="dom_input_3",
    )

    permitted, targets = _repair_constraints(
        context,
        candidate,
        "proposal_repeats_blocked_progress",
    )

    assert permitted == ["activate"]
    assert targets["activate"] == ["dom_button_1"]


def test_generalist_target_scope_keeps_only_named_checkbox_labels_and_submit() -> None:
    model = _authored_dom_adapter().transduce(
        '<label><input type="checkbox">Jc</label>'
        '<label><input type="checkbox">skip</label>'
        '<label><input type="checkbox">XMHY</label>'
        "<button>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Select Jc, XMHY and click Submit")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Select Jc, XMHY and click Submit",
        operation_class=OperationClass.READ_ONLY,
        targets=("Jc", "XMHY"),
        success_criteria=("submitted",),
        source_request_ref="request-1",
    )
    context = GeneralistLMPlanner(ProposalModel()).build_context(RunRequest(task_spec=task_spec), state, snapshot)

    targets = _restrict_targets_to_objective(
        context,
        {"activate": [item.id for item in context.affordances]},
    )

    assert targets["activate"] == ["dom_input_1", "dom_input_3", "dom_button_1"]


def test_generalist_selection_only_goal_excludes_incidental_text_inputs() -> None:
    model = _authored_dom_adapter().transduce(
        "<select><option>Earth</option><option>Mars</option></select><input><button>No</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", 'Choose Mars from the dropdown, then click the button labeled "No"')
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective='Choose Mars from the dropdown, then click the button labeled "No"',
        operation_class=OperationClass.READ_ONLY,
        targets=("Mars", "No"),
        success_criteria=("submitted",),
        source_request_ref="request-1",
    )
    context = GeneralistLMPlanner(ProposalModel()).build_context(RunRequest(task_spec=task_spec), state, snapshot)

    assert _hierarchical_target_operation(context) is None

    permitted, targets = _restrict_action_kinds_to_objective(
        context,
        ["activate", "select_option", "type_text"],
        {
            "activate": ["dom_button_1"],
            "select_option": [],
            "type_text": ["dom_input_1"],
        },
    )

    assert permitted == ["activate", "select_option"]
    assert targets == {
        "activate": ["dom_button_1"],
        "select_option": [],
    }


def test_generalist_excludes_autocomplete_refill_after_current_value_matches() -> None:
    model = _authored_dom_adapter().transduce(
        '<input id="tags" class="ui-autocomplete-input" value="Comoros"><button>Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", 'Enter an item that starts with "Com"')
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective='Enter an item that starts with "Com"',
        operation_class=OperationClass.READ_ONLY,
        targets=("item",),
        success_criteria=("matching item entered",),
        source_request_ref="request-1",
    )
    context = GeneralistLMPlanner(ProposalModel()).build_context(RunRequest(task_spec=task_spec), state, snapshot)

    permitted, targets = _restrict_action_kinds_to_objective(
        context,
        ["activate", "type_text"],
        {"activate": ["dom_button_1"], "type_text": ["dom_input_1"]},
    )

    assert permitted == ["activate"]
    assert targets == {"activate": ["dom_button_1"]}


def test_generalist_compiles_unique_terminal_after_requested_text_is_present() -> None:
    model = _authored_dom_adapter().transduce(
        '<textarea id="reply-text">Ornare commodo.</textarea><button>Send reply</button><button>Cancel</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    model = replace(
        model,
        affordances=[
            replace(item, state={**item.state, "control_value": "Ornare commodo."})
            if item.id == "dom_textarea_1"
            else item
            for item in model.affordances
        ],
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", 'Reply with the text "Ornare commodo.".')
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective='Reply with the text "Ornare commodo.".',
        operation_class=OperationClass.READ_ONLY,
        targets=("email",),
        success_criteria=("reply sent",),
        source_request_ref="request-1",
    )
    planner_model = ProposalModel()

    decision = asyncio.run(
        _compatibility_planner(planner_model).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert decision.proposal.action_kind == PlannerActionKind.ACTIVATE
    assert decision.proposal.target_affordance_id == "dom_button_1"
    assert planner_model.context is None


def test_generalist_opens_unique_search_when_named_source_is_not_visible() -> None:
    model = _authored_dom_adapter().transduce(
        '<span id="open-search" data-runtime-handle="open" data-runtime-interactive="1"></span>'
        '<span id="search-cancel" data-runtime-handle="cancel" data-runtime-interactive="1"></span>'
        '<div data-runtime-handle="other" tabindex="0">Other</div>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", 'Find the email by Ryann and reply with the text "Hello".')
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective='Find the email by Ryann and reply with the text "Hello".',
        operation_class=OperationClass.READ_ONLY,
        targets=("email",),
        success_criteria=("reply sent",),
        source_request_ref="request-1",
    )
    planner_model = ProposalModel()

    decision = asyncio.run(
        _compatibility_planner(planner_model).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert decision.proposal.action_kind == PlannerActionKind.ACTIVATE
    assert decision.proposal.target_affordance_id == "dom_span_1"
    assert planner_model.context is None


def test_generalist_enters_absent_source_into_unique_search_and_forward_recipient_into_unique_input() -> None:
    model = _authored_dom_adapter().transduce(
        '<input id="search-input" placeholder="Search">',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    source_context = GeneralistLMPlanner(ProposalModel()).build_context(
        RunRequest(
            task_spec=TaskSpec(
                task_id="task-1",
                revision=1,
                objective='Find the email by Ryann and reply with the text "Hello".',
                operation_class=OperationClass.READ_ONLY,
                targets=("email",),
                success_criteria=("reply sent",),
                source_request_ref="request-1",
            )
        ),
        StateKernel("task-1", "find email"),
        BrowserSnapshot(observation, model),
    )
    permitted, targets, value = _target_discovery_constraints(
        source_context, ["activate", "type_text"], {"type_text": ["dom_input_1"]}
    )
    assert (permitted, targets, value) == (["type_text"], {"type_text": ["dom_input_1"]}, "Ryann")

    forward_model = _authored_dom_adapter().transduce(
        '<input id="forward-sender"><textarea id="forward-text">Message body</textarea>'
        '<span id="send-forward" data-runtime-handle="send" data-runtime-interactive="1"></span>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    forward_observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=forward_model.page_revision)
    forward_context = GeneralistLMPlanner(ProposalModel()).build_context(
        RunRequest(
            task_spec=TaskSpec(
                task_id="task-2",
                revision=1,
                objective="Find the email by Ryann and forward that email to Marlo.",
                operation_class=OperationClass.READ_ONLY,
                targets=("email",),
                success_criteria=("forward sent",),
                source_request_ref="request-1",
            )
        ),
        StateKernel("task-2", "forward email"),
        BrowserSnapshot(forward_observation, forward_model),
    )
    permitted, targets, value = _forward_recipient_constraints(
        forward_context, ["activate", "type_text"], {"type_text": ["dom_input_1"]}
    )
    assert (permitted, targets, value) == (["type_text"], {"type_text": ["dom_input_1"]}, "Marlo")


def test_generalist_prefers_terminal_control_after_requested_text_is_present() -> None:
    model = _authored_dom_adapter().transduce(
        '<textarea id="reply-text">Ornare commodo.</textarea><button>Send reply</button><button>Cancel</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    model = replace(
        model,
        affordances=[
            replace(item, state={**item.state, "control_value": "Ornare commodo."})
            if item.id == "dom_textarea_1"
            else item
            for item in model.affordances
        ],
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", 'Reply with the text "Ornare commodo.".')
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective='Reply with the text "Ornare commodo.".',
        operation_class=OperationClass.READ_ONLY,
        targets=("email",),
        success_criteria=("reply sent",),
        source_request_ref="request-1",
    )
    context = GeneralistLMPlanner(ProposalModel()).build_context(RunRequest(task_spec=task_spec), state, snapshot)

    permitted, targets = _restrict_action_kinds_to_objective(
        context,
        ["activate", "type_text"],
        {
            "activate": ["dom_button_1", "dom_button_2"],
            "type_text": ["dom_textarea_1"],
        },
    )

    assert permitted == ["activate"]
    assert targets == {"activate": ["dom_button_1"]}


def test_generalist_recognizes_hyphenated_terminal_control_after_text_is_present() -> None:
    model = _authored_dom_adapter().transduce(
        '<textarea id="reply-text">Ornare commodo.</textarea>'
        '<span data-runtime-handle="send" data-runtime-interactive="1">send-reply</span>'
        "<label>to:</label>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    model = replace(
        model,
        affordances=[
            replace(item, state={**item.state, "control_value": "Ornare commodo."})
            if item.id == "dom_textarea_1"
            else item
            for item in model.affordances
        ],
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", 'Reply with the text "Ornare commodo.".')
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective='Reply with the text "Ornare commodo.".',
        operation_class=OperationClass.READ_ONLY,
        targets=("email",),
        success_criteria=("reply sent",),
        source_request_ref="request-1",
    )
    context = GeneralistLMPlanner(ProposalModel()).build_context(RunRequest(task_spec=task_spec), state, snapshot)

    permitted, targets = _restrict_action_kinds_to_objective(
        context,
        ["activate", "type_text"],
        {
            "activate": ["dom_span_1", "dom_label_1"],
            "type_text": ["dom_textarea_1"],
        },
    )

    assert permitted == ["activate"]
    assert targets == {"activate": ["dom_span_1"]}


def test_generalist_resolves_ordinal_collection_across_pagination() -> None:
    model = _authored_dom_adapter().transduce(
        '<div><a data-result="0">one</a></div>'
        '<div><a data-result="1">two</a></div>'
        '<div><a data-result="2">three</a></div>'
        "<ul><li><a>2</a></li></ul>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    state = StateKernel("task-1", "Click the 4th search result")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Click the 4th search result",
        operation_class=OperationClass.READ_ONLY,
        targets=("result",),
        success_criteria=("opened",),
        source_request_ref="request-1",
    )
    context = GeneralistLMPlanner(ProposalModel()).build_context(
        RunRequest(task_spec=task_spec),
        state,
        BrowserSnapshot(observation, model),
    )

    assert _ordinal_collection_operation(context) == "dom_a_4"

    page_two = _authored_dom_adapter().transduce(
        '<div><a data-result="3">four</a></div><div><a data-result="4">five</a></div>',
        environment_revision="rev-2",
        snapshot_id="snapshot-2",
    )
    page_two_observation = Observation(
        "rev-2",
        snapshot_id="snapshot-2",
        page_revision=page_two.page_revision,
    )
    page_two_state = StateKernel("task-1", "Click the 4th search result")
    page_two_state.remember_observation(page_two_observation)
    page_two_context = GeneralistLMPlanner(ProposalModel()).build_context(
        RunRequest(task_spec=task_spec),
        page_two_state,
        BrowserSnapshot(page_two_observation, page_two),
    )

    assert _ordinal_collection_operation(page_two_context) == "dom_a_1"


def test_generalist_binds_only_remaining_requested_multi_select_value() -> None:
    model = _authored_dom_adapter().transduce(
        '<select data-runtime-handle="items" multiple><option>Ertha</option><option>Aurel</option></select>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    model = replace(
        model,
        affordances=[
            replace(item, state={**item.state, "selected_options": ["Ertha"]}) if item.id == "dom_select_1" else item
            for item in model.affordances
        ],
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    state = StateKernel("task-1", "Select Ertha, Aurel from the scroll list and click Submit")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Select Ertha, Aurel from the scroll list and click Submit",
        operation_class=OperationClass.READ_ONLY,
        targets=("items",),
        success_criteria=("submitted",),
        source_request_ref="request-1",
    )
    context = GeneralistLMPlanner(ProposalModel()).build_context(
        RunRequest(task_spec=task_spec),
        state,
        BrowserSnapshot(observation, model),
    )

    assert _remaining_requested_selection_values(context) == ("Aurel",)
    candidate = PlannerProposalCandidate(
        action_kind=PlannerActionKind.SELECT_OPTION,
        target_affordance_id="dom_select_1",
        parameters={"option": "Brittne"},
    )
    assert candidate.bind(context).parameters == {"option": "Brittne"}
    assert candidate.bind(context, compatibility_rewrites=True).parameters == {"option": ["Ertha", "Aurel"]}


def test_generalist_keeps_only_autocomplete_option_matching_prefix_and_suffix() -> None:
    model = _authored_dom_adapter().transduce(
        '<input id="tags" class="ui-autocomplete-input" value="Mo"><button>Submit</button>'
        '<ul data-runtime-handle="menu" tabindex="0">'
        '<li><div data-runtime-handle="moldova" tabindex="-1">Moldova</div></li>'
        '<li><div data-runtime-handle="morocco" tabindex="-1">Morocco</div></li>'
        "</ul>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", 'Enter an item that starts with "Mo" and ends with "va"')
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective='Enter an item that starts with "Mo" and ends with "va"',
        operation_class=OperationClass.READ_ONLY,
        targets=("item",),
        success_criteria=("matching item entered",),
        source_request_ref="request-1",
    )
    context = GeneralistLMPlanner(ProposalModel()).build_context(RunRequest(task_spec=task_spec), state, snapshot)

    targets = _restrict_targets_to_objective(
        context,
        {"activate": ["dom_button_1", "dom_div_1", "dom_div_2"]},
    )

    assert targets == {"activate": ["dom_button_1", "dom_div_1"]}


def test_generalist_target_scope_binds_each_ordinal_to_its_control_role() -> None:
    model = _authored_dom_adapter().transduce(
        '<input type="radio" value="1"><input type="radio" value="2"><input type="radio" value="3">'
        '<input type="text"><input type="text"><input type="text"><button>Submit</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Check 1st radio and enter 27 in 2nd textbox")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Check the 1st radio button and enter 27 in the 2nd textbox.",
        operation_class=OperationClass.READ_ONLY,
        targets=("1st radio", "2nd textbox"),
        success_criteria=("submitted",),
        source_request_ref="request-1",
    )
    context = GeneralistLMPlanner(ProposalModel()).build_context(RunRequest(task_spec=task_spec), state, snapshot)

    targets = _restrict_targets_to_objective(
        context,
        {
            "activate": ["dom_input_1", "dom_input_2", "dom_input_3", "dom_button_1"],
            "type_text": ["dom_input_4", "dom_input_5", "dom_input_6"],
        },
    )

    assert targets == {
        "activate": ["dom_input_1", "dom_button_1"],
        "type_text": ["dom_input_5"],
    }


def test_generalist_rejects_an_action_target_mismatch_before_binding() -> None:
    model = _authored_dom_adapter().transduce(
        "<select><option>Earth</option></select><button>Submit</button>",
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Choose Earth and click Submit")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Choose Earth and click Submit",
        operation_class=OperationClass.READ_ONLY,
        targets=("Earth",),
        success_criteria=("submitted",),
        source_request_ref="request-1",
    )
    context = GeneralistLMPlanner(ProposalModel()).build_context(RunRequest(task_spec=task_spec), state, snapshot)
    candidate = PlannerProposalCandidate(
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id="dom_select_1",
    )

    assert _candidate_prebind_issue(candidate, context) == "proposal_target_action_mismatch"


def test_generalist_rebinds_select_option_from_option_affordance_to_unique_select_owner() -> None:
    model = _authored_dom_adapter().transduce(
        '<select><option value="earth">Earth</option></select>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Choose Earth")
    state.remember_observation(observation)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Choose Earth",
        operation_class=OperationClass.READ_ONLY,
        targets=("Earth",),
        success_criteria=("Earth selected",),
        source_request_ref="request-1",
    )

    class OptionTargetModel(ProposalModel):
        async def generate_structured(
            self, messages: Sequence[ModelMessage], output_schema: type[T], config: ModelConfig
        ) -> T:
            del messages, config
            return output_schema.model_validate(
                {
                    "action_kind": "select_option",
                    "target_affordance_id": "dom_option_1",
                    "parameters": {"option": "earth"},
                }
            )

    decision = asyncio.run(
        _compatibility_planner(OptionTargetModel()).propose_legacy(RunRequest(task_spec=task_spec), state, snapshot)
    )

    assert decision.proposal is not None
    assert decision.proposal.target_affordance_id == "dom_select_1"


def test_generalist_context_exposes_passed_effect_without_surface_payload() -> None:
    model = _authored_dom_adapter().transduce(
        '<button id="save">Save</button>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Save theme")
    state.transition("observing")
    state.remember_observation(observation)
    state.transition("planning")
    state.record_planner_proposal(
        {
            "proposal_id": "previous",
            "action_kind": "activate",
            "target_affordance_id": "dom_button_1",
            "expected_effects": ["theme saved"],
        }
    )
    from affordance_runtime.verification import VerificationReport, VerificationStatus

    state.latest_verification = VerificationReport(VerificationStatus.PASSED)
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Save theme",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("theme",),
        success_criteria=("theme saved",),
        source_request_ref="request-1",
    )

    context = GeneralistLMPlanner(ProposalModel()).build_context(
        RunRequest(task_spec=task_spec),
        state,
        snapshot,
    )

    assert context.verified_effects == ("theme saved",)
    assert context.recent_proposals[-1]["target_affordance_id"] == "dom_button_1"


def test_generalist_context_bounds_inventory_history_and_failure_detail() -> None:
    html = "".join(f'<button id="button-{index}">Button {index}</button>' for index in range(90))
    model = _authored_dom_adapter().transduce(html, environment_revision="rev-1", snapshot_id="snapshot-1")
    observation = Observation("rev-1", snapshot_id="snapshot-1", page_revision=model.page_revision)
    snapshot = BrowserSnapshot(observation, model)
    state = StateKernel("task-1", "Click a button")
    state.transition("observing")
    state.remember_observation(observation)
    state.transition("planning")
    for index in range(6):
        state.record_planner_proposal(
            {
                "proposal_id": f"previous-{index}",
                "action_kind": "activate",
                "target_affordance_id": f"dom_button_{index + 1}",
                "expected_effects": ["button clicked"],
            }
        )
    from affordance_runtime.verification import (
        VerificationEvidence,
        VerificationReport,
        VerificationStatus,
    )

    state.latest_verification = VerificationReport(
        VerificationStatus.FAILED,
        evidence=[
            VerificationEvidence("evidence", "transport", True, "receipt", True, True),
            VerificationEvidence("state_delta", "button", False, "post_action_observation", "rev-1", "changed"),
        ],
        reason="semantic state did not change",
    )
    state.latest_progress_guard = {
        "reason": "no_progress_repeat",
        "signature": "activate:button",
        "environment_revision": "rev-1",
    }
    task_spec = TaskSpec(
        task_id="task-1",
        revision=1,
        objective="Click a button",
        operation_class=OperationClass.READ_ONLY,
        targets=("button",),
        success_criteria=("button clicked",),
        source_request_ref="request-1",
    )

    context = GeneralistLMPlanner(ProposalModel()).build_context(RunRequest(task_spec=task_spec), state, snapshot)

    assert len(context.affordances) == 80
    assert len(context.recent_proposals) == 1
    assert context.recent_proposals[0]["proposal_id"] == "previous-5"
    assert context.latest_outcome["verified_state_delta"] == [
        {
            "verifier_kind": "state_delta",
            "target": "button",
            "passed": False,
            "observed": "rev-1",
            "expected": "changed",
        }
    ]
    assert context.recovery_summary["reason"] == "no_progress_repeat"
    assert "source_request_ref" not in context.task_spec

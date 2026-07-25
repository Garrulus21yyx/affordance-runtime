import pytest

from affordance_runtime.contracts import Observation
from affordance_runtime.criteria import criterion_id, evidence_requirement_id
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec, TaskStructure
from affordance_runtime.task_planning import (
    TASK_PLAN_CARDINALITY_POLICY_VERSION,
    TASK_PLAN_CONTEXT_POLICY_VERSION,
    TASK_PLAN_ENTRY_SCHEMA_POLICY_VERSION,
    LLMTaskPlanner,
    PlanningAffordanceState,
    PlanningAffordanceSummary,
    PlanningEnvironmentSummary,
    PlanningRouter,
    PlanProgress,
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanCandidate,
    TaskPlanningBudgetSummary,
    TaskPlanningContext,
    TaskPlanProviderEnvelope,
    TaskPlanSource,
    TaskPlanValidationStatus,
    TaskPlanValidator,
    synthetic_task_plan,
    task_plan_allowed_outcome_relations,
    task_plan_provider_model_for_context,
    task_plan_repair_directives,
    task_planner_model_config,
)
from affordance_runtime.verification import VerificationEvidence, VerificationReport, VerificationStatus


def _task() -> TaskSpec:
    return TaskSpec(
        task_id="task-1",
        revision=2,
        objective="Update the theme and confirm it",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("theme",),
        success_criteria=("theme is dark",),
        evidence_requirements=("settings API confirms dark",),
        requested_capabilities=("settings.write",),
        source_request_ref="request-1",
    )


def _context(*, state_version: int = 4) -> TaskPlanningContext:
    return TaskPlanningContext(
        task_spec=_task(),
        state_version=state_version,
        remaining_budget=TaskPlanningBudgetSummary(
            steps_remaining=10,
            observations_remaining=10,
            replans_remaining=2,
            recoveries_remaining=2,
            effectful_actions_remaining=2,
        ),
    )


def test_simple_router_preserves_flat_path_as_one_verifier_backed_subgoal() -> None:
    plan = PlanningRouter().plan(_context())

    assert plan.generated_by == TaskPlanSource.RULE
    assert len(plan.subgoals) == 1
    assert plan.subgoals[0].objective == _task().objective
    assert TaskPlanValidator().validate(plan, _task(), state_version=4).status == TaskPlanValidationStatus.ACCEPT


def test_task_planning_context_versions_bounded_current_state_policy() -> None:
    context = _context()

    assert context.schema_version == "1.1"
    assert TASK_PLAN_CONTEXT_POLICY_VERSION == "bounded-current-state-v1"


def test_llm_facing_subgoal_schema_requires_typed_outcome_and_evidence() -> None:
    schema = TaskPlanCandidate.model_json_schema()
    items_schema = schema["properties"]["subgoals"]["items"]
    mapping = items_schema["discriminator"]["mapping"]

    assert items_schema["discriminator"]["propertyName"] == "action_family"
    assert set(mapping) == {item.value for item in TaskPlanActionFamily}
    for family_value, candidate_ref in mapping.items():
        candidate_schema = schema["$defs"][candidate_ref.rsplit("/", 1)[-1]]
        outcome_ref = candidate_schema["properties"]["outcome"]["$ref"]
        outcome_schema = schema["$defs"][outcome_ref.rsplit("/", 1)[-1]]
        relation_schema = outcome_schema["properties"]["relation"]
        if "$ref" in relation_schema:
            relation_schema = schema["$defs"][relation_schema["$ref"].rsplit("/", 1)[-1]]
        schema_relations = set(
            relation_schema.get("enum", [relation_schema.get("const")])
        )
        family = TaskPlanActionFamily(family_value)

        assert schema_relations == {
            item.value for item in task_plan_allowed_outcome_relations(family)
        }
        assert set(candidate_schema["required"]) >= {
            "subgoal_id",
            "outcome",
            "evidence_requirements",
            "operation_class",
            "action_family",
        }
        assert candidate_schema["properties"]["evidence_requirements"]["minItems"] == 1
        assert "success_criteria" not in candidate_schema["properties"]
    assert set(SubgoalSpec.model_json_schema()["required"]) == {
        "subgoal_id",
        "objective",
        "operation_class",
    }
    assert task_planner_model_config().prompt_version == "task-planner-v11"


def test_llm_facing_schema_rejects_invalid_action_outcome_pair_before_binding() -> None:
    with pytest.raises(ValueError, match="is_available"):
        TaskPlanCandidate.model_validate(
            {
                "subgoals": [
                    {
                        "subgoal_id": "activate-search",
                        "outcome": {
                            "subject": "search button",
                            "relation": "is_available",
                        },
                        "evidence_requirements": ["current search state"],
                        "operation_class": "reversible_write",
                        "action_family": "activate",
                    }
                ]
            }
        )


def test_llm_facing_schema_accepts_same_relation_for_compatible_navigation() -> None:
    candidate = TaskPlanCandidate.model_validate(
        {
            "subgoals": [
                {
                    "subgoal_id": "open-search",
                    "outcome": {
                        "subject": "search page",
                        "relation": "is_available",
                    },
                    "evidence_requirements": ["current page observation"],
                    "operation_class": "read_only",
                    "action_family": "navigate",
                }
            ]
        }
    )

    assert candidate.subgoals[0].action_family == TaskPlanActionFamily.NAVIGATE


def test_context_schema_constrains_only_first_subgoal_to_current_actions() -> None:
    context = _context().model_copy(
        update={
            "environment": PlanningEnvironmentSummary(
                affordances=(
                    PlanningAffordanceSummary(
                        semantic_target_id="search-text",
                        supported_actions=("type_text", "activate"),
                    ),
                )
            )
        }
    )
    provider_model = task_plan_provider_model_for_context(context)
    schema = provider_model.model_json_schema()
    entry_schema = schema["properties"]["entry_subgoal"]
    remaining_items = schema["properties"]["remaining_subgoals"]["items"]

    assert TASK_PLAN_ENTRY_SCHEMA_POLICY_VERSION == "explicit-entry-envelope-v1"
    assert set(schema["required"]) == {"entry_subgoal"}
    assert "subgoals" not in schema["properties"]
    assert set(entry_schema["discriminator"]["mapping"]) == {
        "activate",
        "type_text",
    }
    assert set(remaining_items["discriminator"]["mapping"]) == {
        item.value for item in TaskPlanActionFamily
    }
    assert schema["properties"]["remaining_subgoals"]["minItems"] == 1
    assert schema["properties"]["remaining_subgoals"]["maxItems"] == 7
    assert (
        TASK_PLAN_CARDINALITY_POLICY_VERSION
        == "flat-1-multistage-initial-2-replacement-1-to-8-v2"
    )


def test_context_schema_parser_preserves_future_family_and_public_shape() -> None:
    context = _context().model_copy(
        update={
            "environment": PlanningEnvironmentSummary(
                affordances=(
                    PlanningAffordanceSummary(
                        semantic_target_id="search-text",
                        supported_actions=("type_text",),
                    ),
                )
            )
        }
    )
    provider_model = task_plan_provider_model_for_context(context)

    envelope = provider_model.model_validate(
        {
            "entry_subgoal": {
                "subgoal_id": "enter",
                "outcome": {
                    "subject": "search text",
                    "relation": "equals",
                    "value": "Myron",
                },
                "evidence_requirements": ["current input value"],
                "operation_class": "reversible_write",
                "action_family": "type_text",
            },
            "remaining_subgoals": [
                {
                    "subgoal_id": "open",
                    "outcome": {
                        "subject": "results page",
                        "relation": "is_available",
                    },
                    "depends_on": ["enter"],
                    "evidence_requirements": ["current page observation"],
                    "operation_class": "reversible_write",
                    "action_family": "navigate",
                },
            ]
        }
    )
    candidate = envelope.to_candidate()

    assert isinstance(envelope, TaskPlanProviderEnvelope)
    assert isinstance(candidate, TaskPlanCandidate)
    assert [item.action_family for item in candidate.subgoals] == [
        TaskPlanActionFamily.TYPE_TEXT,
        TaskPlanActionFamily.NAVIGATE,
    ]


def test_context_schema_stays_generic_when_environment_is_unknown() -> None:
    assert task_plan_provider_model_for_context(_context()) is TaskPlanProviderEnvelope


def test_replacement_schema_allows_one_unfinished_entry_after_verified_progress() -> None:
    context = _context().model_copy(update={"completed_subgoal_ids": ("done",)})

    schema = task_plan_provider_model_for_context(context).model_json_schema()

    assert schema["properties"]["remaining_subgoals"]["minItems"] == 0


def test_provider_envelope_rejects_legacy_positional_candidate_shape() -> None:
    with pytest.raises(ValueError, match="entry_subgoal"):
        TaskPlanProviderEnvelope.model_validate({"subgoals": []})


class RecordingComplexPlanner:
    def __init__(self) -> None:
        self.calls = 0

    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        self.calls += 1
        return synthetic_task_plan(context, generated_by=TaskPlanSource.PARENT)


def test_multi_stage_router_uses_only_the_declared_complex_planner() -> None:
    complex_planner = RecordingComplexPlanner()
    context = _context().model_copy(
        update={
            "task_spec": _task().model_copy(
                update={"task_structure": TaskStructure.MULTI_STAGE}
            )
        }
    )

    plan = PlanningRouter(complex_planner=complex_planner).plan(context)

    assert complex_planner.calls == 1
    assert plan.generated_by == TaskPlanSource.PARENT


def test_multi_stage_router_fails_closed_without_a_declared_complex_planner() -> None:
    context = _context().model_copy(
        update={
            "task_spec": _task().model_copy(
                update={"task_structure": TaskStructure.MULTI_STAGE}
            )
        }
    )

    with pytest.raises(ValueError, match="complex task requires"):
        PlanningRouter().plan(context)


def test_validator_rejects_stale_escalating_and_cyclic_plans() -> None:
    plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=1,
        plan_version=1,
        based_on_state_version=3,
        generated_by=TaskPlanSource.LLM,
        subgoals=(
            SubgoalSpec(
                subgoal_id="a",
                objective="Write theme",
                depends_on=("b",),
                success_criteria=("theme is dark",),
                evidence_requirements=("API confirms",),
                operation_class=OperationClass.IRREVERSIBLE,
            ),
            SubgoalSpec(
                subgoal_id="b",
                objective="Confirm theme",
                depends_on=("a",),
                success_criteria=("theme is dark",),
                evidence_requirements=("API confirms",),
                operation_class=OperationClass.REVERSIBLE_WRITE,
            ),
        ),
    )

    report = TaskPlanValidator().validate(plan, _task(), state_version=4)

    assert report.status == TaskPlanValidationStatus.REJECT
    assert {item.code for item in report.issues} >= {
        "task_revision_mismatch",
        "state_version_mismatch",
        "operation_class_escalation",
        "dependency_cycle",
    }


def test_validator_marks_missing_verification_requirements_repairable() -> None:
    plan = TaskPlan(
        plan_id="plan-1",
        task_id="task-1",
        task_revision=2,
        plan_version=1,
        based_on_state_version=4,
        generated_by=TaskPlanSource.LLM,
        subgoals=(
            SubgoalSpec(
                subgoal_id="a",
                objective="Update theme",
                operation_class=OperationClass.REVERSIBLE_WRITE,
            ),
        ),
    )

    report = TaskPlanValidator().validate(plan, _task(), state_version=4)

    assert report.status == TaskPlanValidationStatus.REPAIRABLE
    assert {item.code for item in report.issues} == {"missing_success_criteria", "missing_evidence_requirements"}


@pytest.mark.parametrize("source", (TaskPlanSource.LLM, TaskPlanSource.PARENT))
def test_validator_requires_complex_multistage_plan_to_be_decomposed(
    source: TaskPlanSource,
) -> None:
    task = _task().model_copy(update={"task_structure": TaskStructure.MULTI_STAGE})
    plan = synthetic_task_plan(
        _context().model_copy(update={"task_spec": task}),
        generated_by=source,
    )

    report = TaskPlanValidator().validate(plan, task, state_version=4)

    assert report.status == TaskPlanValidationStatus.REPAIRABLE
    issue = next(item for item in report.issues if item.code == "multi_stage_plan_not_decomposed")
    assert issue.field == "subgoals"
    assert issue.disallowed_values == ("1",)
    assert issue.required_semantics == "at_least_two_outcome_subgoals"


def test_validator_preserves_flat_single_and_accepts_two_stage_llm_plan() -> None:
    flat = synthetic_task_plan(_context(), generated_by=TaskPlanSource.LLM)
    task = _task().model_copy(update={"task_structure": TaskStructure.MULTI_STAGE})
    first = flat.subgoals[0].model_copy(update={"subgoal_id": "first"})
    second = flat.subgoals[0].model_copy(
        update={"subgoal_id": "second", "depends_on": ("first",)}
    )
    decomposed = flat.model_copy(
        update={
            "task_id": task.task_id,
            "task_revision": task.revision,
            "subgoals": (first, second),
        }
    )

    assert (
        TaskPlanValidator().validate(flat, _task(), state_version=4).status
        == TaskPlanValidationStatus.ACCEPT
    )
    assert (
        TaskPlanValidator().validate(decomposed, task, state_version=4).status
        == TaskPlanValidationStatus.ACCEPT
    )


@pytest.mark.parametrize(
    "instruction",
    (
        "Press the Search button",
        "Click the third result",
        "Enter Myron into the search textbox",
        "Select the requested option",
    ),
)
def test_validator_requires_outcomes_instead_of_multistage_action_instructions(
    instruction: str,
) -> None:
    task = _task().model_copy(update={"task_structure": TaskStructure.MULTI_STAGE})
    plan = synthetic_task_plan(
        _context().model_copy(update={"task_spec": task})
    )
    instructed = plan.model_copy(
        update={
            "subgoals": (
                plan.subgoals[0].model_copy(update={"objective": instruction}),
            )
        }
    )

    report = TaskPlanValidator().validate(instructed, task, state_version=4)

    assert report.status == TaskPlanValidationStatus.REPAIRABLE
    assert {item.code for item in report.issues} == {"action_instruction_subgoal"}


def test_validator_accepts_observable_multistage_outcome() -> None:
    task = _task().model_copy(update={"task_structure": TaskStructure.MULTI_STAGE})
    plan = synthetic_task_plan(
        _context().model_copy(update={"task_spec": task})
    )
    outcome = plan.model_copy(
        update={
            "subgoals": (
                plan.subgoals[0].model_copy(
                    update={"objective": "Search results for Myron are visible"}
                ),
            )
        }
    )

    report = TaskPlanValidator().validate(outcome, task, state_version=4)

    assert report.status == TaskPlanValidationStatus.ACCEPT


@pytest.mark.parametrize(
    "action_family",
    (
        TaskPlanActionFamily.ACTIVATE,
        TaskPlanActionFamily.POINT_ACTIVATE,
        TaskPlanActionFamily.TYPE_TEXT,
        TaskPlanActionFamily.SELECT_OPTION,
        TaskPlanActionFamily.PRESS_KEY,
        TaskPlanActionFamily.DRAG,
        TaskPlanActionFamily.SCROLL,
    ),
)
def test_validator_marks_current_target_availability_as_precondition_only(
    action_family: TaskPlanActionFamily,
) -> None:
    task = _task().model_copy(update={"task_structure": TaskStructure.MULTI_STAGE})
    plan = synthetic_task_plan(_context().model_copy(update={"task_spec": task}))
    incompatible = plan.model_copy(
        update={
            "subgoals": (
                plan.subgoals[0].model_copy(
                    update={
                        "objective": "setting control is available",
                        "success_criteria": ("setting control is available",),
                        "action_family": action_family,
                        "outcome": SubgoalOutcome(
                            subject="setting control",
                            relation=SubgoalOutcomeRelation.IS_AVAILABLE,
                        ),
                    }
                ),
            )
        }
    )

    report = TaskPlanValidator().validate(incompatible, task, state_version=4)

    assert report.status == TaskPlanValidationStatus.REPAIRABLE
    assert "precondition_only_outcome" in {item.code for item in report.issues}


def test_validator_allows_availability_as_navigation_outcome() -> None:
    task = _task().model_copy(update={"task_structure": TaskStructure.MULTI_STAGE})
    plan = synthetic_task_plan(_context().model_copy(update={"task_spec": task}))
    navigated = plan.model_copy(
        update={
            "subgoals": (
                plan.subgoals[0].model_copy(
                    update={
                        "objective": "settings page is available",
                        "success_criteria": ("settings page is available",),
                        "action_family": TaskPlanActionFamily.NAVIGATE,
                        "outcome": SubgoalOutcome(
                            subject="settings page",
                            relation=SubgoalOutcomeRelation.IS_AVAILABLE,
                        ),
                    }
                ),
            )
        }
    )

    report = TaskPlanValidator().validate(navigated, task, state_version=4)

    assert report.status == TaskPlanValidationStatus.ACCEPT


def test_validator_marks_current_entry_action_family_unavailable() -> None:
    task = _task().model_copy(update={"task_structure": TaskStructure.MULTI_STAGE})
    plan = synthetic_task_plan(_context().model_copy(update={"task_spec": task}))
    unavailable = plan.model_copy(
        update={
            "subgoals": (
                plan.subgoals[0].model_copy(
                    update={
                        "objective": "search page is available",
                        "success_criteria": ("search page is available",),
                        "action_family": TaskPlanActionFamily.NAVIGATE,
                        "outcome": SubgoalOutcome(
                            subject="search page",
                            relation=SubgoalOutcomeRelation.IS_AVAILABLE,
                        ),
                    }
                ),
            )
        }
    )
    context = _context().model_copy(
        update={
            "task_spec": task,
            "environment": PlanningEnvironmentSummary(
                affordances=(
                    PlanningAffordanceSummary(
                        semantic_target_id="search-text",
                        label="Search",
                        supported_actions=("type_text", "activate"),
                    ),
                )
            ),
        }
    )

    report = TaskPlanValidator().validate(
        unavailable,
        task,
        state_version=4,
        planning_context=context,
    )

    assert report.status == TaskPlanValidationStatus.REPAIRABLE
    issue = next(item for item in report.issues if item.code == "entry_action_family_unavailable")
    assert issue.detail == "subgoal-1"
    assert issue.field == "action_family"
    assert issue.disallowed_values == ("navigate",)
    assert issue.required_semantics == "currently_bindable_action_family"


@pytest.mark.parametrize(
    ("relation", "value", "family", "current_state"),
    (
        (
            SubgoalOutcomeRelation.EQUALS,
            "Keli",
            TaskPlanActionFamily.TYPE_TEXT,
            PlanningAffordanceState(control_value="Keli"),
        ),
        (
            SubgoalOutcomeRelation.CONTAINS,
            "eli",
            TaskPlanActionFamily.TYPE_TEXT,
            PlanningAffordanceState(control_value="Keli"),
        ),
        (
            SubgoalOutcomeRelation.IS_VISIBLE,
            "Keli",
            TaskPlanActionFamily.ACTIVATE,
            PlanningAffordanceState(visible=True, control_value="Keli"),
        ),
        (
            SubgoalOutcomeRelation.IS_VISIBLE,
            "true",
            TaskPlanActionFamily.ACTIVATE,
            PlanningAffordanceState(visible=True),
        ),
        (
            SubgoalOutcomeRelation.IS_CHECKED,
            "",
            TaskPlanActionFamily.ACTIVATE,
            PlanningAffordanceState(checked=True),
        ),
        (
            SubgoalOutcomeRelation.IS_SELECTED,
            "dark",
            TaskPlanActionFamily.SELECT_OPTION,
            PlanningAffordanceState(selected_options=("dark",)),
        ),
        (
            SubgoalOutcomeRelation.IS_SELECTED,
            "true",
            TaskPlanActionFamily.SELECT_OPTION,
            PlanningAffordanceState(selected=True),
        ),
        (
            SubgoalOutcomeRelation.IS_EXPANDED,
            "",
            TaskPlanActionFamily.ACTIVATE,
            PlanningAffordanceState(expanded=True),
        ),
        (
            SubgoalOutcomeRelation.IS_AVAILABLE,
            "",
            TaskPlanActionFamily.NAVIGATE,
            PlanningAffordanceState(visible=True, enabled=True),
        ),
    ),
)
def test_validator_repairs_uniquely_proven_current_entry(
    relation: SubgoalOutcomeRelation,
    value: str,
    family: TaskPlanActionFamily,
    current_state: PlanningAffordanceState,
) -> None:
    plan = synthetic_task_plan(_context())
    entry = plan.subgoals[0].model_copy(
        update={
            "objective": SubgoalOutcome(
                subject="search text",
                relation=relation,
                value=value,
            ).description(),
            "success_criteria": ("typed predicate",),
            "action_family": family,
            "outcome": SubgoalOutcome(
                subject="search text",
                relation=relation,
                value=value,
            ),
        }
    )
    context = _context().model_copy(
        update={
            "environment": PlanningEnvironmentSummary(
                affordances=(
                    PlanningAffordanceSummary(
                        semantic_target_id="semantic:search-text",
                        label="search-text",
                        supported_actions=(family.value,),
                        current_state=current_state,
                    ),
                )
            )
        }
    )

    report = TaskPlanValidator().validate(
        plan.model_copy(update={"subgoals": (entry,)}),
        _task(),
        state_version=4,
        planning_context=context,
    )

    assert report.status == TaskPlanValidationStatus.REPAIRABLE
    assert {item.code for item in report.issues} == {
        "entry_outcome_already_satisfied"
    }
    issue = report.issues[0]
    assert issue.field == "outcome"
    assert (
        issue.required_semantics
        == "different_currently_unsatisfied_outcome_without_boolean_negation"
    )
    directives = task_plan_repair_directives(report.issues)
    assert len(directives) == 1
    assert directives[0].field == "outcome"
    assert (
        directives[0].required_semantics
        == "different_currently_unsatisfied_outcome_without_boolean_negation"
    )


def test_validator_detects_satisfied_subject_independently_of_action_target() -> None:
    plan = synthetic_task_plan(_context())
    outcome = SubgoalOutcome(
        subject="search-text",
        relation=SubgoalOutcomeRelation.IS_VISIBLE,
        value="Keli",
    )
    entry = plan.subgoals[0].model_copy(
        update={
            "objective": outcome.description(),
            "success_criteria": (outcome.description(),),
            "action_family": TaskPlanActionFamily.ACTIVATE,
            "outcome": outcome,
        }
    )
    context = _context().model_copy(
        update={
            "environment": PlanningEnvironmentSummary(
                affordances=(
                    PlanningAffordanceSummary(
                        semantic_target_id="semantic:search-text",
                        label="search-text",
                        supported_actions=("type_text",),
                        current_state=PlanningAffordanceState(
                            visible=True,
                            control_value="Keli",
                        ),
                    ),
                    PlanningAffordanceSummary(
                        semantic_target_id="semantic:search",
                        label="Search",
                        supported_actions=("activate",),
                        current_state=PlanningAffordanceState(visible=True),
                    ),
                )
            )
        }
    )

    report = TaskPlanValidator().validate(
        plan.model_copy(update={"subgoals": (entry,)}),
        _task(),
        state_version=4,
        planning_context=context,
    )

    assert report.status == TaskPlanValidationStatus.REPAIRABLE
    assert report.issues[0].code == "entry_outcome_already_satisfied"


def test_validator_keeps_unknown_ambiguous_and_causal_entry_state() -> None:
    plan = synthetic_task_plan(_context())
    outcome = SubgoalOutcome(
        subject="results panel",
        relation=SubgoalOutcomeRelation.IS_VISIBLE,
    )
    causal = plan.subgoals[0].model_copy(
        update={
            "objective": outcome.description(),
            "success_criteria": (outcome.description(),),
            "action_family": TaskPlanActionFamily.ACTIVATE,
            "outcome": outcome,
        }
    )
    causal_context = _context().model_copy(
        update={
            "environment": PlanningEnvironmentSummary(
                affordances=(
                    PlanningAffordanceSummary(
                        semantic_target_id="semantic:disclosure",
                        label="Show results",
                        supported_actions=("activate",),
                        current_state=PlanningAffordanceState(visible=True),
                    ),
                )
            )
        }
    )
    unknown_context = causal_context.model_copy(
        update={
            "environment": PlanningEnvironmentSummary(
                affordances=(
                    PlanningAffordanceSummary(
                        semantic_target_id="semantic:results-panel",
                        label="results panel",
                        supported_actions=("activate",),
                    ),
                )
            )
        }
    )
    ambiguous_context = causal_context.model_copy(
        update={
            "environment": PlanningEnvironmentSummary(
                affordances=(
                    PlanningAffordanceSummary(
                        semantic_target_id=f"semantic:results-panel:{index}",
                        label="results panel",
                        supported_actions=("activate",),
                        current_state=PlanningAffordanceState(visible=True),
                    )
                    for index in range(2)
                )
            )
        }
    )
    candidate = plan.model_copy(update={"subgoals": (causal,)})

    assert TaskPlanValidator().validate(
        candidate,
        _task(),
        state_version=4,
        planning_context=causal_context,
    ).status == TaskPlanValidationStatus.ACCEPT
    assert TaskPlanValidator().validate(
        candidate,
        _task(),
        state_version=4,
        planning_context=unknown_context,
    ).status == TaskPlanValidationStatus.ACCEPT
    assert TaskPlanValidator().validate(
        candidate,
        _task(),
        state_version=4,
        planning_context=ambiguous_context,
    ).status == TaskPlanValidationStatus.ACCEPT


@pytest.mark.parametrize(
    ("relation", "value", "code", "required_semantics"),
    (
        (
            SubgoalOutcomeRelation.CONTAINS,
            "",
            "outcome_value_required",
            "non_empty_value_for_relation",
        ),
        (
            SubgoalOutcomeRelation.IS_VISIBLE,
            "false",
            "outcome_value_forbidden",
            "empty_value_for_unary_relation",
        ),
    ),
)
def test_validator_enforces_outcome_relation_value_arity(
    relation: SubgoalOutcomeRelation,
    value: str,
    code: str,
    required_semantics: str,
) -> None:
    plan = synthetic_task_plan(_context())
    outcome = SubgoalOutcome(
        subject="search-text",
        relation=relation,
        value=value,
    )
    entry = plan.subgoals[0].model_copy(
        update={
            "objective": outcome.description(),
            "success_criteria": (outcome.description(),),
            "action_family": (
                TaskPlanActionFamily.TYPE_TEXT
                if relation == SubgoalOutcomeRelation.CONTAINS
                else TaskPlanActionFamily.ACTIVATE
            ),
            "outcome": outcome,
        }
    )
    context = _context().model_copy(
        update={
            "environment": PlanningEnvironmentSummary(
                affordances=(
                    PlanningAffordanceSummary(
                        semantic_target_id="semantic:search-text",
                        label="search-text",
                        supported_actions=("type_text", "activate"),
                        current_state=PlanningAffordanceState(visible=True),
                    ),
                )
            )
        }
    )

    report = TaskPlanValidator().validate(
        plan.model_copy(update={"subgoals": (entry,)}),
        _task(),
        state_version=4,
        planning_context=context,
    )

    assert report.status == TaskPlanValidationStatus.REPAIRABLE
    assert {item.code for item in report.issues} == {code}
    assert report.issues[0].field == "outcome.value"
    assert report.issues[0].required_semantics == required_semantics


def test_validator_allows_optional_named_selected_value() -> None:
    plan = synthetic_task_plan(_context())
    outcome = SubgoalOutcome(
        subject="theme",
        relation=SubgoalOutcomeRelation.IS_SELECTED,
        value="dark",
    )
    entry = plan.subgoals[0].model_copy(
        update={
            "objective": outcome.description(),
            "success_criteria": (outcome.description(),),
            "action_family": TaskPlanActionFamily.SELECT_OPTION,
            "outcome": outcome,
        }
    )
    context = _context().model_copy(
        update={
            "environment": PlanningEnvironmentSummary(
                affordances=(
                    PlanningAffordanceSummary(
                        semantic_target_id="semantic:theme",
                        label="theme",
                        supported_actions=("select_option",),
                        current_state=PlanningAffordanceState(
                            selected_options=("light",),
                        ),
                    ),
                )
            )
        }
    )

    report = TaskPlanValidator().validate(
        plan.model_copy(update={"subgoals": (entry,)}),
        _task(),
        state_version=4,
        planning_context=context,
    )

    assert report.status == TaskPlanValidationStatus.ACCEPT


def test_validator_checks_only_current_ready_subgoal_against_inventory() -> None:
    task = _task().model_copy(update={"task_structure": TaskStructure.MULTI_STAGE})
    first = SubgoalSpec(
        subgoal_id="enter",
        objective="search text equals Myron",
        success_criteria=("search text equals Myron",),
        evidence_requirements=("current input value",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        action_family=TaskPlanActionFamily.TYPE_TEXT,
        outcome=SubgoalOutcome(
            subject="search text",
            relation=SubgoalOutcomeRelation.EQUALS,
            value="Myron",
        ),
    )
    later = SubgoalSpec(
        subgoal_id="open",
        objective="results page is available",
        depends_on=("enter",),
        success_criteria=("results page is available",),
        evidence_requirements=("current page observation",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
        action_family=TaskPlanActionFamily.NAVIGATE,
        outcome=SubgoalOutcome(
            subject="results page",
            relation=SubgoalOutcomeRelation.IS_AVAILABLE,
        ),
    )
    plan = TaskPlan(
        plan_id="plan-entry",
        task_id=task.task_id,
        task_revision=task.revision,
        plan_version=1,
        based_on_state_version=4,
        generated_by=TaskPlanSource.LLM,
        subgoals=(first, later),
    )
    context = _context().model_copy(
        update={
            "task_spec": task,
            "environment": PlanningEnvironmentSummary(
                affordances=(
                    PlanningAffordanceSummary(
                        semantic_target_id="search-text",
                        supported_actions=("fill",),
                    ),
                )
            ),
        }
    )

    report = TaskPlanValidator().validate(
        plan,
        task,
        state_version=4,
        planning_context=context,
    )

    assert report.status == TaskPlanValidationStatus.ACCEPT


def test_validator_does_not_infer_unavailability_from_empty_environment_summary() -> None:
    task = _task().model_copy(update={"task_structure": TaskStructure.MULTI_STAGE})
    plan = synthetic_task_plan(_context().model_copy(update={"task_spec": task}))
    unknown = plan.model_copy(
        update={
            "subgoals": (
                plan.subgoals[0].model_copy(
                    update={
                        "action_family": TaskPlanActionFamily.NAVIGATE,
                        "outcome": SubgoalOutcome(
                            subject="settings page",
                            relation=SubgoalOutcomeRelation.IS_AVAILABLE,
                        ),
                    }
                ),
            )
        }
    )

    report = TaskPlanValidator().validate(
        unknown,
        task,
        state_version=4,
        planning_context=_context().model_copy(update={"task_spec": task}),
    )

    assert report.status == TaskPlanValidationStatus.ACCEPT


@pytest.mark.parametrize(
    ("action_family", "relation", "expected_status"),
    (
        (
            TaskPlanActionFamily.ACTIVATE,
            SubgoalOutcomeRelation.IS_SELECTED,
            TaskPlanValidationStatus.REPAIRABLE,
        ),
        (
            TaskPlanActionFamily.SELECT_OPTION,
            SubgoalOutcomeRelation.IS_SELECTED,
            TaskPlanValidationStatus.ACCEPT,
        ),
        (
            TaskPlanActionFamily.TYPE_TEXT,
            SubgoalOutcomeRelation.EQUALS,
            TaskPlanValidationStatus.ACCEPT,
        ),
        (
            TaskPlanActionFamily.TYPE_TEXT,
            SubgoalOutcomeRelation.IS_CHECKED,
            TaskPlanValidationStatus.REPAIRABLE,
        ),
        (
            TaskPlanActionFamily.DRAG,
            SubgoalOutcomeRelation.IS_ORDERED_AS,
            TaskPlanValidationStatus.ACCEPT,
        ),
    ),
)
def test_validator_enforces_semantic_action_outcome_matrix(
    action_family: TaskPlanActionFamily,
    relation: SubgoalOutcomeRelation,
    expected_status: TaskPlanValidationStatus,
) -> None:
    task = _task().model_copy(update={"task_structure": TaskStructure.MULTI_STAGE})
    plan = synthetic_task_plan(_context().model_copy(update={"task_spec": task}))
    candidate = plan.model_copy(
        update={
            "subgoals": (
                plan.subgoals[0].model_copy(
                    update={
                        "objective": f"setting {relation.value} dark",
                        "success_criteria": (f"setting {relation.value} dark",),
                        "action_family": action_family,
                        "outcome": SubgoalOutcome(
                            subject="setting",
                            relation=relation,
                            value="dark",
                        ),
                    }
                ),
            )
        }
    )

    report = TaskPlanValidator().validate(candidate, task, state_version=4)

    assert report.status == expected_status
    issue_codes = {item.code for item in report.issues}
    if expected_status == TaskPlanValidationStatus.REPAIRABLE:
        assert "incompatible_action_outcome" in issue_codes


def test_precondition_issue_projects_to_typed_repair_directive() -> None:
    directives = task_plan_repair_directives(
        (
            TaskPlanValidator()
            .validate(
                TaskPlan(
                    plan_id="plan-1",
                    task_id="task-1",
                    task_revision=2,
                    plan_version=1,
                    based_on_state_version=4,
                    generated_by=TaskPlanSource.LLM,
                    subgoals=(
                        SubgoalSpec(
                            subgoal_id="activate-control",
                            objective="setting control is available",
                            success_criteria=("setting control is available",),
                            evidence_requirements=("current control state",),
                            operation_class=OperationClass.REVERSIBLE_WRITE,
                            action_family=TaskPlanActionFamily.ACTIVATE,
                            outcome=SubgoalOutcome(
                                subject="setting control",
                                relation=SubgoalOutcomeRelation.IS_AVAILABLE,
                            ),
                        ),
                    ),
                ),
                _task(),
                state_version=4,
            )
            .issues
        )
    )

    assert [item.model_dump(mode="json") for item in directives] == [
        {
            "subgoal_id": "activate-control",
            "field": "outcome.relation",
            "disallowed_values": ["is_available"],
            "required_semantics": "post_action_state",
        }
    ]


def test_validator_rejects_non_monotonic_replacement_lineage() -> None:
    previous = synthetic_task_plan(_context())
    replacement = previous.model_copy(
        update={
            "plan_id": "replacement",
            "based_on_state_version": 5,
            "plan_version": previous.plan_version,
            "supersedes_plan_id": "wrong-plan",
        }
    )

    report = TaskPlanValidator().validate(
        replacement,
        _task(),
        state_version=5,
        previous_plan=previous,
    )

    assert report.status == TaskPlanValidationStatus.REJECT
    assert "invalid_replacement_plan_lineage" in {item.code for item in report.issues}


@pytest.mark.parametrize(
    "forbidden",
    (
        "use selector=#save",
        "mouse_click(120, 240)",
        "x=120 y=240",
        "backend=playwright",
        "approval_token=trusted",
        "grant capability settings.write",
    ),
)
def test_validator_rejects_executable_handles_and_authority_in_plan_text(forbidden: str) -> None:
    plan = synthetic_task_plan(_context())
    unsafe = plan.model_copy(update={"subgoals": (plan.subgoals[0].model_copy(update={"objective": forbidden}),)})

    report = TaskPlanValidator().validate(unsafe, _task(), state_version=4)

    assert report.status == TaskPlanValidationStatus.REJECT
    assert "executable_plan_content" in {item.code for item in report.issues}


def test_progress_selects_ready_subgoals_serially_and_preserves_evidence() -> None:
    task = _task()
    first = SubgoalSpec(
        subgoal_id="write",
        objective="Write",
        success_criteria=("written",),
        evidence_requirements=("receipt",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
    )
    second = SubgoalSpec(
        subgoal_id="verify",
        objective="Verify",
        depends_on=("write",),
        success_criteria=("verified",),
        evidence_requirements=("API",),
        operation_class=OperationClass.REVERSIBLE_WRITE,
    )
    plan = TaskPlan(
        plan_id="plan-1",
        task_id=task.task_id,
        task_revision=task.revision,
        plan_version=1,
        based_on_state_version=0,
        generated_by=TaskPlanSource.RULE,
        subgoals=(first, second),
    )
    progress = PlanProgress()

    assert progress.activate_next(plan) == "write"
    progress.complete("write", ("receipt-1",))
    assert progress.activate_next(plan) == "verify"
    assert progress.evidence_by_subgoal == {"write": ["receipt-1"]}


def test_synthetic_plan_copies_task_constraints_into_verification_boundary() -> None:
    plan = synthetic_task_plan(_context(state_version=0))
    assert plan.subgoals[0].evidence_requirements == ("settings API confirms dark",)


def test_state_kernel_keeps_plan_immutable_and_tracks_progress_separately() -> None:
    task = _task()
    plan = synthetic_task_plan(_context(state_version=0).model_copy(update={"task_spec": task}))
    state = StateKernel(task.task_id, task.objective)

    state.install_task_plan(plan)
    assert state.task_plan == plan
    assert state.active_subgoal() == task.objective
    state.complete_subgoal("subgoal-1", ("settings-api-receipt",))

    assert state.task_plan == plan
    assert state.plan_progress is not None
    assert state.plan_progress.completed_subgoal_ids == ["subgoal-1"]
    assert state.evidence == ["settings-api-receipt"]


def test_replan_cannot_redefine_a_verified_subgoal() -> None:
    plan = synthetic_task_plan(_context(state_version=0))
    state = StateKernel(_task().task_id, _task().objective)
    state.install_task_plan(plan)
    state.complete_subgoal("subgoal-1", ("settings-state",))
    changed = plan.subgoals[0].model_copy(update={"success_criteria": ("different outcome",)})
    replacement = plan.model_copy(
        update={
            "plan_id": "plan-2",
            "plan_version": 2,
            "supersedes_plan_id": plan.plan_id,
            "based_on_state_version": state.version,
            "subgoals": (changed,),
        }
    )

    with pytest.raises(ValueError, match="cannot redefine"):
        state.replace_task_plan(replacement)


def _verified_replacement_fixture() -> tuple[
    TaskPlan,
    TaskPlanningContext,
    SubgoalSpec,
]:
    first = synthetic_task_plan(_context(state_version=0)).subgoals[0].model_copy(
        update={"subgoal_id": "first"}
    )
    second = first.model_copy(
        update={
            "subgoal_id": "second",
            "objective": "Theme update is confirmed",
            "depends_on": ("first",),
            "success_criteria": ("theme update is confirmed",),
            "evidence_requirements": ("current theme confirmation",),
        }
    )
    previous = TaskPlan(
        plan_id="plan-previous",
        task_id=_task().task_id,
        task_revision=_task().revision,
        plan_version=1,
        based_on_state_version=0,
        generated_by=TaskPlanSource.LLM,
        subgoals=(first, second),
    )
    context = _context(state_version=7).model_copy(
        update={
            "current_plan_id": previous.plan_id,
            "current_plan_version": previous.plan_version,
            "completed_subgoal_ids": ("first",),
            "criteria_evidence_ledger": (),
        }
    )
    return previous, context, second


def test_validator_rejects_replacement_missing_verified_subgoal() -> None:
    previous, context, second = _verified_replacement_fixture()
    replacement = previous.model_copy(
        update={
            "plan_id": "plan-replacement",
            "plan_version": 2,
            "supersedes_plan_id": previous.plan_id,
            "based_on_state_version": context.state_version,
            "subgoals": (second,),
        }
    )

    report = TaskPlanValidator().validate(
        replacement,
        _task(),
        state_version=context.state_version,
        previous_plan=previous,
        planning_context=context,
    )

    assert report.status == TaskPlanValidationStatus.REJECT
    assert "verified_subgoal_missing" in {item.code for item in report.issues}


def test_validator_rejects_replacement_redefining_verified_subgoal() -> None:
    previous, context, second = _verified_replacement_fixture()
    changed = previous.subgoals[0].model_copy(
        update={"success_criteria": ("different verified state",)}
    )
    replacement = previous.model_copy(
        update={
            "plan_id": "plan-replacement",
            "plan_version": 2,
            "supersedes_plan_id": previous.plan_id,
            "based_on_state_version": context.state_version,
            "subgoals": (changed, second),
        }
    )

    report = TaskPlanValidator().validate(
        replacement,
        _task(),
        state_version=context.state_version,
        previous_plan=previous,
        planning_context=context,
    )

    assert report.status == TaskPlanValidationStatus.REJECT
    assert "verified_subgoal_redefined" in {item.code for item in report.issues}


def test_validator_requires_unfinished_unit_after_verified_progress() -> None:
    previous, context, _ = _verified_replacement_fixture()
    replacement = previous.model_copy(
        update={
            "plan_id": "plan-replacement",
            "plan_version": 2,
            "supersedes_plan_id": previous.plan_id,
            "based_on_state_version": context.state_version,
            "subgoals": (previous.subgoals[0],),
        }
    )

    report = TaskPlanValidator().validate(
        replacement,
        _task(),
        state_version=context.state_version,
        previous_plan=previous,
        planning_context=context,
    )

    assert report.status == TaskPlanValidationStatus.REPAIRABLE
    assert {item.code for item in report.issues} == {
        "replacement_missing_unfinished_subgoal"
    }


def test_subgoal_verifier_requires_independent_passed_evidence() -> None:
    from affordance_runtime.task_planning import VerifierBackedSubgoalVerifier

    subgoal = synthetic_task_plan(_context(state_version=0)).subgoals[0]
    verifier = VerifierBackedSubgoalVerifier()
    report = VerificationReport(
        VerificationStatus.PASSED,
        evidence=[
            VerificationEvidence(
                "observation_metadata",
                "saved",
                True,
                "post_action_observation",
                evidence_id="settings-state",
                criterion_ids=(criterion_id("subgoal", subgoal.subgoal_id, 0),),
                requirement_ids=(evidence_requirement_id("subgoal", subgoal.subgoal_id, 0),),
                environment_revision="revision-1",
                snapshot_id="snapshot-1",
                strength="strong",
            )
        ],
    )
    observation = Observation("revision-1", snapshot_id="snapshot-1")

    matched = verifier.verify(subgoal, report, observation)
    unmatched = verifier.verify(
        subgoal,
        VerificationReport(VerificationStatus.PASSED),
        observation,
    )

    assert matched.passed
    assert matched.match.evidence_ids == ("settings-state",)
    assert not unmatched.passed


class RepairingTaskPlanModel:
    provider = "fixed"
    model = "fixed-task-planner"
    endpoint_class = "test"
    last_call = None

    def __init__(self) -> None:
        self.calls = 0

    async def generate_structured(self, messages, output_schema, config):  # type: ignore[no-untyped-def]
        del config
        self.calls += 1
        if self.calls == 1:
            assert len(messages) == 2
            assert '"task_id"' not in messages[-1].content
            assert '"source_request_ref"' not in messages[-1].content
            assert '"created_at_s"' not in messages[-1].content
            return output_schema.model_validate(
                {
                    "entry_subgoal": {
                        "subgoal_id": "discover",
                        "outcome": {
                            "subject": "Press the setting control",
                            "relation": "is_completed",
                        },
                        "evidence_requirements": ["settings API"],
                        "operation_class": "reversible_write",
                        "action_family": "activate",
                    }
                }
            )
        assert "validation_errors" in messages[-1].content
        return output_schema.model_validate(
            {
                "entry_subgoal": {
                    "subgoal_id": "discover",
                    "outcome": {
                        "subject": "current setting",
                        "relation": "is_visible",
                    },
                    "evidence_requirements": ["settings API"],
                    "operation_class": "reversible_write",
                    "action_family": "activate",
                },
                "remaining_subgoals": [
                    {
                        "subgoal_id": "write",
                        "outcome": {
                            "subject": "setting",
                            "relation": "equals",
                            "value": "dark",
                        },
                        "depends_on": ["discover"],
                        "evidence_requirements": ["settings API"],
                        "operation_class": "reversible_write",
                        "action_family": "select_option",
                    },
                    {
                        "subgoal_id": "confirm",
                        "outcome": {
                            "subject": "confirmed setting",
                            "relation": "equals",
                            "value": "dark",
                        },
                        "depends_on": ["write"],
                        "evidence_requirements": ["settings API"],
                        "operation_class": "reversible_write",
                        "action_family": "wait",
                    },
                ]
            }
        )


def test_llm_task_planner_repairs_once_then_returns_runtime_bound_plan() -> None:
    import asyncio

    model = RepairingTaskPlanModel()
    task = _task().model_copy(update={"task_structure": TaskStructure.MULTI_STAGE})
    plan = asyncio.run(
        LLMTaskPlanner(model).plan(_context().model_copy(update={"task_spec": task}))
    )

    assert model.calls == 2
    assert plan.generated_by == TaskPlanSource.LLM
    assert plan.task_id == _task().task_id
    assert len(plan.subgoals) == 3
    assert type(plan.subgoals[0].outcome) is SubgoalOutcome
    assert (
        TaskPlanValidator().validate(plan, task, state_version=4).status
        == TaskPlanValidationStatus.ACCEPT
    )


class ActionInstructionRepairModel:
    provider = "fixed"
    model = "fixed-task-planner"
    endpoint_class = "test"
    last_call = None

    def __init__(self) -> None:
        self.calls = 0

    async def generate_structured(self, messages, output_schema, config):  # type: ignore[no-untyped-def]
        del config
        self.calls += 1
        if self.calls == 2:
            assert "action_instruction_subgoal" in messages[-1].content
        return output_schema.model_validate(
            {
                "entry_subgoal": {
                    "subgoal_id": "results-visible",
                    "outcome": (
                        {
                            "subject": "Press the Search button",
                            "relation": "is_completed",
                        }
                        if self.calls == 1
                        else {
                            "subject": "Search results for Myron",
                            "relation": "is_visible",
                        }
                    ),
                    "evidence_requirements": ["post-action results observation"],
                    "operation_class": "reversible_write",
                    "action_family": "activate",
                },
                "remaining_subgoals": [
                    {
                        "subgoal_id": "confirmed",
                        "outcome": {
                            "subject": "task confirmation",
                            "relation": "is_completed",
                        },
                        "depends_on": ["results-visible"],
                        "evidence_requirements": ["fresh confirmation observation"],
                        "operation_class": "reversible_write",
                        "action_family": "activate",
                    }
                ],
            }
        )


def test_llm_task_planner_repairs_action_instruction_into_outcome() -> None:
    import asyncio

    task = _task().model_copy(update={"task_structure": TaskStructure.MULTI_STAGE})
    context = _context().model_copy(update={"task_spec": task})
    model = ActionInstructionRepairModel()

    plan = asyncio.run(LLMTaskPlanner(model).plan(context))

    assert model.calls == 2
    assert plan.subgoals[0].objective == "Search results for Myron is visible"
    assert (
        TaskPlanValidator().validate(plan, task, state_version=4).status
        == TaskPlanValidationStatus.ACCEPT
    )


class ContextualEntryRepairModel:
    provider = "fixed"
    model = "fixed-task-planner"
    endpoint_class = "test"
    last_call = None

    def __init__(self) -> None:
        self.calls = 0

    async def generate_structured(self, messages, output_schema, config):  # type: ignore[no-untyped-def]
        del config
        self.calls += 1
        entry_mapping = output_schema.model_json_schema()["properties"]["entry_subgoal"][
            "discriminator"
        ]["mapping"]
        assert set(entry_mapping) == {"type_text"}
        if self.calls == 2:
            assert '"field": "action_family"' in messages[-1].content
            assert '"disallowed_values": ["navigate"]' in messages[-1].content
            assert '"required_semantics": "currently_bindable_action_family"' in messages[-1].content
            assert '"required_semantics": "at_least_two_outcome_subgoals"' in messages[-1].content
        return output_schema.model_validate(
            {
                "entry_subgoal": {
                    "subgoal_id": "entry",
                    "outcome": (
                        {
                            "subject": "search page",
                            "relation": "is_available",
                        }
                        if self.calls == 1
                        else {
                            "subject": "search text",
                            "relation": "equals",
                            "value": "Myron",
                        }
                    ),
                    "evidence_requirements": ["fresh current-state observation"],
                    "operation_class": "reversible_write",
                    "action_family": "navigate" if self.calls == 1 else "type_text",
                },
                "remaining_subgoals": (
                    []
                    if self.calls == 1
                    else [
                        {
                            "subgoal_id": "complete",
                            "outcome": {
                                "subject": "search submission",
                                "relation": "is_completed",
                            },
                            "depends_on": ["entry"],
                            "evidence_requirements": ["fresh submission observation"],
                            "operation_class": "reversible_write",
                            "action_family": "activate",
                        }
                    ]
                ),
            }
        )


def test_llm_task_planner_repairs_unavailable_entry_family_once() -> None:
    import asyncio

    task = _task().model_copy(update={"task_structure": TaskStructure.MULTI_STAGE})
    context = _context().model_copy(
        update={
            "task_spec": task,
            "environment": PlanningEnvironmentSummary(
                affordances=(
                    PlanningAffordanceSummary(
                        semantic_target_id="search-text",
                        supported_actions=("type_text",),
                    ),
                )
            ),
        }
    )
    model = ContextualEntryRepairModel()

    plan = asyncio.run(LLMTaskPlanner(model).plan(context))

    assert model.calls == 2
    assert plan.subgoals[0].action_family == TaskPlanActionFamily.TYPE_TEXT
    assert (
        TaskPlanValidator().validate(
            plan,
            task,
            state_version=4,
            planning_context=context,
        ).status
        == TaskPlanValidationStatus.ACCEPT
    )

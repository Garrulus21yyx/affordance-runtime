from __future__ import annotations

import ast
from pathlib import Path

from affordance_runtime.simplified_runtime_contracts import StateCriterionRelation
from affordance_runtime.task_intake import (
    OperationClass,
    SourcedTaskClaim,
    TaskClaimKind,
    TaskObligationKind,
    TaskObligationRelation,
    TaskObligationSpec,
    TaskObligationValueSource,
    TaskSpec,
)
from affordance_runtime.task_plan_contracts import PlanCandidate, TaskPlanGeneratorSource
from affordance_runtime.task_plan_generators import (
    PlanCandidateGeneratorRouter,
    PricingPlanCandidateGenerator,
    RulePlanCandidateGenerator,
)
from affordance_runtime.task_planning import (
    TaskPlanningBudgetSummary,
    TaskPlanningContext,
)

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "affordance_runtime"


def _budget() -> TaskPlanningBudgetSummary:
    return TaskPlanningBudgetSummary(
        steps_remaining=10,
        observations_remaining=10,
        replans_remaining=2,
        recoveries_remaining=2,
        effectful_actions_remaining=3,
    )


def _context(task_spec: TaskSpec) -> TaskPlanningContext:
    return TaskPlanningContext(
        task_spec=task_spec,
        state_version=4,
        remaining_budget=_budget(),
    )


def _task_with_obligations() -> TaskSpec:
    return TaskSpec(
        task_id="task-1",
        revision=2,
        objective="Enter Alice then submit",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("name_field", "submit_button"),
        success_criteria=("name field equals Alice", "form submitted"),
        evidence_requirements=("field value evidence", "submission evidence"),
        requested_capabilities=("form.write",),
        source_request_ref="request-1",
        source_claims=(
            SourcedTaskClaim(
                claim_id="claim-name",
                kind=TaskClaimKind.EFFECT,
                statement="name field equals Alice",
                source_ref="request-1",
                source_unit_ids=("source-unit:name",),
            ),
            SourcedTaskClaim(
                claim_id="claim-submit",
                kind=TaskClaimKind.EFFECT,
                statement="form submitted",
                source_ref="request-1",
                source_unit_ids=("source-unit:submit",),
            ),
        ),
        obligations=(
            TaskObligationSpec(
                obligation_id="obligation:name",
                kind=TaskObligationKind.EFFECT,
                subject="name_field",
                relation=TaskObligationRelation.EQUALS,
                value_source=TaskObligationValueSource.LITERAL,
                expected_value="Alice",
                claim_ids=("claim-name",),
                evidence_requirements=("field value evidence",),
            ),
            TaskObligationSpec(
                obligation_id="obligation:submit",
                kind=TaskObligationKind.EFFECT,
                subject="submit_button",
                relation=TaskObligationRelation.IS_COMPLETED,
                claim_ids=("claim-submit",),
                depends_on=("obligation:name",),
                evidence_requirements=("submission evidence",),
                terminal=True,
            ),
        ),
    )


def test_rule_task_plan_generator_produces_draft_without_authority_fields() -> None:
    context = _context(_task_with_obligations())

    draft = RulePlanCandidateGenerator().generate(context)

    assert isinstance(draft, PlanCandidate)
    assert draft.generated_by == TaskPlanGeneratorSource.RULE
    assert draft.task_spec_identity == context.task_spec.identity
    assert not hasattr(draft, "plan_id")
    assert not hasattr(draft, "plan_version")
    assert tuple(step.step_id for step in draft.steps) == (
        "obligation:name",
        "obligation:submit",
    )
    assert draft.steps[1].depends_on == ("obligation:name",)
    first_criterion = draft.steps[0].completion_criteria[0]
    assert first_criterion.subject == "name_field"
    assert first_criterion.relation == StateCriterionRelation.EQUALS
    assert first_criterion.expected_value == "Alice"
    assert draft.steps[0].source_refs[0].source_unit_id == "source-unit:name"


def test_rule_task_plan_generator_directly_uses_canonical_obligations() -> None:
    context = _context(_task_with_obligations())

    draft = RulePlanCandidateGenerator().generate(context)

    assert tuple(step.step_id for step in draft.steps) == (
        "obligation:name",
        "obligation:submit",
    )
    assert all(step.objective for step in draft.steps)
    source = (SOURCE_ROOT / "task_plan_generators.py").read_text(encoding="utf-8")
    assert "RuleTaskPlanner" not in source
    assert "PlanCandidateProjector" not in source
    assert ".legacy_planner" not in source
    assert ".projector" not in source


def test_synthetic_flat_generator_returns_single_draft_step() -> None:
    task = TaskSpec(
        task_id="flat",
        revision=1,
        objective="Read the account status",
        operation_class=OperationClass.READ_ONLY,
        targets=("account",),
        success_criteria=("account status visible",),
        evidence_requirements=("DOM state evidence",),
        source_request_ref="request-1",
    )

    draft = RulePlanCandidateGenerator().generate(_context(task))

    assert tuple(step.step_id for step in draft.steps) == ("step:implicit",)
    assert draft.steps[0].objective == "Read the account status"
    assert draft.steps[0].source_refs[0].source_id == "request-1"


def test_pricing_task_plan_generator_returns_draft_not_accepted_plan() -> None:
    task = TaskSpec(
        task_id="pricing",
        revision=1,
        objective="Reveal pricing limits",
        operation_class=OperationClass.READ_ONLY,
        targets=("pricing",),
        success_criteria=("pricing limits visible",),
        evidence_requirements=("DOM state evidence",),
        source_request_ref="request-1",
    )

    draft = PricingPlanCandidateGenerator().generate(_context(task))

    assert isinstance(draft, PlanCandidate)
    assert draft.generated_by == TaskPlanGeneratorSource.RULE
    assert tuple(step.step_id for step in draft.steps) == ("reveal-pro", "reveal-enterprise")
    assert draft.steps[1].depends_on == ("reveal-pro",)


def test_draft_generator_router_preserves_rule_and_complex_selection() -> None:
    calls: list[str] = []

    class RecordingGenerator:
        def __init__(self, name: str) -> None:
            self.name = name

        def generate(self, context: TaskPlanningContext) -> PlanCandidate:
            calls.append(self.name)
            return RulePlanCandidateGenerator().generate(context)

    context = _context(_task_with_obligations())
    router = PlanCandidateGeneratorRouter(
        rule_generator=RecordingGenerator("rule"),
        complex_generator=RecordingGenerator("complex"),
    )

    router.generate(context, complex_task=True)

    assert calls == ["rule"]


def test_rule_generator_rejects_forbidden_obligation_content() -> None:
    task = _task_with_obligations().model_copy(
        update={
            "source_claims": (
                SourcedTaskClaim(
                    claim_id="claim-name",
                    kind=TaskClaimKind.EFFECT,
                    statement="use selector #name",
                    source_ref="request-1",
                    source_unit_ids=("source-unit:name",),
                ),
                SourcedTaskClaim(
                    claim_id="claim-submit",
                    kind=TaskClaimKind.EFFECT,
                    statement="form submitted",
                    source_ref="request-1",
                    source_unit_ids=("source-unit:submit",),
                ),
            ),
            "obligations": (
                TaskObligationSpec(
                    obligation_id="obligation:name",
                    kind=TaskObligationKind.EFFECT,
                    subject="name_field",
                    relation=TaskObligationRelation.EQUALS,
                    value_source=TaskObligationValueSource.LITERAL,
                    expected_value="Alice",
                    claim_ids=("claim-name",),
                    evidence_requirements=("field value evidence",),
                ),
                TaskObligationSpec(
                    obligation_id="obligation:submit",
                    kind=TaskObligationKind.EFFECT,
                    subject="submit_button",
                    relation=TaskObligationRelation.IS_COMPLETED,
                    claim_ids=("claim-submit",),
                    depends_on=("obligation:name",),
                    evidence_requirements=("submission evidence",),
                    terminal=True,
                ),
            ),
        }
    )

    try:
        RulePlanCandidateGenerator().generate(_context(task))
    except ValueError as exc:
        assert "forbidden implementation detail" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("forbidden selector content was accepted")


def test_task_plan_generators_do_not_import_runtime_authority_modules() -> None:
    source = (SOURCE_ROOT / "task_plan_generators.py").read_text(encoding="utf-8")
    lowered = source.casefold()
    forbidden = (
        "affordance_runtime.coordinator",
        "affordance_runtime.state_kernel",
        "affordance_runtime.trace",
        "affordance_runtime.browser_session",
        "affordance_runtime.benchmarks",
    )
    for item in forbidden:
        assert item not in lowered

    tree = ast.parse(source)
    generate_methods = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "generate"
    ]
    assert generate_methods
    for method in generate_methods:
        calls = [
            node
            for node in ast.walk(method)
            if isinstance(node, ast.Attribute)
            and node.attr in {"install_task_plan", "replace_task_plan"}
        ]
        assert calls == []

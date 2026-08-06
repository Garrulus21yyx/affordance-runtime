from __future__ import annotations

import ast
from pathlib import Path

from affordance_runtime.task_intake import (
    OperationClass,
    TaskRequirement,
    TaskSemanticPayload,
    TaskSpec,
)
from affordance_runtime.task_plan_contracts import PlanProposal, TaskPlanGeneratorSource
from affordance_runtime.task_plan_generators import (
    PlanProposalGeneratorRouter,
    PricingPlanProposalGenerator,
    RulePlanProposalGenerator,
)
from affordance_runtime.task_planner import TaskPlanningBudgetSummary, TaskPlanningRequest
from affordance_runtime.verification.contracts import SuccessExpression

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "affordance_runtime"


def _budget() -> TaskPlanningBudgetSummary:
    return TaskPlanningBudgetSummary(
        steps_remaining=10,
        observations_remaining=10,
        replans_remaining=2,
        recoveries_remaining=2,
        effectful_actions_remaining=3,
    )


def _request(task_spec: TaskSpec) -> TaskPlanningRequest:
    return TaskPlanningRequest(
        task_spec=task_spec,
        state_version=4,
        remaining_budget=_budget(),
    )


def _requirement(identifier: str, subject: str, operation: OperationClass) -> TaskRequirement:
    return TaskRequirement(
        requirement_id=identifier,
        payload=TaskSemanticPayload(
            kind="effect",
            subject=subject,
            operation_class=operation,
        ),
        source_anchor_refs=(f"anchor:{identifier}",),
    )


def _task_with_requirements() -> TaskSpec:
    return TaskSpec(
        task_id="task-1",
        revision=2,
        objective="Enter Alice then submit",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=(
            _requirement("effect:name", "name_field", OperationClass.REVERSIBLE_WRITE),
            _requirement("effect:submit", "submit_button", OperationClass.REVERSIBLE_WRITE),
        ),
        allowed_effect_refs=("effect:name", "effect:submit"),
        success=SuccessExpression(
            expression_id="success:form",
            operator="criterion",
            criterion_id="criterion:form",
            requirement_refs=("effect:name", "effect:submit"),
        ),
        source_request_ref="request-1",
    )


def test_rule_generator_uses_flat_canonical_requirements() -> None:
    request = _request(_task_with_requirements())

    draft = RulePlanProposalGenerator().generate(request)

    assert isinstance(draft, PlanProposal)
    assert draft.generated_by == TaskPlanGeneratorSource.RULE
    assert draft.task_spec_identity == request.task_spec.identity
    assert not hasattr(draft, "plan_id")
    assert not hasattr(draft, "plan_version")
    assert tuple(step.step_id for step in draft.steps) == ("step:implicit",)
    assert draft.steps[0].requirement_refs == ("effect:name", "effect:submit")
    assert draft.steps[0].objective == "name_field"


def test_synthetic_flat_generator_returns_single_draft_step() -> None:
    task = TaskSpec(
        task_id="flat",
        revision=1,
        objective="Read the account status",
        operation_class=OperationClass.READ_ONLY,
        requirements=(_requirement("requirement:account", "account", OperationClass.READ_ONLY),),
        allowed_effect_refs=("requirement:account",),
        success=SuccessExpression(
            expression_id="success:account",
            operator="criterion",
            criterion_id="criterion:account",
            requirement_refs=("requirement:account",),
        ),
        source_request_ref="request-1",
    )

    draft = RulePlanProposalGenerator().generate(_request(task))

    assert tuple(step.step_id for step in draft.steps) == ("step:implicit",)
    assert draft.steps[0].objective == "account"
    assert draft.steps[0].source_refs[0].source_id == "request-1"


def test_pricing_task_plan_generator_returns_draft_not_accepted_plan() -> None:
    task = TaskSpec(
        task_id="pricing",
        revision=1,
        objective="Reveal pricing limits",
        operation_class=OperationClass.READ_ONLY,
        requirements=(_requirement("requirement:pricing", "pricing", OperationClass.READ_ONLY),),
        allowed_effect_refs=("requirement:pricing",),
        success=SuccessExpression(
            expression_id="success:pricing",
            operator="criterion",
            criterion_id="criterion:pricing",
            requirement_refs=("requirement:pricing",),
        ),
        source_request_ref="request-1",
    )

    draft = PricingPlanProposalGenerator().generate(_request(task))

    assert isinstance(draft, PlanProposal)
    assert draft.generated_by == TaskPlanGeneratorSource.RULE
    assert tuple(step.step_id for step in draft.steps) == ("reveal-pro", "reveal-enterprise")
    assert draft.steps[1].depends_on == ("reveal-pro",)


def test_draft_generator_router_preserves_rule_and_complex_selection() -> None:
    calls: list[str] = []

    class RecordingGenerator:
        def __init__(self, name: str) -> None:
            self.name = name

        def generate(self, request: TaskPlanningRequest) -> PlanProposal:
            calls.append(self.name)
            return RulePlanProposalGenerator().generate(request)

    request = _request(_task_with_requirements())
    router = PlanProposalGeneratorRouter(
        rule_generator=RecordingGenerator("rule"),
        complex_generator=RecordingGenerator("complex"),
    )

    router.generate(request, complex_task=True)

    assert calls == ["complex"]


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
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "generate"
    ]
    assert generate_methods
    for method in generate_methods:
        calls = [
            node
            for node in ast.walk(method)
            if isinstance(node, ast.Attribute) and node.attr in {"install_task_plan", "replace_task_plan"}
        ]
        assert calls == []


def test_task_planning_serializer_is_bounded_and_authority_preserving() -> None:
    from affordance_runtime.planning_request_serializer import (
        serialize_task_planning_request,
    )

    payload = serialize_task_planning_request(_request(_task_with_requirements()))
    task_payload = payload["task_spec"]

    assert task_payload["allowed_effect_refs"] == ["effect:name", "effect:submit"]
    assert "task_structure" not in task_payload
    encoded = repr(payload).casefold()
    for forbidden in (
        "selector",
        "coordinate",
        "backend_handle",
        "locator",
        "approval_token",
    ):
        assert forbidden not in encoded

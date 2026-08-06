from __future__ import annotations

import pytest

from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.verification.contracts import (
    CriterionEvaluation,
    CriterionStatus,
    OutputSpec,
    SuccessExpression,
    TaskCompletionEvaluation,
)
from affordance_runtime.verification.task_completion import TaskCompletionEvaluator


def _leaf(criterion_id: str) -> SuccessExpression:
    return SuccessExpression(
        expression_id=f"expr:{criterion_id}",
        operator="criterion",
        criterion_id=criterion_id,
    )


def test_typed_completion_contracts_are_immutable_and_task_bound() -> None:
    success = SuccessExpression(
        expression_id="success:root",
        operator="all_of",
        children=(_leaf("criterion:saved"), _leaf("criterion:dialog-absent")),
    )
    task = TaskSpec(
        task_id="task:save",
        revision=1,
        objective="save settings",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("settings",),
        success_criteria=("legacy display only",),
        success=success,
        required_outputs=(
            OutputSpec(
                output_id="saved_record",
                materialization_criterion_id="criterion:output",
                source_binding_requirement=("source:any",),
            ),
        ),
        source_request_ref="request:save",
    )
    evaluation = TaskCompletionEvaluation(
        status=CriterionStatus.SATISFIED,
        root_criterion_id=task.success.expression_id,
        criterion_results=(
            CriterionEvaluation("criterion:saved", CriterionStatus.SATISFIED),
        ),
        result_payload={"saved_record": {"id": "record:1"}},
    )

    assert task.success == success
    assert evaluation.result_payload == {"saved_record": {"id": "record:1"}}
    with pytest.raises((AttributeError, TypeError)):
        evaluation.result_payload["saved_record"] = {}  # type: ignore[index]


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: SuccessExpression(expression_id="root", operator="criterion"), "criterion_id"),
        (
            lambda: SuccessExpression(
                expression_id="root",
                operator="not",
                children=(_leaf("one"), _leaf("two")),
            ),
            "exactly one",
        ),
    ],
)
def test_success_expression_rejects_incomplete_shapes(
    build: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build()  # type: ignore[operator]


@pytest.mark.parametrize(
    ("case", "criterion_results", "result_payload", "source_bindings", "uncertain", "expected"),
    [
        (
            "complete closure",
            (
                CriterionEvaluation("criterion:saved", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:dialog-absent", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:constraint", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:external", CriterionStatus.SATISFIED),
                CriterionEvaluation(
                    "criterion:recheck",
                    CriterionStatus.SATISFIED,
                    authoritative_final_recheck=True,
                ),
                CriterionEvaluation("criterion:output", CriterionStatus.SATISFIED),
            ),
            {"saved_record": {"id": "record:1"}},
            {"saved_record": ("resource:record:1",)},
            (),
            CriterionStatus.SATISFIED,
        ),
        (
            "receipt report plan and prose are not criteria",
            (),
            {
                "receipt_success": True,
                "latest_report_passed": True,
                "plan_exhausted": True,
                "planner_summary": "done",
                "saved_record": {"id": "record:1"},
            },
            {"saved_record": ("resource:record:1",)},
            (),
            CriterionStatus.UNKNOWN,
        ),
        (
            "constraint violation",
            (
                CriterionEvaluation("criterion:saved", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:dialog-absent", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:constraint", CriterionStatus.UNSATISFIED),
            ),
            {},
            {},
            (),
            CriterionStatus.UNSATISFIED,
        ),
        (
            "external effect remains uncertain",
            (
                CriterionEvaluation("criterion:saved", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:dialog-absent", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:constraint", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:output", CriterionStatus.SATISFIED),
            ),
            {"saved_record": {"id": "record:1"}},
            {"saved_record": ("resource:record:1",)},
            ("effect:send",),
            CriterionStatus.UNKNOWN,
        ),
        (
            "final recheck is not authoritative",
            (
                CriterionEvaluation("criterion:saved", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:dialog-absent", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:constraint", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:external", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:recheck", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:output", CriterionStatus.SATISFIED),
            ),
            {"saved_record": {"id": "record:1"}},
            {"saved_record": ("resource:record:1",)},
            (),
            CriterionStatus.UNKNOWN,
        ),
        (
            "required output lacks source binding",
            (
                CriterionEvaluation("criterion:saved", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:dialog-absent", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:constraint", CriterionStatus.SATISFIED),
                CriterionEvaluation("criterion:external", CriterionStatus.SATISFIED),
                CriterionEvaluation(
                    "criterion:recheck",
                    CriterionStatus.SATISFIED,
                    authoritative_final_recheck=True,
                ),
                CriterionEvaluation("criterion:output", CriterionStatus.SATISFIED),
            ),
            {"saved_record": {"id": "record:1"}},
            {},
            (),
            CriterionStatus.UNSATISFIED,
        ),
    ],
)
def test_task_completion_requires_full_typed_closure(
    case: str,
    criterion_results: tuple[CriterionEvaluation, ...],
    result_payload: dict[str, object],
    source_bindings: dict[str, tuple[str, ...]],
    uncertain: tuple[str, ...],
    expected: CriterionStatus,
) -> None:
    del case
    task = TaskSpec(
        task_id="task:save",
        revision=1,
        objective="save settings",
        operation_class=OperationClass.EXTERNAL_SIDE_EFFECT,
        targets=("settings",),
        success_criteria=("legacy display only",),
        success=SuccessExpression(
            expression_id="success:root",
            operator="all_of",
            children=(_leaf("criterion:saved"), _leaf("criterion:dialog-absent")),
        ),
        constraint_criterion_ids=("criterion:constraint",),
        external_effect_criterion_ids=("criterion:external",),
        final_recheck_criterion_ids=("criterion:recheck",),
        required_outputs=(
            OutputSpec(
                output_id="saved_record",
                materialization_criterion_id="criterion:output",
            ),
        ),
        source_request_ref="request:save",
    )

    evaluation = TaskCompletionEvaluator().evaluate(
        task_spec=task,
        criterion_results=criterion_results,
        result_payload=result_payload,
        output_source_bindings=source_bindings,
        uncertain_external_effects=uncertain,
    )

    assert evaluation.status == expected
    assert evaluation.completed is (expected == CriterionStatus.SATISFIED)


@pytest.mark.parametrize(
    "operation_class",
    (OperationClass.EXTERNAL_SIDE_EFFECT, OperationClass.IRREVERSIBLE),
)
def test_high_risk_completion_requires_declared_effect_and_authoritative_recheck(
    operation_class: OperationClass,
) -> None:
    task = TaskSpec(
        task_id="task:high-risk",
        revision=1,
        objective="perform external effect",
        operation_class=operation_class,
        targets=("external-system",),
        success_criteria=("effect observed",),
        success=_leaf("criterion:effect-observed"),
        source_request_ref="request:high-risk",
    )

    evaluation = TaskCompletionEvaluator().evaluate(
        task_spec=task,
        criterion_results=(
            CriterionEvaluation(
                "criterion:effect-observed", CriterionStatus.SATISFIED
            ),
        ),
        result_payload={"effect": "observed"},
    )

    assert evaluation.status == CriterionStatus.UNKNOWN
    assert evaluation.uncertain_external_effects == (
        "task_spec:external_effect_evaluation_required",
    )
    assert evaluation.missing_rechecks == (
        "task_spec:authoritative_final_recheck_required",
    )

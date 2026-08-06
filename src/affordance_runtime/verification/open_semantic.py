"""Fail-closed routing for unresolved open-semantic step criteria."""

from __future__ import annotations

from affordance_runtime.criteria import (
    CriterionExpr,
    OpenSemanticCriterion,
    criterion_nodes,
)
from affordance_runtime.source_context import TaskSpecGap
from affordance_runtime.verification.contracts import CriterionEvaluation, CriterionStatus

OPEN_SEMANTIC_UNRESOLVED = "OPEN_SEMANTIC_UNRESOLVED"


def unresolved_open_semantic_gaps(
    expressions: tuple[CriterionExpr, ...],
    evaluation: CriterionEvaluation | None,
) -> tuple[TaskSpecGap, ...]:
    if evaluation is None or evaluation.status != CriterionStatus.UNSUPPORTED:
        return ()
    criteria = tuple(
        node
        for expression in expressions
        for node in criterion_nodes(expression)
        if isinstance(node, OpenSemanticCriterion)
    )
    return tuple(
        TaskSpecGap(
            gap_id=f"gap:{OPEN_SEMANTIC_UNRESOLVED}:{criterion.criterion_id}",
            missing_field=f"open_semantic:{criterion.operator_name}",
            anchor_ids=criterion.source_refs,
            clarification=(
                "Clarification is required because semantic criterion "
                f"'{criterion.operator_name}' has no admitted resolver."
            ),
        )
        for criterion in criteria
    )

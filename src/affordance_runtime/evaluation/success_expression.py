"""Bounded typed boolean success-expression evaluation."""

from __future__ import annotations

from collections.abc import Mapping

from affordance_runtime.evaluation.contracts import CriterionEvaluationStatus

MAX_EXPRESSION_DEPTH = 8
MAX_EXPRESSION_NODES = 64


def evaluate_success_expression(
    expression: Mapping[str, object] | None,
    statuses: dict[str, CriterionEvaluationStatus],
) -> bool | None:
    if expression is None:
        if not statuses:
            return True
        expression = {"all": [{"criterion": item} for item in statuses]}
    nodes = [0]
    return _evaluate(expression, statuses, 1, nodes)


def _evaluate(value, statuses, depth: int, nodes: list[int]) -> bool | None:
    nodes[0] += 1
    if depth > MAX_EXPRESSION_DEPTH or nodes[0] > MAX_EXPRESSION_NODES or not isinstance(value, Mapping) or len(value) != 1:
        raise ValueError("success expression exceeds the bounded grammar")
    if "criterion" in value:
        identity = value["criterion"]
        if not isinstance(identity, str) or identity not in statuses:
            raise ValueError("success expression references an unknown criterion")
        status = statuses[identity]
        if status == CriterionEvaluationStatus.SATISFIED:
            return True
        if status == CriterionEvaluationStatus.UNSATISFIED:
            return False
        return None
    if "not" in value:
        result = _evaluate(value["not"], statuses, depth + 1, nodes)
        return None if result is None else not result
    operator = "all" if "all" in value else "any" if "any" in value else ""
    items = value.get(operator) if operator else None
    if not operator or not isinstance(items, tuple | list) or not 1 <= len(items) <= 64:
        raise ValueError("success expression operator is unsupported")
    results = tuple(_evaluate(item, statuses, depth + 1, nodes) for item in items)
    if operator == "all":
        return False if False in results else None if None in results else True
    return True if True in results else None if None in results else False

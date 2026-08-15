from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]
RUNTIME = ROOT / "src" / "affordance_runtime"


def _source(relative: str) -> str:
    return (RUNTIME / relative).read_text(encoding="utf-8")


def test_execution_control_and_vision_do_not_parse_task_prose_or_benchmark_slugs() -> None:
    assert not (RUNTIME / "task/set_objective_state.py").exists()
    governed = ("world/vision_escalation.py",)
    banned = (
        "task_instruction",
        ".instruction",
        "click-shades",
        "grid-coordinate",
        "visual-addition",
        "task_predicate_truth",
        "has_universal_quantifier",
    )
    for relative in governed:
        source = _source(relative)
        assert all(token not in source for token in banned), relative


def test_removed_witness_compilers_and_task_relative_projection_stay_absent() -> None:
    assert not (RUNTIME / "task/set_objective_compiler.py").exists()
    assert not (
        RUNTIME / "benchmarks/external_smoke/browsergym_visual_predicate.py"
    ).exists()
    assert "task_predicate_truth" not in _source(
        "surfaces/browsergym/semantics.py"
    )
    assert "repeated_leaf" not in _source(
        "surfaces/browsergym/backend.py"
    ).casefold()


def test_catalog_set_directive_uses_explicit_mode_not_empty_set_truthiness() -> None:
    tree = ast.parse(_source("model_policy/grounded_tool_catalog.py"))
    suspicious = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        direct_name = node.test.id if isinstance(node.test, ast.Name) else ""
        negated_name = (
            node.test.operand.id
            if isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
            and isinstance(node.test.operand, ast.Name)
            else ""
        )
        if {direct_name, negated_name} & {"allowed_action_ids", "admitted_target_ids"}:
            suspicious.append(ast.unparse(node.test))
    assert suspicious == []

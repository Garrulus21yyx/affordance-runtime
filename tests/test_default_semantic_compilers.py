from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from affordance_runtime.default_semantic_compilers import (
    DefaultSemanticCompilerCallbacks,
    build_default_semantic_compiler_registry,
)
from affordance_runtime.semantic_compilers import (
    SemanticCompilation,
    SemanticCompilerContext,
    SemanticConstraints,
)


@dataclass(frozen=True)
class FixtureAffordance:
    action: str
    role: str = ""
    state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FixtureContext:
    task_spec: dict[str, Any]
    affordances: tuple[FixtureAffordance, ...]


def _compile_as(
    calls: list[str],
    name: str,
    action_kind: str,
) -> Callable[[SemanticCompilerContext], SemanticCompilation]:
    def compile(context: SemanticCompilerContext) -> SemanticCompilation:
        del context
        calls.append(name)
        return SemanticCompilation(action_kind=action_kind, target_affordance_id=name)

    return compile


def _callbacks(calls: list[str]) -> DefaultSemanticCompilerCallbacks:
    def constrain(
        context: SemanticCompilerContext,
        permitted: list[str],
        targets: dict[str, list[str]],
    ) -> SemanticConstraints:
        del context
        calls.append("constraints")
        return SemanticConstraints(tuple(permitted), {key: tuple(value) for key, value in targets.items()})

    return DefaultSemanticCompilerCallbacks(
        calendar_event=_compile_as(calls, "calendar", "drag"),
        copy_operation=_compile_as(calls, "copy", "type_text"),
        incremental_control=_compile_as(calls, "incremental", "press_key"),
        semantic_operation=_compile_as(calls, "semantic", "activate"),
        planner_constraints=constrain,
    )


def test_default_registry_factory_preserves_declared_rule_precedence() -> None:
    calls: list[str] = []
    registry = build_default_semantic_compiler_registry(_callbacks(calls))

    assert [rule.compiler_id for rule in registry.rules] == [
        "authored-calendar-range-v1",
        "bounded-text-transform-v1",
        "typed-incremental-control-v1",
        "typed-affordance-semantics-v1",
    ]
    assert [rule.compiler_id for rule in registry.constraint_rules] == [
        "typed-planner-constraints-v1"
    ]

    result = registry.compile(
        FixtureContext(
            task_spec={"operation_class": "reversible_write"},
            affordances=(
                FixtureAffordance("fill", state={"range_selectable": True}),
                FixtureAffordance("press", role="slider", state={"context_text": "1"}),
            ),
        )
    )

    assert result is not None
    assert result.compiler_id == "authored-calendar-range-v1"
    assert result.target_affordance_id == "calendar"
    assert calls == ["calendar"]


def test_default_registry_factory_keeps_evidence_and_operation_scope_explicit() -> None:
    registry = build_default_semantic_compiler_registry(_callbacks([]))

    expected_sources = (
        "runtime-generic-calendar-conformance",
        "runtime-generic-text-transform-conformance",
        "runtime-generic-incremental-control-conformance",
        "runtime-generic-affordance-conformance",
        "runtime-generic-planner-constraint-conformance",
    )
    all_rules = (*registry.rules, *registry.constraint_rules)

    assert tuple(rule.evidence.source for rule in all_rules) == expected_sources
    assert all(rule.evidence.version == "1" for rule in all_rules)
    assert all(rule.evidence.negative_examples for rule in all_rules)
    assert all(rule.evidence.verifier_requirements for rule in all_rules)
    assert all("browsergym" not in repr(rule).casefold() for rule in all_rules)
    assert all("miniwob" not in repr(rule).casefold() for rule in all_rules)
    assert all(
        rule.operation_classes
        == ("read_only", "navigation", "reversible_write", "external_side_effect", "irreversible")
        for rule in registry.rules
    )


def test_default_registry_factory_rejects_inapplicable_and_unsupported_contexts() -> None:
    calls: list[str] = []
    registry = build_default_semantic_compiler_registry(_callbacks(calls))
    empty = FixtureContext(task_spec={"operation_class": "read_only"}, affordances=())
    unsupported = FixtureContext(
        task_spec={"operation_class": "undeclared"},
        affordances=(FixtureAffordance("activate"),),
    )

    assert registry.compile(empty) is None
    assert registry.constrain(empty, ["activate"], {"activate": ["target"]}) is None
    assert registry.compile(unsupported) is None
    assert calls == []

"""Typed, inspectable System-1 semantic compiler registry."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


class SemanticCompilerContext(Protocol):
    task_spec: dict[str, Any]
    affordances: tuple[Any, ...]


@dataclass(frozen=True)
class SemanticCompilation:
    action_kind: str
    target_affordance_id: str = ""
    destination_affordance_id: str = ""
    parameters: dict[str, str | int | float | bool | list[str]] = field(default_factory=dict)
    compiler_id: str = ""
    evidence_ref: str = ""


@dataclass(frozen=True)
class SemanticConstraints:
    permitted_action_kinds: tuple[str, ...]
    compatible_target_ids: dict[str, tuple[str, ...]]
    allowed_press_keys: tuple[str, ...] = ()
    allowed_text_values: tuple[str, ...] = ()
    require_bound_text_source: bool = False
    compiler_id: str = ""
    evidence_ref: str = ""


@dataclass(frozen=True)
class SemanticCompilerEvidence:
    required_state_keys: tuple[str, ...]
    output_action_kinds: tuple[str, ...]
    verifier_requirements: tuple[str, ...]
    negative_examples: tuple[str, ...]
    source: str
    version: str

    def __post_init__(self) -> None:
        if not self.output_action_kinds or not self.verifier_requirements:
            raise ValueError("semantic compiler evidence requires output and verifier declarations")
        if not self.negative_examples or not self.source or not self.version:
            raise ValueError("semantic compiler evidence requires negative examples, source, and version")


SemanticCompileFn = Callable[[SemanticCompilerContext], SemanticCompilation | None]
SemanticApplicabilityFn = Callable[[SemanticCompilerContext], bool]
SemanticConstraintFn = Callable[
    [SemanticCompilerContext, list[str], dict[str, list[str]]],
    SemanticConstraints | None,
]


@dataclass(frozen=True)
class SemanticCompilerRule:
    compiler_id: str
    supported_intents: tuple[str, ...]
    operation_classes: tuple[str, ...]
    applicability_description: str
    applicability: SemanticApplicabilityFn
    compile: SemanticCompileFn
    evidence: SemanticCompilerEvidence

    def __post_init__(self) -> None:
        if not self.compiler_id or not self.supported_intents or not self.operation_classes:
            raise ValueError("semantic compiler identity and applicability scope must be declared")
        if not self.applicability_description:
            raise ValueError("semantic compiler applicability must be explained")


@dataclass(frozen=True)
class SemanticConstraintRule:
    compiler_id: str
    applicability_description: str
    applicability: SemanticApplicabilityFn
    constrain: SemanticConstraintFn
    evidence: SemanticCompilerEvidence

    def __post_init__(self) -> None:
        if not self.compiler_id or not self.applicability_description:
            raise ValueError("semantic constraint compiler must declare identity and applicability")


@dataclass(frozen=True)
class SemanticCompilerRegistry:
    rules: tuple[SemanticCompilerRule, ...] = ()
    constraint_rules: tuple[SemanticConstraintRule, ...] = ()

    def __post_init__(self) -> None:
        compiler_ids = [item.compiler_id for item in self.rules]
        compiler_ids.extend(item.compiler_id for item in self.constraint_rules)
        if len(compiler_ids) != len(set(compiler_ids)):
            raise ValueError("semantic compiler ids must be unique")

    def compile(self, context: SemanticCompilerContext) -> SemanticCompilation | None:
        operation_class = str(context.task_spec.get("operation_class") or "")
        for rule in self.rules:
            if operation_class and operation_class not in rule.operation_classes:
                continue
            if not _required_state_present(context, rule.evidence.required_state_keys):
                continue
            if not rule.applicability(context):
                continue
            result = rule.compile(context)
            if result is None:
                continue
            if result.action_kind not in rule.evidence.output_action_kinds:
                raise ValueError(
                    f"semantic compiler {rule.compiler_id} emitted undeclared action {result.action_kind}"
                )
            return SemanticCompilation(
                action_kind=result.action_kind,
                target_affordance_id=result.target_affordance_id,
                destination_affordance_id=result.destination_affordance_id,
                parameters=dict(result.parameters),
                compiler_id=rule.compiler_id,
                evidence_ref=f"{rule.evidence.source}@{rule.evidence.version}",
            )
        return None

    def constrain(
        self,
        context: SemanticCompilerContext,
        permitted_action_kinds: list[str],
        compatible_target_ids: dict[str, list[str]],
    ) -> SemanticConstraints | None:
        for rule in self.constraint_rules:
            if not _required_state_present(context, rule.evidence.required_state_keys):
                continue
            if not rule.applicability(context):
                continue
            result = rule.constrain(
                context,
                list(permitted_action_kinds),
                {key: list(value) for key, value in compatible_target_ids.items()},
            )
            if result is None:
                continue
            undeclared = set(result.permitted_action_kinds) - set(rule.evidence.output_action_kinds)
            if undeclared:
                raise ValueError(
                    f"semantic constraint compiler {rule.compiler_id} emitted undeclared actions: "
                    f"{sorted(undeclared)}"
                )
            return SemanticConstraints(
                permitted_action_kinds=result.permitted_action_kinds,
                compatible_target_ids=dict(result.compatible_target_ids),
                allowed_press_keys=result.allowed_press_keys,
                allowed_text_values=result.allowed_text_values,
                require_bound_text_source=result.require_bound_text_source,
                compiler_id=rule.compiler_id,
                evidence_ref=f"{rule.evidence.source}@{rule.evidence.version}",
            )
        return None

    @property
    def digest(self) -> str:
        """Return a stable identity for reporting and immutable-run checks."""

        payload = {
            "rules": [_rule_identity(item) for item in self.rules],
            "constraint_rules": [_rule_identity(item) for item in self.constraint_rules],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    @property
    def compiler_ids(self) -> tuple[str, ...]:
        return tuple(item.compiler_id for item in self.rules) + tuple(
            item.compiler_id for item in self.constraint_rules
        )

    @classmethod
    def disabled(cls) -> "SemanticCompilerRegistry":
        return cls()


def _required_state_present(
    context: SemanticCompilerContext,
    required_state_keys: tuple[str, ...],
) -> bool:
    available = {
        str(key)
        for affordance in context.affordances
        for key in getattr(affordance, "state", {})
    }
    return set(required_state_keys).issubset(available)


def _rule_identity(rule: SemanticCompilerRule | SemanticConstraintRule) -> dict[str, object]:
    payload: dict[str, object] = {
        "compiler_id": rule.compiler_id,
        "applicability_description": rule.applicability_description,
        "evidence": {
            "required_state_keys": rule.evidence.required_state_keys,
            "output_action_kinds": rule.evidence.output_action_kinds,
            "verifier_requirements": rule.evidence.verifier_requirements,
            "negative_examples": rule.evidence.negative_examples,
            "source": rule.evidence.source,
            "version": rule.evidence.version,
        },
    }
    if isinstance(rule, SemanticCompilerRule):
        payload.update(
            {
                "supported_intents": rule.supported_intents,
                "operation_classes": rule.operation_classes,
            }
        )
    return payload

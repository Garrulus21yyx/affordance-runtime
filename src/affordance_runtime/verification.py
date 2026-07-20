"""Verifier ladder and preflight checks."""

from __future__ import annotations

import ast
import operator
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

from affordance_runtime.contracts import (
    ActionContract,
    Condition,
    ExecutionReceipt,
    Observation,
    RuntimeErrorCode,
    VerifierSpec,
)


class Verifier(Protocol):
    kind: str

    def verify(self, spec: VerifierSpec, receipt: ExecutionReceipt, observation: Observation) -> bool:
        ...


@dataclass
class EvidenceVerifier:
    kind: str = "evidence"

    def verify(self, spec: VerifierSpec, receipt: ExecutionReceipt, observation: Observation) -> bool:
        value = receipt.evidence.get(spec.target)
        return value == spec.expected if spec.strict else bool(value)


@dataclass
class ObservationMetadataVerifier:
    kind: str = "observation_metadata"

    def verify(self, spec: VerifierSpec, receipt: ExecutionReceipt, observation: Observation) -> bool:
        value = observation.metadata.get(spec.target)
        return value == spec.expected if spec.strict else bool(value)


@dataclass
class VerifierLadder:
    """Prefer structural receipts before model or human judgment."""

    verifiers: list[Verifier] = field(default_factory=lambda: [EvidenceVerifier(), ObservationMetadataVerifier()])

    def verify(self, specs: list[VerifierSpec], receipt: ExecutionReceipt, observation: Observation) -> bool:
        if not specs:
            return receipt.success
        for spec in specs:
            verifier = next((item for item in self.verifiers if item.kind == spec.kind), None)
            if verifier is None:
                if spec.strict:
                    return False
                continue
            if not verifier.verify(spec, receipt, observation):
                return False
        return True


@dataclass(frozen=True)
class ConditionResult:
    condition: Condition
    passed: bool
    observed: Any = None
    expected: Any = None
    reason: str = ""


_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
}


def preflight(contract: ActionContract, observation: Observation) -> RuntimeErrorCode | None:
    if contract.environment_revision != observation.environment_revision:
        return RuntimeErrorCode.STALE_OBSERVATION
    facts = {
        **observation.metadata,
        "observation": {
            "environment_revision": observation.environment_revision,
            "url": observation.url,
            "dom_hash": observation.dom_hash,
            "screenshot_ref": observation.screenshot_ref,
        },
        "params": contract.parameters,
        "target": contract.locator,
    }
    if not evaluate_conditions(contract.preconditions, facts):
        return RuntimeErrorCode.PRECONDITION_FAILED
    return None


def evaluate_condition(condition: Condition, facts: Mapping[str, Any]) -> ConditionResult:
    """Evaluate a conservative declarative predicate without using ``eval``."""

    predicate = condition.predicate.strip()
    try:
        parts = [part.strip() for part in predicate.split(" and ") if part.strip()]
        if len(parts) > 1:
            results = [evaluate_condition(Condition(part, condition.description, condition.required), facts) for part in parts]
            return ConditionResult(
                condition=condition,
                passed=all(result.passed for result in results),
                observed=[result.observed for result in results],
                expected=[result.expected for result in results],
                reason="; ".join(result.reason for result in results if result.reason),
            )

        path, op, expected_raw = _split_predicate(predicate)
        if op is None:
            literal = _parse_value(path)
            if isinstance(literal, (bool, type(None))) and path.lower() in {"true", "false", "none", "null"}:
                return ConditionResult(condition, bool(literal), observed=literal)
            observed = _resolve_path(facts, path)
            return ConditionResult(condition, bool(observed), observed=observed)

        observed = _resolve_path(facts, path)
        expected = _resolve_expected(facts, expected_raw)
        return ConditionResult(condition, _OPERATORS[op](observed, expected), observed, expected)
    except Exception as exc:
        return ConditionResult(condition, False, reason=str(exc))


def evaluate_conditions(conditions: list[Condition], facts: Mapping[str, Any]) -> bool:
    return all(result.passed or not result.condition.required for result in (evaluate_condition(item, facts) for item in conditions))


def _split_predicate(predicate: str) -> tuple[str, str | None, str]:
    for op in ("==", "!=", ">=", "<=", ">", "<"):
        if op in predicate:
            left, right = predicate.split(op, 1)
            return left.strip(), op, right.strip()
    return predicate, None, ""


def _resolve_expected(facts: Mapping[str, Any], raw: str) -> Any:
    if raw.startswith("$"):
        return _resolve_path(facts, raw.removeprefix("$.").removeprefix("$"))
    if "." in raw:
        try:
            return _resolve_path(facts, raw)
        except KeyError:
            pass
    return _parse_value(raw)


def _parse_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"none", "null"}:
        return None
    try:
        return ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return raw.strip("\"'")


def _resolve_path(facts: Mapping[str, Any], path: str) -> Any:
    value: Any = facts
    for part in path.split("."):
        if isinstance(value, Mapping) and part in value:
            value = value[part]
        else:
            raise KeyError(f"missing condition path: {path}")
    return value


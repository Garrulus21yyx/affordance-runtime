"""Verifier ladder and preflight checks."""

from __future__ import annotations

import ast
import json
import operator
from dataclasses import dataclass, field
from enum import StrEnum
from html.parser import HTMLParser
from time import time
from typing import Any, Callable, Mapping, Protocol
from urllib.request import urlopen

from affordance_runtime.contracts import (
    ActionContract,
    Condition,
    ExecutionReceipt,
    Observation,
    RuntimeErrorCode,
    VerifierSpec,
    gesture_preflight,
)


class Verifier(Protocol):
    kind: str

    def verify(self, spec: VerifierSpec, receipt: ExecutionReceipt, observation: Observation) -> bool: ...


class VerificationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class VerificationEvidence:
    verifier_kind: str
    target: str
    passed: bool
    source: str
    observed: Any = None
    expected: Any = None
    evidence_id: str = ""
    criterion_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    environment_revision: str = ""
    snapshot_id: str = ""
    observed_at_s: float = 0.0
    strength: str = "weak"


@dataclass(frozen=True)
class VerificationReport:
    status: VerificationStatus
    evidence: list[VerificationEvidence] = field(default_factory=list)
    reason: str = ""

    @property
    def passed(self) -> bool:
        return self.status == VerificationStatus.PASSED


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
class DomContainsVerifier:
    kind: str = "dom_contains"

    def verify(self, spec: VerifierSpec, receipt: ExecutionReceipt, observation: Observation) -> bool:
        del receipt
        html = str(observation.metadata.get("html") or "")
        expected = str(spec.expected)
        return expected in html


@dataclass
class DomAbsentVerifier:
    kind: str = "dom_absent"

    def verify(self, spec: VerifierSpec, receipt: ExecutionReceipt, observation: Observation) -> bool:
        del receipt
        return str(spec.expected) not in str(observation.metadata.get("html") or "")


class _DomAttributeParser(HTMLParser):
    def __init__(self, target_attribute: str, target_value: str, observed_attribute: str) -> None:
        super().__init__(convert_charrefs=True)
        self.target_attribute = target_attribute
        self.target_value = target_value
        self.observed_attribute = observed_attribute
        self.observed: Any = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag
        values = {key: (value or "") for key, value in attrs}
        if values.get(self.target_attribute) == self.target_value:
            self.observed = values.get(self.observed_attribute)


@dataclass
class DomAttributeVerifier:
    """Verify one attribute on one post-observation DOM element."""

    kind: str = "dom_attribute"

    def verify(self, spec: VerifierSpec, receipt: ExecutionReceipt, observation: Observation) -> bool:
        del receipt
        if not isinstance(spec.expected, Mapping):
            return False
        target_attribute = str(spec.expected.get("target_attribute") or "")
        attribute = str(spec.expected.get("attribute") or "")
        if not target_attribute or not attribute or not spec.target:
            return False
        parser = _DomAttributeParser(target_attribute, spec.target, attribute)
        parser.feed(str(observation.metadata.get("html") or ""))
        parser.close()
        return parser.observed == spec.expected.get("value")


@dataclass
class ControlStateVerifier:
    """Verify a generic post-observation property by an opaque control key."""

    kind: str = "control_state"

    def verify(self, spec: VerifierSpec, receipt: ExecutionReceipt, observation: Observation) -> bool:
        del receipt
        if not isinstance(spec.expected, Mapping):
            return False
        states = observation.metadata.get("control_states")
        if not isinstance(states, Mapping):
            return False
        state = states.get(spec.target)
        if not isinstance(state, Mapping):
            return False
        field_name = str(spec.expected.get("field") or "")
        observed = state.get(field_name)
        if "changed_from" in spec.expected:
            return observed not in {None, ""} and observed != spec.expected.get("changed_from")
        return observed == spec.expected.get("value")


@dataclass
class StateDeltaOrTerminalVerifier:
    """Require a changed state revision or a positive adapter-declared terminal result."""

    kind: str = "state_delta_or_terminal"

    def verify(self, spec: VerifierSpec, receipt: ExecutionReceipt, observation: Observation) -> bool:
        if receipt.evidence.get("terminal_success") is True:
            return True
        if receipt.evidence.get("terminal_failure") is True:
            return False
        if observation.metadata.get("active_control") == spec.target:
            return True
        if isinstance(spec.expected, Mapping):
            states = observation.metadata.get("control_states")
            state = states.get(spec.target) if isinstance(states, Mapping) else None
            field_name = str(spec.expected.get("field") or "")
            if isinstance(state, Mapping) and field_name:
                observed = state.get(field_name)
                if observed != spec.expected.get("changed_from"):
                    return True
        return bool(observation.environment_revision) and (observation.environment_revision != receipt.started_revision)


@dataclass
class HttpJsonVerifier:
    """Strong fixture/API verifier for persisted business effects."""

    kind: str = "http_json"

    def verify(self, spec: VerifierSpec, receipt: ExecutionReceipt, observation: Observation) -> bool:
        del receipt, observation
        if not isinstance(spec.expected, Mapping):
            return False
        try:
            with urlopen(spec.target, timeout=2.0) as response:  # noqa: S310 - URL is capability/policy constrained
                value: Any = json.loads(response.read())
            for part in str(spec.expected.get("path") or "").split("."):
                if part:
                    value = value[part]
            return value == spec.expected.get("value")
        except Exception:
            return False


@dataclass
class VerifierLadder:
    """Prefer structural receipts before model or human judgment."""

    verifiers: list[Verifier] = field(
        default_factory=lambda: [
            EvidenceVerifier(),
            HttpJsonVerifier(),
            ObservationMetadataVerifier(),
            DomContainsVerifier(),
            DomAbsentVerifier(),
            DomAttributeVerifier(),
            ControlStateVerifier(),
            StateDeltaOrTerminalVerifier(),
        ]
    )

    def verify(self, specs: list[VerifierSpec], receipt: ExecutionReceipt, observation: Observation) -> bool:
        if not specs:
            return receipt.success
        return self.verify_report(specs, receipt, observation).passed

    def verify_report(
        self,
        specs: list[VerifierSpec],
        receipt: ExecutionReceipt,
        observation: Observation,
    ) -> VerificationReport:
        if not specs:
            # A receipt-only result remains available for the debug API but is
            # explicitly marked inconclusive for the task-level coordinator.
            status = VerificationStatus.INCONCLUSIVE if receipt.success else VerificationStatus.FAILED
            return VerificationReport(status, reason="no independent verifier was specified")
        evidence: list[VerificationEvidence] = []
        for index, spec in enumerate(specs):
            verifier = next((item for item in self.verifiers if item.kind == spec.kind), None)
            if verifier is None:
                if spec.strict:
                    return VerificationReport(
                        VerificationStatus.ERROR,
                        evidence,
                        f"strict verifier is not registered: {spec.kind}",
                    )
                continue
            passed = verifier.verify(spec, receipt, observation)
            adapter_terminal_success = (
                spec.kind == "state_delta_or_terminal"
                and receipt.evidence.get("terminal_success") is True
            )
            if spec.kind == "evidence":
                observed = receipt.evidence.get(spec.target)
            elif spec.kind == "dom_contains":
                observed = str(spec.expected) in str(observation.metadata.get("html") or "")
            elif spec.kind == "dom_absent":
                observed = str(spec.expected) not in str(observation.metadata.get("html") or "")
            elif spec.kind == "http_json":
                observed = passed
            elif spec.kind in {"dom_attribute", "control_state", "state_delta_or_terminal"}:
                observed = passed
            else:
                observed = observation.metadata.get(spec.target)
            evidence.append(
                VerificationEvidence(
                    verifier_kind=spec.kind,
                    target=spec.target,
                    passed=passed,
                    source=(
                        "execution_receipt"
                        if spec.kind == "evidence"
                        else "external_evaluator"
                        if adapter_terminal_success
                        else "independent_http_json"
                        if spec.kind == "http_json"
                        else "post_action_observation"
                    ),
                    observed=observed,
                    expected=spec.expected,
                    evidence_id=(
                        f"verification:{observation.snapshot_id or observation.environment_revision}:"
                        f"{index}:{spec.evidence_key or f'{spec.kind}:{spec.target}'}"
                    ),
                    criterion_ids=spec.criterion_ids,
                    requirement_ids=spec.requirement_ids,
                    environment_revision=observation.environment_revision,
                    snapshot_id=observation.snapshot_id,
                    observed_at_s=observation.observed_at_s,
                    strength=(
                        "weak"
                        if spec.kind in {"evidence", "state_delta_or_terminal"}
                        and not adapter_terminal_success
                        else "strong"
                    ),
                )
            )
            if not passed:
                return VerificationReport(
                    VerificationStatus.FAILED, evidence, f"verifier failed: {spec.kind}:{spec.target}"
                )
        if not evidence:
            return VerificationReport(VerificationStatus.NOT_APPLICABLE, reason="no applicable verifier")
        return VerificationReport(VerificationStatus.PASSED, evidence)


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


def preflight(
    contract: ActionContract,
    observation: Observation,
    *,
    require_snapshot_identity: bool = True,
    require_environment_revision: bool = True,
) -> RuntimeErrorCode | None:
    if require_environment_revision and contract.environment_revision != observation.environment_revision:
        return RuntimeErrorCode.STALE_OBSERVATION
    if contract.page_revision and contract.page_revision != observation.page_revision:
        return RuntimeErrorCode.STALE_PAGE_REVISION
    if require_snapshot_identity and contract.snapshot_id and contract.snapshot_id != observation.snapshot_id:
        return RuntimeErrorCode.SNAPSHOT_MISMATCH
    if contract.expires_at_s and time() > contract.expires_at_s:
        return RuntimeErrorCode.LEASE_EXPIRED
    if contract.target_fingerprint:
        observed_fingerprint = observation.target_fingerprints.get(
            contract.target_fingerprint_key or contract.affordance_id
        )
        if observed_fingerprint != contract.target_fingerprint:
            return RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH
    if contract.gesture_binding is not None:
        gesture_error = gesture_preflight(
            contract.gesture_binding,
            observation,
            require_snapshot_identity=require_snapshot_identity,
            require_environment_revision=require_environment_revision,
        )
        if gesture_error is not None:
            return gesture_error
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
            results = [
                evaluate_condition(Condition(part, condition.description, condition.required), facts) for part in parts
            ]
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
    return all(
        result.passed or not result.condition.required
        for result in (evaluate_condition(item, facts) for item in conditions)
    )


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

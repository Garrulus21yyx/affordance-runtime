"""Schema-owned JSON codec for canonical target-loop case evidence."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, cast

from affordance_runtime.agent.runtime_failure import (
    FailureKind,
    FailureStage,
    RuntimeFailure,
)
from affordance_runtime.benchmarks.target_loop.contracts import (
    CASE_SCHEMA_VERSION,
    BenchmarkCaseResult,
    CaseFacts,
    CaseFailureOrigin,
    MetricMeasurement,
    TerminalReasonCode,
)


def public_case_evidence(result: BenchmarkCaseResult) -> dict[str, object]:
    """Serialize every declared public case field from one schema authority."""
    payload = {
        "schema_version": result.case_schema_version,
        **{
            item.name: _json_value(getattr(result, item.name))
            for item in fields(BenchmarkCaseResult)
            if item.name != "failure_reason"
        },
    }
    if result.case_schema_version == "target-loop-case.v6":
        facts = cast(dict[str, object], payload["failure_facts"])
        facts.pop("runtime_failure")
    return payload


def decode_public_case_evidence(payload: dict[str, object]) -> BenchmarkCaseResult:
    """Validate and reconstruct the complete public typed case evidence view."""

    expected = {
        item.name for item in fields(BenchmarkCaseResult) if item.name != "failure_reason"
    } | {"schema_version"}
    if set(payload) != expected:
        raise ValueError("public case evidence fields do not match the declared schema")
    if payload["schema_version"] != payload["case_schema_version"]:
        raise ValueError("public case schema identity is inconsistent")
    if payload["schema_version"] not in {"target-loop-case.v6", CASE_SCHEMA_VERSION}:
        raise ValueError("public case evidence schema is unsupported")
    measurements = {}
    metric_fields = {item.name for item in fields(MetricMeasurement)}
    for name, value in _dict(payload["measurements"]).items():
        if not isinstance(name, str) or not isinstance(value, dict) or set(value) != metric_fields:
            raise ValueError("public case metric evidence is malformed")
        measurements[name] = MetricMeasurement(**value)
    raw_facts = _dict(payload["failure_facts"])
    fact_fields = {item.name for item in fields(CaseFacts)}
    legacy_fact_fields = fact_fields - {"runtime_failure"}
    expected_fact_fields = (
        legacy_fact_fields
        if payload["schema_version"] == "target-loop-case.v6"
        else fact_fields
    )
    if set(raw_facts) != expected_fact_fields:
        raise ValueError("public case facts are incomplete")
    string_fact_names = fact_fields - {"component_origin", "runtime_failure"}
    if any(not isinstance(raw_facts[name], str) for name in string_fact_names):
        raise TypeError("public case fact codes must use strings")
    raw_origin = raw_facts["component_origin"]
    if not isinstance(raw_origin, str):
        raise TypeError("public component origin must be a string")
    facts = CaseFacts(
        runtime_reason_code=raw_facts["runtime_reason_code"],
        agent_failure_code=raw_facts["agent_failure_code"],
        policy_failure_code=raw_facts["policy_failure_code"],
        component_origin=CaseFailureOrigin(raw_origin),
        component_code=raw_facts["component_code"],
        component_exception_class=raw_facts["component_exception_class"],
        watchdog_code=raw_facts["watchdog_code"],
        cleanup_code=raw_facts["cleanup_code"],
        cleanup_exception_class=raw_facts["cleanup_exception_class"],
        harness_integrity_code=raw_facts["harness_integrity_code"],
        runtime_failure=_decode_runtime_failure(raw_facts.get("runtime_failure")),
    )
    values = {
        item.name: payload[item.name]
        for item in fields(BenchmarkCaseResult)
        if item.name != "failure_reason"
    }
    values["failure_reason"] = ""
    values["measurements"] = measurements
    values["failure_facts"] = facts
    failure_origin = values["failure_origin"]
    if not isinstance(failure_origin, str):
        raise ValueError("public failure origin is malformed")
    values["failure_origin"] = CaseFailureOrigin(failure_origin)
    terminal = values["terminal_reason_code"]
    if terminal is not None and not isinstance(terminal, str):
        raise ValueError("terminal reason code is malformed")
    values["terminal_reason_code"] = TerminalReasonCode(terminal) if terminal else None
    return BenchmarkCaseResult(**cast(Any, values))


def _decode_runtime_failure(value: object) -> RuntimeFailure | None:
    if value is None:
        return None
    raw = _dict(value)
    expected = {item.name for item in fields(RuntimeFailure)}
    if set(raw) != expected or any(not isinstance(item, str) for item in raw.values()):
        raise ValueError("public Runtime failure is malformed")
    return RuntimeFailure(
        FailureStage(raw["stage"]),
        FailureKind(raw["kind"]),
        raw["code"],
        raw["root_id"],
        raw["attempt_id"],
        raw["exception_class"],
    )


def _json_value(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _dict(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("public case evidence object is malformed")
    return value

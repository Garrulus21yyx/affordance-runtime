"""Compatibility-only projection of canonical case facts into legacy fields."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.benchmarks.target_loop.contracts import (
    CaseFacts,
    CaseFailureOrigin,
    TerminalReasonCode,
    terminal_reason_from_facts,
)


@dataclass(frozen=True)
class LegacyCaseProjection:
    case_failure_code: str
    terminal_reason_code: TerminalReasonCode | None
    termination_origin: str


def project_legacy_case_fields(status: str, facts: CaseFacts) -> LegacyCaseProjection:
    """Derive compatibility fields without owning benchmark classification."""

    case_failure_code = (
        facts.watchdog_code
        or (f"policy_{facts.policy_failure_code}" if facts.policy_failure_code else "")
        or facts.agent_failure_code
        or facts.runtime_reason_code
        or facts.component_code
        or facts.cleanup_code
        or facts.harness_integrity_code
    )
    has_runtime_truth = bool(
        facts.runtime_failure
        or facts.runtime_reason_code
        or facts.agent_failure_code
        or facts.policy_failure_code
        or terminal_reason_from_facts(
            status, facts.runtime_reason_code, facts.agent_failure_code,
        )
    )
    termination_origin = (
        "harness_watchdog"
        if facts.watchdog_code
        else "component"
        if facts.component_origin is not CaseFailureOrigin.NONE
        else "runtime"
        if has_runtime_truth
        else "cleanup"
        if facts.cleanup_code
        else "runtime"
    )
    return LegacyCaseProjection(
        case_failure_code,
        terminal_reason_from_facts(
            status, facts.runtime_reason_code, facts.agent_failure_code,
        ),
        termination_origin,
    )

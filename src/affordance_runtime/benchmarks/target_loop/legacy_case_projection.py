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

    task_terminal = facts.task_outcome_kind == "terminal_failure"
    case_failure_code = (
        facts.watchdog_code
        or (f"policy_{facts.policy_failure_code}" if facts.policy_failure_code else "")
        or facts.agent_failure_code
        or facts.runtime_reason_code
        or (facts.task_outcome_code if status == "blocked" else "")
        or facts.component_code
        or facts.cleanup_code
        or facts.harness_integrity_code
    )
    has_runtime_truth = bool(
        facts.runtime_failure
        or facts.runtime_reason_code
        or facts.agent_failure_code
        or facts.policy_failure_code
    )
    pure_task_terminal = task_terminal and not has_runtime_truth
    terminal_reason = (
        None
        if pure_task_terminal
        else terminal_reason_from_facts(
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
        else ""
        if pure_task_terminal
        else "runtime"
    )
    return LegacyCaseProjection(
        case_failure_code,
        terminal_reason,
        termination_origin,
    )

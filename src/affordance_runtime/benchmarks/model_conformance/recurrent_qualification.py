"""Pure qualification summary over exact recurrent matrix attempts."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .classification import ModelPolicyCapabilityStatus
from .decision_matrix import DECISION_VARIANTS
from .matrix_runner import DecisionMatrixResult

CRITICAL_CASE_IDS = (
    "actions-8-correct-8", "actions-16-correct-8", "non-first-direct",
    "destinations-0-correct-0", "destinations-1-correct-1",
    "destinations-2-correct-2", "destinations-2-correct-2-similar-ids",
    "cross-action-destination",
)
_PRIMARY_CASES = {
    "select_action": "select", "request_observation": "observe",
    "request_action_page": "page", "ask_user": "ask", "propose_done": "done",
    "wait": "wait", "abort": "abort",
}


@dataclass(frozen=True)
class RecurrentQualification:
    mode: str
    repetitions: int
    status: str
    admitted: bool
    decision_success_counts: tuple[tuple[str, int, int], ...]
    critical_success_counts: tuple[tuple[str, int, int], ...]
    failure_counts: tuple[tuple[str, int], ...]
    runtime_success_count: int
    retry_count: int
    fallback_count: int
    safety_violation_count: int
    errors: tuple[str, ...]


def qualify_recurrent_result(result: DecisionMatrixResult, *, support_attestation: bool) -> RecurrentQualification:
    by_case = Counter(item.case_id for item in result.attempts)
    success = Counter(item.case_id for item in result.attempts if item.success)
    decisions = tuple(
        (variant, success[_PRIMARY_CASES[variant]], by_case[_PRIMARY_CASES[variant]])
        for variant in DECISION_VARIANTS
    )
    critical = tuple((case, success[case], by_case[case]) for case in CRITICAL_CASE_IDS if by_case[case])
    failures = Counter(item.failure_stage for item in result.attempts if not item.success)
    provider_only = bool(failures) and set(failures) == {"provider_unavailable"}
    decision_gate = all(passed == total == result.repetitions for _, passed, total in decisions)
    critical_gate = support_attestation or all(passed == total == result.repetitions for _, passed, total in critical)
    runtime_gate = result.runtime_control_success_count == len(DECISION_VARIANTS)
    admitted = decision_gate and critical_gate and runtime_gate and not failures
    if provider_only:
        status = ModelPolicyCapabilityStatus.INCONCLUSIVE_PROVIDER_AVAILABILITY.value
    elif admitted and support_attestation:
        status = "full_recurrent_policy_supported"
    elif admitted:
        status = "candidate_passed"
    else:
        status = "candidate_failed" if not support_attestation else ModelPolicyCapabilityStatus.PARTIAL.value
    errors = tuple(f"{kind}: {count}" for kind, count in sorted(failures.items()))
    return RecurrentQualification(
        "support" if support_attestation else "candidate", result.repetitions, status, admitted,
        decisions, critical, tuple(sorted(failures.items())), result.runtime_control_success_count,
        result.retry_count, result.fallback_count, 0, errors,
    )

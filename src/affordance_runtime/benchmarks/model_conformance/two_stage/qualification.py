"""Pure diagnosis of routing, payload, coupling and provider availability."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .contracts import TwoStageMatrixResult


class TwoStageDiagnosticConclusion(StrEnum):
    ROUTING_BOTTLENECK = "routing_bottleneck"
    PAYLOAD_BOTTLENECK = "payload_bottleneck"
    COUPLING_BOTTLENECK = "coupling_bottleneck"
    HANDOFF_BOTTLENECK = "handoff_bottleneck"
    TWO_STAGE_UNNECESSARY = "two_stage_unnecessary"
    PROFILE_UNSUITABLE = "profile_unsuitable"
    PROVIDER_AVAILABILITY_INCONCLUSIVE = "provider_availability_inconclusive"


class TwoStageProfileStatus(StrEnum):
    NOT_RUN = "not_run"
    ROUTING_PARTIAL = "routing_partial"
    PAYLOAD_PARTIAL = "payload_partial"
    COUPLING_RELIEF_OBSERVED = "coupling_relief_observed"
    CANDIDATE_PASSED = "candidate_passed"
    CANDIDATE_FAILED = "candidate_failed"
    SUPPORT_ATTESTED = "support_attested"
    INCONCLUSIVE_PROVIDER_AVAILABILITY = "inconclusive_provider_availability"


@dataclass(frozen=True)
class TwoStageQualification:
    status: TwoStageProfileStatus
    conclusion: TwoStageDiagnosticConclusion
    admitted: bool
    errors: tuple[str, ...]
    routing_success: int
    routing_total: int
    payload_success: int
    payload_total: int
    end_to_end_success: int
    end_to_end_total: int
    critical_success: int
    critical_total: int
    baseline_success: int
    baseline_total: int
    provider_unavailable_count: int
    provider_calls: int
    retry_count: int
    fallback_count: int


def diagnose_two_stage(
    *,
    routing_rate: float,
    payload_rate: float,
    end_to_end_rate: float,
    single_stage_rate: float,
    provider_unavailable_rate: float = 0.0,
) -> TwoStageDiagnosticConclusion:
    if provider_unavailable_rate >= 0.5:
        return TwoStageDiagnosticConclusion.PROVIDER_AVAILABILITY_INCONCLUSIVE
    routing_good = routing_rate == 1.0
    payload_good = payload_rate == 1.0
    end_good = end_to_end_rate == 1.0
    single_good = single_stage_rate == 1.0
    if not routing_good and payload_good:
        return TwoStageDiagnosticConclusion.ROUTING_BOTTLENECK
    if routing_good and not payload_good:
        return TwoStageDiagnosticConclusion.PAYLOAD_BOTTLENECK
    if not routing_good and not payload_good:
        return TwoStageDiagnosticConclusion.PROFILE_UNSUITABLE
    if not end_good:
        return TwoStageDiagnosticConclusion.HANDOFF_BOTTLENECK
    if not single_good:
        return TwoStageDiagnosticConclusion.COUPLING_BOTTLENECK
    return TwoStageDiagnosticConclusion.TWO_STAGE_UNNECESSARY


def qualify_candidate(
    routing: TwoStageMatrixResult,
    payload: TwoStageMatrixResult,
    end_to_end: TwoStageMatrixResult,
    critical: TwoStageMatrixResult,
    *,
    baseline_success: int,
    baseline_total: int,
    support: bool = False,
) -> TwoStageQualification:
    unavailable = sum(
        item.failure_category.endswith("provider_unavailable")
        for result in (routing, payload, end_to_end, critical)
        for item in result.attempts
    )
    totals = sum(len(item.attempts) for item in (routing, payload, end_to_end, critical))
    conclusion = diagnose_two_stage(
        routing_rate=_rate(routing.success_count, len(routing.attempts)),
        payload_rate=_rate(payload.success_count, len(payload.attempts)),
        end_to_end_rate=_rate(end_to_end.success_count, len(end_to_end.attempts)),
        single_stage_rate=_rate(baseline_success, baseline_total),
        provider_unavailable_rate=_rate(unavailable, totals),
    )
    errors = []
    for name, result in (("routing", routing), ("payload", payload), ("end-to-end", end_to_end), ("critical", critical)):
        if result.success_count != len(result.attempts):
            errors.append(f"{name} matrix is incomplete")
        if result.runtime_control_success_count != 7:
            errors.append(f"{name} Runtime control preflight is incomplete")
    retry = sum(item.retry_count for item in (routing, payload, end_to_end, critical))
    fallback = sum(item.fallback_count for item in (routing, payload, end_to_end, critical))
    if retry or fallback:
        errors.append("retry or fallback was recorded")
    admitted = not errors
    status = (
        TwoStageProfileStatus.SUPPORT_ATTESTED if admitted and support
        else TwoStageProfileStatus.CANDIDATE_PASSED if admitted
        else TwoStageProfileStatus.INCONCLUSIVE_PROVIDER_AVAILABILITY
        if unavailable and unavailable == totals
        else TwoStageProfileStatus.CANDIDATE_FAILED
    )
    return TwoStageQualification(
        status, conclusion, admitted, tuple(errors), routing.success_count, len(routing.attempts),
        payload.success_count, len(payload.attempts), end_to_end.success_count,
        len(end_to_end.attempts), critical.success_count, len(critical.attempts),
        baseline_success, baseline_total, unavailable,
        sum(item.provider_calls for item in (routing, payload, end_to_end, critical)),
        retry, fallback,
    )


def _rate(success: int, total: int) -> float:
    return success / total if total else 0.0

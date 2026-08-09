"""Pure diagnosis of routing, payload, coupling and provider availability."""

from __future__ import annotations

from enum import StrEnum


class TwoStageDiagnosticConclusion(StrEnum):
    ROUTING_BOTTLENECK = "routing_bottleneck"
    PAYLOAD_BOTTLENECK = "payload_bottleneck"
    COUPLING_BOTTLENECK = "coupling_bottleneck"
    HANDOFF_BOTTLENECK = "handoff_bottleneck"
    TWO_STAGE_UNNECESSARY = "two_stage_unnecessary"
    PROFILE_UNSUITABLE = "profile_unsuitable"
    PROVIDER_AVAILABILITY_INCONCLUSIVE = "provider_availability_inconclusive"


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

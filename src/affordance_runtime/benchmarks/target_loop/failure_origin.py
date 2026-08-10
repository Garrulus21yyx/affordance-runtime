"""Total semantic failure-origin mapping for observation operations."""

from __future__ import annotations

from affordance_runtime.benchmarks.target_loop.contracts import CaseFailureOrigin
from affordance_runtime.world import ObservationRequestKind

OBSERVATION_FAILURE_ORIGINS = {
    ObservationRequestKind.POLICY_REQUEST: CaseFailureOrigin.DECISION_CONTROL,
    ObservationRequestKind.WAIT_REFRESH: CaseFailureOrigin.DECISION_CONTROL,
    ObservationRequestKind.BINDING_REFRESH: CaseFailureOrigin.ACTION_BINDING,
    ObservationRequestKind.CURRENTNESS_REFRESH: CaseFailureOrigin.CURRENTNESS,
    ObservationRequestKind.CONFIRMATION_REFRESH: CaseFailureOrigin.CURRENTNESS,
    ObservationRequestKind.POST_ACTION_FALLBACK: CaseFailureOrigin.POST_ACTION_OBSERVATION,
}

if set(OBSERVATION_FAILURE_ORIGINS) != set(ObservationRequestKind):
    raise RuntimeError("observation failure-origin mapping is not total")


def observation_failure_origin(kind: ObservationRequestKind | str) -> CaseFailureOrigin:
    """Return one semantic origin for returned and thrown acquisition failures."""

    try:
        typed = kind if isinstance(kind, ObservationRequestKind) else ObservationRequestKind(kind)
    except ValueError:
        return CaseFailureOrigin.UNKNOWN
    return OBSERVATION_FAILURE_ORIGINS[typed]

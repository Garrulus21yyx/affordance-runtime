"""WoT implementation of the unified SurfaceAdapter contract."""

from affordance_runtime.surfaces.wot.adapter import WotSurfaceAdapter
from affordance_runtime.surfaces.wot.contracts import (
    WotAffordanceBinding,
    WotDeploymentScope,
    WotTransportResult,
    WotTransportStatus,
)

__all__ = [
    "WotAffordanceBinding",
    "WotDeploymentScope",
    "WotTransportResult",
    "WotTransportStatus",
    "WotSurfaceAdapter",
]

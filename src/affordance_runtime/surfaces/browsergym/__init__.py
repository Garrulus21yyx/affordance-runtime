"""Reusable BrowserGym surface acquisition, projection, binding, and execution."""

from affordance_runtime.surfaces.browsergym.environment import (
    BrowserGymPort,
    BrowserGymSurfaceAdapter,
)
from affordance_runtime.surfaces.browsergym.inventory import (
    BrowserGymApiInventory,
    browsergym_api_inventory,
)
from affordance_runtime.surfaces.browsergym.task_state import (
    BrowserGymTaskStateSnapshot,
    BrowserGymTaskStateSource,
)
from affordance_runtime.surfaces.browsergym.transition import (
    BrowserGymStabilityStatus,
    BrowserGymStepTransition,
    BrowserGymTransitionTrace,
)

__all__ = [
    "BrowserGymApiInventory",
    "BrowserGymSurfaceAdapter",
    "BrowserGymStabilityStatus",
    "BrowserGymStepTransition",
    "BrowserGymPort",
    "BrowserGymTaskStateSnapshot",
    "BrowserGymTaskStateSource",
    "BrowserGymTransitionTrace",
    "browsergym_api_inventory",
]

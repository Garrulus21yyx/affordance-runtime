"""Fresh-observation identity closure shared by every recurrent loop path."""

from __future__ import annotations

from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.environment import WorldEnvironment


class FreshObservationUnavailable(RuntimeError):
    """The environment did not produce a new acquisition identity."""


async def observe_fresh(
    environment: WorldEnvironment,
    previous_id: str,
    reason: str,
) -> WorldObservation:
    observation = await environment.observe(reason)
    if observation.observation_id == previous_id:
        raise FreshObservationUnavailable(f"{reason}: observation identity was reused")
    return observation

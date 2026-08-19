"""Ephemeral recoverable World delivery lens bound to one current observation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorldDeliveryLens:
    world_observation_id: str
    selected_region_key: str = ""
    cursor: str = ""

    def __post_init__(self) -> None:
        if not self.world_observation_id.strip():
            raise ValueError("delivery lens requires current world identity")
        if (
            self.selected_region_key
            and (
                not self.selected_region_key.startswith("region:")
                or len(self.selected_region_key) > 96
            )
        ):
            raise ValueError("delivery lens selected region key is invalid")
        if len(self.cursor) > 512:
            raise ValueError("delivery lens cursor is invalid")

    def select(self, region_key: str, *, cursor: str = "") -> "WorldDeliveryLens":
        return WorldDeliveryLens(self.world_observation_id, region_key, cursor)

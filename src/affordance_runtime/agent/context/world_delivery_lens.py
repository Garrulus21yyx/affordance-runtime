"""Ephemeral same-World delivery preference for exact recovery results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorldDeliveryLens:
    world_observation_id: str
    kind: str = "base"
    selected_region_key: str = ""
    query: str = ""
    page_cursor: str = ""
    next_cursor: str = ""

    def __post_init__(self) -> None:
        if not self.world_observation_id.strip():
            raise ValueError("delivery lens requires current world identity")
        if self.kind not in {"base", "region", "find", "view_all", "actions"}:
            raise ValueError("delivery lens kind is invalid")
        if self.selected_region_key and (
            not self.selected_region_key.startswith("region:")
            or len(self.selected_region_key) > 96
        ):
            raise ValueError("delivery lens selected region key is invalid")
        if len(self.query) > 120 or len(self.page_cursor) > 512 or len(self.next_cursor) > 512:
            raise ValueError("delivery lens query/cursor state is invalid")
        if self.kind == "region" and not self.selected_region_key:
            raise ValueError("region lens requires a private region key")
        if self.kind == "find" and not self.query.strip():
            raise ValueError("find lens requires a bounded query")

    def select(
        self,
        region_key: str,
        *,
        page_cursor: str = "",
        next_cursor: str = "",
    ) -> "WorldDeliveryLens":
        return WorldDeliveryLens(
            self.world_observation_id,
            "region",
            region_key,
            "",
            page_cursor,
            next_cursor,
        )

    def select_find(
        self,
        query: str,
        *,
        page_cursor: str = "",
        next_cursor: str = "",
    ) -> "WorldDeliveryLens":
        return WorldDeliveryLens(
            self.world_observation_id,
            "find",
            "",
            query,
            page_cursor,
            next_cursor,
        )

    def select_view_all(
        self,
        *,
        page_cursor: str = "",
        next_cursor: str = "",
    ) -> "WorldDeliveryLens":
        return WorldDeliveryLens(
            self.world_observation_id,
            "view_all",
            "",
            "",
            page_cursor,
            next_cursor,
        )

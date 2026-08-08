"""Narrow Visual pointer dispatch."""

from typing import Protocol

from affordance_runtime.surfaces.visual.contracts import VisualRegionBinding


class PointerSession(Protocol):
    def click_xy(self, x: int, y: int) -> None: ...


def point_is_in_viewport(binding: VisualRegionBinding) -> bool:
    x, y = binding.action_point_xy
    return 0 <= x < binding.viewport.width and 0 <= y < binding.viewport.height


def dispatch_point_activate(session: PointerSession, binding: VisualRegionBinding) -> None:
    x, y = binding.action_point_xy
    session.click_xy(round(x), round(y))

"""Narrow Visual integer-point validation and pointer dispatch."""

import math
from typing import Protocol

from affordance_runtime.surfaces.visual.contracts import VisualRegionBinding


class PointerSession(Protocol):
    def click_xy(self, x: int, y: int) -> None: ...


def integer_click_point(binding: VisualRegionBinding) -> tuple[int, int]:
    """Return one rounded point guaranteed inside both bbox and viewport."""

    x, y, width, height = binding.bbox_xywh
    minimum_x = max(0, math.ceil(x))
    minimum_y = max(0, math.ceil(y))
    maximum_x = min(binding.viewport.width - 1, math.ceil(x + width) - 1)
    maximum_y = min(binding.viewport.height - 1, math.ceil(y + height) - 1)
    if minimum_x > maximum_x or minimum_y > maximum_y:
        raise ValueError("visual region has no valid integer click point")
    rounded_x = round(binding.action_point_xy[0])
    rounded_y = round(binding.action_point_xy[1])
    point = (
        min(max(rounded_x, minimum_x), maximum_x),
        min(max(rounded_y, minimum_y), maximum_y),
    )
    if not (x <= point[0] < x + width and y <= point[1] < y + height):
        raise ValueError("rounded integer click point is outside visual region")
    return point


def dispatch_point_activate(session: PointerSession, point: tuple[int, int]) -> None:
    session.click_xy(*point)

"""Canonical semantic action to one pinned BrowserGym high-level action."""

from __future__ import annotations

import json

from affordance_runtime.execution import BoundActionRequest
from affordance_runtime.surfaces.browsergym.binding import (
    BrowserGymDragBinding,
    BrowserGymElementBinding,
    BrowserGymPrivateBinding,
    BrowserGymVisualBinding,
)
from affordance_runtime.surfaces.visual.execution import integer_click_point


def browsergym_action(request: BoundActionRequest, private: BrowserGymPrivateBinding) -> str:
    primitive = request.binding.primitive_action
    if isinstance(private, BrowserGymVisualBinding):
        if primitive != "point_activate":
            raise ValueError("BrowserGym visual binding uses an unsupported primitive")
        x, y = integer_click_point(private.region)
        return f"mouse_click({x}, {y})"
    if isinstance(private, BrowserGymDragBinding):
        if primitive != "drag_and_drop":
            raise ValueError("BrowserGym drag binding uses an unsupported primitive")
        destination = private.destination(request.intent.destination_id)
        source_bid = json.dumps(private.private_element_id, ensure_ascii=False)
        destination_bid = json.dumps(destination.private_element_id, ensure_ascii=False)
        return f"drag_and_drop({source_bid}, {destination_bid})"
    assert isinstance(private, BrowserGymElementBinding)
    bid = json.dumps(private.private_element_id, ensure_ascii=False)
    if primitive == "click":
        return f"click({bid})"
    if primitive == "fill":
        value = request.intent.parameters.get("text")
        if not isinstance(value, str):
            raise ValueError("fill requires one string value")
        return f"fill({bid}, {json.dumps(value, ensure_ascii=False)})"
    if primitive == "select_option":
        label = request.intent.parameters.get("value")
        if not isinstance(label, str):
            raise ValueError("select requires one current option label")
        value = private.option_value(label)
        return f"select_option({bid}, {json.dumps(value, ensure_ascii=False)})"
    raise ValueError("BrowserGym binding uses an unsupported primitive")

"""Canonical semantic action to one pinned BrowserGym high-level action."""

from __future__ import annotations

import json
from collections.abc import Mapping

from affordance_runtime.execution import BoundActionRequest
from affordance_runtime.surfaces.browsergym.binding import (
    BrowserGymDragBinding,
    BrowserGymElementBinding,
    BrowserGymFocusedContextBinding,
    BrowserGymNavigationBinding,
    BrowserGymPrivateBinding,
    BrowserGymViewportBinding,
    BrowserGymVisualBinding,
)
from affordance_runtime.surfaces.visual.execution import integer_click_point


def browsergym_action(request: BoundActionRequest, private: BrowserGymPrivateBinding) -> str:
    primitive = request.binding.primitive_action
    if isinstance(private, BrowserGymNavigationBinding):
        if primitive != private.supported_primitive:
            raise ValueError("BrowserGym navigation primitive changed after binding")
        if primitive == "goto":
            url = request.intent.parameters.get("url")
            if not isinstance(url, str) or not private.allows_url(url):
                raise ValueError("goto URL is outside the current browser environment")
            return f"goto({json.dumps(url, ensure_ascii=False)})"
        if primitive == "tab_focus":
            index = request.intent.parameters.get("index")
            if type(index) is not int or not 0 <= index < len(private.open_pages_urls):
                raise ValueError("tab_focus index is outside the current tab domain")
            return f"tab_focus({index})"
        if request.intent.parameters:
            raise ValueError("parameterless browser navigation received arguments")
        return f"{primitive}()"
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
    if isinstance(private, BrowserGymViewportBinding):
        if primitive != "scroll":
            raise ValueError("BrowserGym viewport binding uses an unsupported primitive")
        delta_x, delta_y = _scroll_delta(request, private)
        return f"scroll({delta_x}, {delta_y})"
    if isinstance(private, BrowserGymFocusedContextBinding):
        if primitive != "keyboard_press":
            raise ValueError("BrowserGym focused-context binding uses an unsupported primitive")
        key = _key(request)
        return f"keyboard_press({json.dumps(key, ensure_ascii=False)})"
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
    if primitive == "press":
        return f"press({bid}, {json.dumps(_key(request), ensure_ascii=False)})"
    raise ValueError("BrowserGym binding uses an unsupported primitive")


def _key(request: BoundActionRequest) -> str:
    value = request.intent.parameters.get("key")
    if not isinstance(value, str):
        raise ValueError("press_key requires one key value")
    schema = request.binding.parameter_schema
    properties = schema.get("properties") if isinstance(schema, Mapping) else None
    key_schema = properties.get("key") if isinstance(properties, Mapping) else None
    allowed = key_schema.get("enum") if isinstance(key_schema, Mapping) else None
    if not isinstance(allowed, tuple | list) or value not in allowed:
        raise ValueError("press_key key is outside the current schema")
    return value


def _scroll_delta(
    request: BoundActionRequest,
    private: BrowserGymViewportBinding,
) -> tuple[float, float]:
    direction = request.intent.parameters.get("direction")
    extent = request.intent.parameters.get("extent")
    if direction not in {"up", "down", "left", "right"} or extent not in {"small", "page"}:
        raise ValueError("scroll requires direction and extent from the current schema")
    vertical_amount = _scroll_amount(private.viewport_height, extent)
    horizontal_amount = _scroll_amount(private.viewport_width, extent)
    if direction == "up":
        return 0.0, -vertical_amount
    if direction == "down":
        return 0.0, vertical_amount
    if direction == "left":
        return -horizontal_amount, 0.0
    return horizontal_amount, 0.0


def _scroll_amount(dimension: int, extent: object) -> float:
    ratio = 0.85 if extent == "page" else 0.25
    return float(max(80, round(dimension * ratio)))

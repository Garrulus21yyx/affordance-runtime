"""Canonical semantic action to one pinned BrowserGym high-level action."""

from __future__ import annotations

import json

from affordance_runtime.benchmarks.external_smoke.browsergym_binding import BrowserGymElementBinding
from affordance_runtime.execution import BoundActionRequest


def browsergym_action(request: BoundActionRequest, private: BrowserGymElementBinding) -> str:
    primitive = request.binding.primitive_action
    bid = json.dumps(private.private_element_id, ensure_ascii=False)
    if primitive == "click":
        return f"click({bid})"
    if primitive == "fill":
        value = request.intent.parameters.get("value")
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

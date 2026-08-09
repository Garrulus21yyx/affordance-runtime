"""Critical non-first and cross-action cases for recurrent qualification."""

from __future__ import annotations

import json
from dataclasses import replace

from .decision_matrix import (
    DecisionMatrixCase,
    DecisionPayloadExpectation,
    build_multi_action_case,
)


def build_nonfirst_direct_case(serialized_context: str) -> DecisionMatrixCase:
    case = build_multi_action_case(serialized_context, action_count=8, correct_index=4)
    context = json.loads(case.serialized_context)
    for index, option in enumerate(context["actions"]["options"]):
        option["relevance_role"] = "direct" if index == 4 else "other"
        option["relevance_score"] = 1.0 if index == 4 else 0.0
    context["task"]["instruction"] = "Choose the only directly relevant candidate that advances the objective."
    return replace(case, case_id="non-first-direct", serialized_context=_json(context))


def build_cross_action_destination_case(serialized_context: str) -> DecisionMatrixCase:
    base = build_multi_action_case(serialized_context, action_count=8, correct_index=7)
    context = json.loads(base.serialized_context)
    options = context["actions"]["options"]
    for index in (0, 7):
        destination = f"destination:action-{index + 1}"
        options[index]["destination_required"] = True
        options[index]["destinations"] = {
            "items": [{"destination_id": destination, "label": f"Route {index + 1}"}],
            "total_count": 1,
            "truncated": False,
        }
    selected = options[7]
    context["task"]["instruction"] = "Use the directly relevant final candidate with its own visible route."
    payload = {
        "type": "select_action", "context_id": context["context_id"],
        "action_id": selected["action_id"], "parameters": {},
        "destination_id": "destination:action-8",
    }
    expectation = DecisionPayloadExpectation(
        "select_action", payload, {}, {}, {}, (),
    )
    return DecisionMatrixCase(
        "cross-action-destination", "select_action", _json(context), payload, expectation,
        correct_action_index=7, correct_destination_index=0,
    )


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

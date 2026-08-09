"""Shared public-context cases for all two-stage comparison modes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from ..critical_cases import build_cross_action_destination_case, build_nonfirst_direct_case
from ..decision_matrix import (
    DecisionMatrixCase,
    DecisionPayloadExpectation,
    build_destination_case,
    build_multi_action_case,
    build_seven_decision_cases,
)


def build_recurrent_cases(serialized_context: str) -> tuple[DecisionMatrixCase, ...]:
    cases = build_seven_decision_cases(serialized_context)
    return tuple(_add_public_missing_input(case) if case.case_id == "ask" else case for case in cases)


def build_critical_cases(serialized_context: str) -> tuple[DecisionMatrixCase, ...]:
    return (
        build_multi_action_case(serialized_context, action_count=8, correct_index=7),
        build_multi_action_case(serialized_context, action_count=16, correct_index=7),
        build_nonfirst_direct_case(serialized_context),
        build_destination_case(serialized_context, destinations=0),
        build_destination_case(serialized_context, destinations=1),
        build_destination_case(serialized_context, destinations=2, correct_index=1),
        build_destination_case(serialized_context, destinations=2, correct_index=1, similar_ids=True),
        build_cross_action_destination_case(serialized_context),
    )


def _add_public_missing_input(case: DecisionMatrixCase) -> DecisionMatrixCase:
    context = json.loads(case.serialized_context)
    context["task"]["public_inputs"]["value"] = None
    context["context_id"] = "context:" + hashlib.sha256(
        json.dumps(context, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload = dict(case.expected_payload)
    payload["context_id"] = context["context_id"]
    exact = dict(case.expectation.exact_fields)
    exact["context_id"] = context["context_id"]
    expectation = DecisionPayloadExpectation(
        case.expectation.expected_variant, exact, case.expectation.allowed_domains,
        case.expectation.collection_item_domains, case.expectation.numeric_bounds,
        case.expectation.required_nonblank_fields,
    )
    return replace(
        case, serialized_context=json.dumps(context, sort_keys=True, separators=(",", ":")),
        expected_payload=payload, expectation=expectation,
    )

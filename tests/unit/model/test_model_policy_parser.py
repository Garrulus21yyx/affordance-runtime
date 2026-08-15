import json

import pytest

from affordance_runtime.agent import (
    Abort,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.context import ModelFailure, ModelFailureKind
from affordance_runtime.model.policy.parser import parse_agent_decision


@pytest.mark.parametrize(
    ("payload", "decision_type"),
    (
        (
            {"type": "select_action", "context_id": "context:1", "action_id": "action:1", "parameters": {}, "destination_id": ""},
            SelectAction,
        ),
        (
            {
                "type": "request_evidence",
                "context_id": "context:1",
                "purpose": "criterion_verification",
                "subject_id": "target:1",
                "evidence_property": "",
                "reason": "refresh",
            },
            RequestObservation,
        ),
        (
            {
                "type": "request_action_page",
                "context_id": "context:1",
                "query": "next",
                "target_id": "",
                "relevance_role": "other",
                "cursor": "",
            },
            RequestActionPage,
        ),
        (
            {"type": "ask_user", "context_id": "context:1", "question": "Which?", "requested_fields": ["choice"]},
            AskUser,
        ),
        (
            {
                "type": "propose_done",
                "context_id": "context:1",
                "claimed_criteria": ["criterion:1"],
                "evidence_refs": ["fact:1"],
                "result_summary": "done",
                "unresolved_items": [],
            },
            ProposeDone,
        ),
        ({"type": "wait", "context_id": "context:1", "reason": "settle", "max_wait_ms": 10}, Wait),
        ({"type": "abort", "context_id": "context:1", "reason": "cannot continue", "category": "policy"}, Abort),
    ),
)
def test_strict_parser_returns_only_typed_decisions(payload, decision_type) -> None:
    parsed = parse_agent_decision(json.dumps(payload), "context:1")

    assert isinstance(parsed, decision_type)


@pytest.mark.parametrize(
    ("payload", "kind"),
    (
        ("not json", ModelFailureKind.INVALID_RESPONSE),
        (json.dumps(["select_action"]), ModelFailureKind.INVALID_RESPONSE),
        (json.dumps({"type": "unknown", "context_id": "context:1"}), ModelFailureKind.SCHEMA_ERROR),
        (
            json.dumps({"type": "select_action", "context_id": "context:1", "action_id": "action:1", "parameters": {}}),
            ModelFailureKind.SCHEMA_ERROR,
        ),
        (
            json.dumps(
                {
                    "type": "select_action",
                    "context_id": "context:1",
                    "action_id": "action:1",
                    "parameters": {},
                    "destination_id": "",
                    "unexpected": True,
                }
            ),
            ModelFailureKind.SCHEMA_ERROR,
        ),
        (
            json.dumps(
                {
                    "type": "select_action",
                    "context_id": "context:stale",
                    "action_id": "action:1",
                    "parameters": {},
                    "destination_id": "",
                }
            ),
            ModelFailureKind.SCHEMA_ERROR,
        ),
    ),
)
def test_strict_parser_rejects_malformed_unknown_missing_and_stale_payloads(payload: str, kind) -> None:
    parsed = parse_agent_decision(payload, "context:1")

    assert isinstance(parsed, ModelFailure)
    assert parsed.kind == kind


def test_parser_rejects_runtime_private_parameter_at_any_depth() -> None:
    payload = json.dumps(
        {
            "type": "select_action",
            "context_id": "context:1",
            "action_id": "action:1",
            "parameters": {"message": {"href": "/private"}},
            "destination_id": "",
        }
    )

    parsed = parse_agent_decision(payload, "context:1")

    assert isinstance(parsed, ModelFailure)
    assert parsed.kind == ModelFailureKind.SCHEMA_ERROR


@pytest.mark.parametrize(("length", "accepted"), ((1_024, True), (1_025, False)))
def test_propose_done_summary_enforces_canonical_budget(length: int, accepted: bool) -> None:
    payload = json.dumps(
        {
            "type": "propose_done",
            "context_id": "context:1",
            "claimed_criteria": [],
            "evidence_refs": [],
            "result_summary": "x" * length,
            "unresolved_items": [],
        }
    )

    parsed = parse_agent_decision(payload, "context:1")

    if accepted:
        assert isinstance(parsed, ProposeDone)
    else:
        assert isinstance(parsed, ModelFailure)
        assert parsed.kind == ModelFailureKind.SCHEMA_ERROR

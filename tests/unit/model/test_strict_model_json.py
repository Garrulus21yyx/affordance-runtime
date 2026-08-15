import json

import pytest

from affordance_runtime.agent.context import ModelFailure, ModelFailureKind
from affordance_runtime.model.policy.parser import parse_agent_decision
from affordance_runtime.model.policy.strict_json import MAX_JSON_DEPTH, strict_json_loads


def _selection(parameters: str = "{}") -> str:
    return (
        '{"type":"select_action","context_id":"context:1","action_id":"action:1",'
        f'"parameters":{parameters},"destination_id":""}}'
    )


@pytest.mark.parametrize(
    "raw",
    (
        '{"type":"abort","type":"wait","context_id":"context:1","reason":"stop","category":"policy"}',
        _selection('{"outer":{"href":"one","href":"two"}}'),
        _selection('{"value":NaN}'),
        _selection('{"value":Infinity}'),
        _selection('{"value":-Infinity}'),
    ),
)
def test_duplicate_keys_and_non_finite_constants_are_invalid_response(raw: str) -> None:
    parsed = parse_agent_decision(raw, "context:1")

    assert isinstance(parsed, ModelFailure)
    assert parsed.kind == ModelFailureKind.INVALID_RESPONSE


def test_strict_loader_accepts_exact_maximum_depth_and_rejects_next_level() -> None:
    accepted: object = True
    for _ in range(MAX_JSON_DEPTH - 2):
        accepted = [accepted]
    strict_json_loads(json.dumps({"value": accepted}))

    rejected = [accepted]
    parsed = parse_agent_decision(_selection(json.dumps({"value": rejected})), "context:1")

    assert isinstance(parsed, ModelFailure)
    assert parsed.kind == ModelFailureKind.INVALID_RESPONSE


def test_excessive_node_count_is_invalid_response() -> None:
    parsed = parse_agent_decision(_selection(json.dumps({"items": [0] * 2_048})), "context:1")

    assert isinstance(parsed, ModelFailure)
    assert parsed.kind == ModelFailureKind.INVALID_RESPONSE


def test_recursion_error_is_classified_as_invalid_response(monkeypatch) -> None:
    def fail(*args, **kwargs):
        del args, kwargs
        raise RecursionError

    monkeypatch.setattr("affordance_runtime.model.policy.strict_json.json.loads", fail)

    parsed = parse_agent_decision(_selection(), "context:1")

    assert isinstance(parsed, ModelFailure)
    assert parsed.kind == ModelFailureKind.INVALID_RESPONSE


def test_malformed_unicode_is_classified_as_invalid_response() -> None:
    parsed = parse_agent_decision('{"type":"abort","reason":"\ud800"}', "context:1")

    assert isinstance(parsed, ModelFailure)
    assert parsed.kind == ModelFailureKind.INVALID_RESPONSE

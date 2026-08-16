import json

import pytest

from affordance_runtime.model.policy.strict_json import MAX_JSON_DEPTH, strict_json_loads


@pytest.mark.parametrize(
    "raw",
    (
        '{"type":"abort","type":"wait"}',
        '{"outer":{"href":"one","href":"two"}}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":-Infinity}',
    ),
)
def test_duplicate_keys_and_non_finite_constants_are_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        strict_json_loads(raw)


def test_strict_loader_accepts_exact_maximum_depth_and_rejects_next_level() -> None:
    accepted: object = True
    for _ in range(MAX_JSON_DEPTH - 2):
        accepted = [accepted]
    strict_json_loads(json.dumps({"value": accepted}))

    rejected = [accepted]
    with pytest.raises(ValueError):
        strict_json_loads(json.dumps({"value": rejected}))


def test_excessive_node_count_is_rejected() -> None:
    with pytest.raises(ValueError):
        strict_json_loads(json.dumps({"items": [0] * 2_048}))


def test_recursion_error_is_rejected(monkeypatch) -> None:
    def fail(*args, **kwargs):
        del args, kwargs
        raise RecursionError

    monkeypatch.setattr("affordance_runtime.model.policy.strict_json.json.loads", fail)

    with pytest.raises(ValueError):
        strict_json_loads("{}")


def test_malformed_unicode_is_rejected() -> None:
    with pytest.raises(ValueError):
        strict_json_loads('{"reason":"\ud800"}')

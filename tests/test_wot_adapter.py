import pytest

from affordance_runtime.adapters.wot import WotAdapter
from affordance_runtime.adapters.wot_security import build_auth, parse_rate_limit


def _runtime_td() -> dict[str, object]:
    return {
        "id": "thermostat",
        "title": "Thermostat",
        "base": "http://localhost:8080",
        "properties": {
            "temperature": {
                "forms": [{"href": "/temperature", "op": ["readproperty", "writeproperty"], "htv:methodName": "PUT"}]
            }
        },
        "actions": {"reset": {"forms": [{"href": "/reset", "op": "invokeaction"}]}},
    }


def test_wot_adapter_parses_runtime_td_affordances() -> None:
    model = WotAdapter().parse(_runtime_td(), environment_revision="rev-1")

    assert model.thing_id == "thermostat"
    assert len(model.state_sources) == 1
    assert {item.action for item in model.affordances} == {"write_property", "invoke"}


def test_wot_affordance_model_payloads_are_immutable_after_parse() -> None:
    model = WotAdapter().parse(_runtime_td(), environment_revision="rev-1")

    with pytest.raises(AttributeError):
        model.affordances.append(model.affordances[0])  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        model.state_sources.append({"thing_id": "polluted"})  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        model.state_sources[0]["href"] = "http://polluted"


def test_wot_adapter_does_not_infer_write_from_read_only_form() -> None:
    td = {
        "id": "sensor",
        "properties": {
            "temperature": {
                "forms": [{"href": "http://fixture/temperature", "op": "readproperty"}],
            }
        },
    }

    model = WotAdapter().parse(td, environment_revision="rev-1")

    assert len(model.state_sources) == 1
    assert model.affordances == []


def test_wot_adapter_extracts_security_rate_schema_and_events_without_credentials() -> None:
    td = {
        "id": "thermostat",
        "base": "http://fixture/thermostat",
        "securityDefinitions": {
            "api": {"scheme": "apikey", "in": "header", "name": "X-API-Key"},
        },
        "security": "api",
        "rateLimit": "10/min",
        "actions": {
            "setTarget": {
                "input": {"type": "number", "minimum": 16, "maximum": 30},
                "output": {"type": "boolean"},
                "forms": [{"href": "/set", "op": "invokeaction"}],
            }
        },
        "events": {
            "overheated": {
                "data": {"type": "number"},
                "forms": [{"href": "/events/overheated", "op": "subscribeevent"}],
            }
        },
    }

    model = WotAdapter().parse(td, environment_revision="rev-1")
    action = next(item for item in model.affordances if item.label == "setTarget")

    assert model.security is not None and model.security.field_name == "X-API-Key"
    assert model.rate_limit is not None and model.rate_limit.min_interval_ms == 6_000
    assert model.events == ("overheated",)
    assert action.locator["security_scheme_ref"] == "api"
    assert action.state["input_schema"]["maximum"] == 30
    assert action.state["output_schema"]["type"] == "boolean"
    assert action.state["rate_limit"]["min_interval_ms"] == 6_000
    assert action.locator["min_interval_ms"] == 6_000
    assert "credential" not in repr(model)


def test_wot_adapter_supports_implicit_property_operations_but_respects_write_only() -> None:
    td = {
        "id": "lamp",
        "properties": {
            "power": {"type": "boolean", "forms": [{"href": "http://fixture/power"}]},
            "command": {
                "type": "string",
                "writeOnly": True,
                "forms": [{"href": "http://fixture/command"}],
            },
        },
    }

    model = WotAdapter().parse(td, environment_revision="rev-1")

    assert {item["property"] for item in model.state_sources} == {"power"}
    assert {item.label for item in model.affordances} == {"power", "command"}


def test_wot_security_helpers_parse_variants_and_build_ephemeral_auth() -> None:
    assert parse_rate_limit("5/sec") == parse_rate_limit({"max": 5, "window": "second"})
    assert parse_rate_limit({"max_requests": 2, "window_seconds": 30}).min_interval_ms == 15_000
    assert parse_rate_limit("garbage") is None
    model = WotAdapter().parse(
        {
            "id": "lamp",
            "securityDefinitions": {"bearer": {"scheme": "bearer"}},
            "security": "bearer",
        },
        environment_revision="rev-1",
    )
    headers, query = build_auth(model.security, "runtime-only-secret")
    assert headers == {"Authorization": "Bearer runtime-only-secret"}
    assert query == {}

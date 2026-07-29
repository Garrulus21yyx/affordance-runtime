import pytest

from affordance_runtime.adapters.wot import WotAdapter


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

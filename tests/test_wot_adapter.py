from affordance_runtime.adapters.wot import WotAdapter


def test_wot_adapter_parses_runtime_td_affordances() -> None:
    td = {
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

    model = WotAdapter().parse(td, environment_revision="rev-1")

    assert model.thing_id == "thermostat"
    assert len(model.state_sources) == 1
    assert {item.action for item in model.affordances} == {"write_property", "invoke"}


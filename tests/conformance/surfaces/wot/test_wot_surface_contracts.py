from dataclasses import replace

import pytest

from affordance_runtime.actions.classification import classify_wot_action
from affordance_runtime.surfaces.wot.contracts import (
    WotAffordanceBinding,
    WotDeploymentScope,
    WotTransportResult,
    WotTransportStatus,
    thing_description_digest,
)
from affordance_runtime.surfaces.wot.thing_description import WotAdapter
from affordance_runtime.task import RiskProfile, TaskGoal


def _task() -> TaskGoal:
    return TaskGoal(
        "shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.LOW,
    )


def _td(security: str = "public") -> dict[str, object]:
    return {
        "id": "shared-state",
        "title": "Shared State",
        "base": "http://127.0.0.1:9999",
        "securityDefinitions": {"public": {"scheme": "nosec"}},
        "security": security,
        "actions": {
            "enable": {
                "forms": [
                    {
                        "href": "/actions/enable",
                        "op": "invokeaction",
                        "htv:methodName": "POST",
                        "contentType": "application/json",
                    }
                ]
            }
        },
        "events": {"changed": {"forms": [{"href": "/events", "op": "subscribeevent"}]}},
    }


def test_wot_route_retains_typed_private_identity_for_explicit_nosec() -> None:
    td = _td()
    digest = thing_description_digest(td)
    model = WotAdapter().parse(td, environment_revision=digest, snapshot_id="wot:1", page_revision=digest)
    route = WotAffordanceBinding.from_affordance("wot:1", digest, model, model.affordances[0])

    assert route.thing_id == "shared-state"
    assert route.td_digest == digest
    assert route.affordance_kind == "action"
    assert route.affordance_name == "enable"
    assert route.security_scheme_ref == "public"
    assert route.href.endswith("/actions/enable")
    assert route.method == "POST"
    assert route.primitive_action == "invoke"
    assert "credential" not in repr(route)


def test_wot_route_rejects_missing_thing_or_td_identity() -> None:
    td = _td()
    model = WotAdapter().parse(td, environment_revision="sha256:td")
    route = WotAffordanceBinding.from_affordance("wot:1", "sha256:td", model, model.affordances[0])

    with pytest.raises(ValueError, match="identity"):
        replace(route, thing_id="")
    with pytest.raises(ValueError, match="identity"):
        replace(route, td_digest="")
    with pytest.raises(ValueError, match="identity"):
        replace(route, source_observation_id="")


@pytest.mark.parametrize(
    ("scope", "category", "risk"),
    [
        (WotDeploymentScope.LOCAL_SIMULATION, "local_reversible", "low"),
        (WotDeploymentScope.REMOTE_SERVICE, "external", "high"),
        (WotDeploymentScope.PHYSICAL_DEVICE, "external", "high"),
    ],
)
def test_wot_deployment_scope_owns_invoke_risk(scope, category: str, risk: str) -> None:
    classification = classify_wot_action(_task(), "action", "activate", scope)
    assert classification.category.value == category
    assert classification.risk.value == risk


def test_td_authored_low_risk_cannot_lower_physical_device_scope() -> None:
    classification = classify_wot_action(
        _task(),
        "action",
        "activate",
        WotDeploymentScope.PHYSICAL_DEVICE,
        authored_risk="low",
    )
    assert classification.risk.value == "high"


def test_wot_read_property_is_always_observation_low() -> None:
    classification = classify_wot_action(
        _task(),
        "property",
        "read",
        WotDeploymentScope.PHYSICAL_DEVICE,
    )
    assert classification.category.value == "observation"
    assert classification.risk.value == "low"


def test_wot_transport_result_has_explicit_dispatch_without_sensitive_evidence() -> None:
    result = WotTransportResult(WotTransportStatus.SENT_UNKNOWN, False, "timeout")
    assert result.status.value == "sent_unknown"
    assert "credential" not in repr(result)
    with pytest.raises(ValueError, match="sensitive"):
        WotTransportResult(WotTransportStatus.SENT, True, evidence={"Authorization": "secret"})

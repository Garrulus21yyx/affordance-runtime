import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from affordance_runtime.execution.contracts import ActionIntent, BoundActionRequest
from affordance_runtime.surfaces.wot import WotDeploymentScope
from affordance_runtime.surfaces.wot.adapter import WotSurfaceAdapter
from affordance_runtime.surfaces.wot.contracts import WotTransportResult, WotTransportStatus
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import ActionBinder, ActionSpaceBuilder, build_agent_world_view
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


def shared_td(*, security: str = "public", min_interval_ms: int = 0) -> dict:
    form = {
        "href": "http://fixture/actions/enable",
        "op": "invokeaction",
        "htv:methodName": "POST",
        "contentType": "application/json",
    }
    if min_interval_ms:
        form["rateLimit"] = {"max_requests": 1, "window_seconds": min_interval_ms / 1000}
    return {
        "id": "shared-state",
        "title": "Shared State",
        "base": "http://fixture",
        "securityDefinitions": {"public": {"scheme": "nosec"}},
        "security": security,
        "properties": {
            "expanded": {
                "type": "boolean",
                "readOnly": True,
                "forms": [
                    {
                        "href": "/properties/expanded",
                        "op": "readproperty",
                        "htv:methodName": "GET",
                    }
                ],
            }
        },
        "actions": {"enable": {"forms": [form]}},
        "events": {"changed": {"forms": [{"href": "/events", "op": "subscribeevent"}]}},
    }


class FakeWotTransport:
    def __init__(self, td=None) -> None:
        self.td = td or shared_td()
        self.expanded = False
        self.fetches = 0
        self.reads = 0
        self.probes = 0
        self.action_port_calls = 0
        self.action_endpoint_calls = 0
        self.probe_failure = False
        self.action_result = WotTransportResult(WotTransportStatus.SENT, True)
        self.apply_effect = True
        self.raise_on_execute = False
        self.property_value = None

    def reset(self) -> None:
        self.expanded = False

    def fetch_thing_description(self):
        self.fetches += 1
        return deepcopy(self.td)

    def probe_thing_revision(self):
        self.probes += 1
        if self.probe_failure:
            raise RuntimeError("TD probe unavailable")
        return deepcopy(self.td)

    def read_property(self, route, scheme):
        del route, scheme
        self.reads += 1
        value = self.expanded if self.property_value is None else self.property_value
        return WotTransportResult(WotTransportStatus.SENT, True, value=value)

    def execute_affordance(self, route, scheme, parameters):
        del route, scheme, parameters
        self.action_port_calls += 1
        if self.raise_on_execute:
            raise RuntimeError("unclassified transport failure")
        if self.action_result.status != WotTransportStatus.NOT_SENT:
            self.action_endpoint_calls += 1
        if self.apply_effect and self.action_result.status != WotTransportStatus.NOT_SENT:
            self.expanded = True
        return self.action_result


def _task(*, risk: RiskProfile = RiskProfile.LOW) -> TaskGoal:
    return TaskGoal(
        "shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=risk,
    )


async def _bound(transport, scope=WotDeploymentScope.LOCAL_SIMULATION, clock=lambda: 100.0):
    adapter = WotSurfaceAdapter(transport, deployment_scope=scope, clock=clock)
    world = UnifiedWorldEnvironment((adapter,))
    task = _task()
    await world.reset(task)
    observed = await world.observe("initial")
    option = ActionSpaceBuilder().build(task, observed).options[0]
    request = ActionBinder().bind(ActionSpaceBuilder().admit(option, {}), observed)
    return adapter, world, observed, request


def test_wot_adapter_observes_state_keeps_route_private_and_executes_once() -> None:
    async def scenario() -> None:
        transport = FakeWotTransport()
        _, world, observed, request = await _bound(transport)

        view = build_agent_world_view(observed)
        assert "href" not in repr(view)
        assert "method" not in repr(view)
        assert "security" not in repr(view)
        assert observed.sources[0].coverage.value == "complete"
        assert any(target.state.get("expanded") is False for target in observed.targets)
        assert request.binding.payload["href"].endswith("/actions/enable")

        result = await world.execute(request)
        assert result.transport_success
        assert result.adapter_evidence["currentness_probe_count"] == 1
        assert transport.probes == 1
        assert transport.action_endpoint_calls == 1

    asyncio.run(scenario())


def test_wot_unresolved_security_and_events_have_no_executable_binding() -> None:
    async def scenario() -> None:
        transport = FakeWotTransport(shared_td(security="missing"))
        adapter = WotSurfaceAdapter(transport, deployment_scope=WotDeploymentScope.LOCAL_SIMULATION)
        await adapter.reset(_task())
        observed = await adapter.observe("locked")

        assert observed.bindings == ()
        assert transport.reads == 0
        assert observed.coverage.value == "failed"
        assert observed.artifacts["unsupported_events"] == ("changed",)

    asyncio.run(scenario())


def test_wot_physical_and_remote_routes_remain_high_risk() -> None:
    async def scenario(scope) -> None:
        transport = FakeWotTransport()
        adapter = WotSurfaceAdapter(transport, deployment_scope=scope)
        world = UnifiedWorldEnvironment((adapter,))
        await world.reset(_task())
        observed = await world.observe("initial")
        option = ActionSpaceBuilder().build(_task(), observed).options[0]
        assert option.risk.value == "high"

    asyncio.run(scenario(WotDeploymentScope.PHYSICAL_DEVICE))
    asyncio.run(scenario(WotDeploymentScope.REMOTE_SERVICE))


def test_wot_changed_td_is_stale_with_zero_action_calls() -> None:
    async def scenario() -> None:
        transport = FakeWotTransport()
        _, world, _, request = await _bound(transport)
        transport.td["actions"]["enable"]["forms"][0]["htv:methodName"] = "PUT"

        result = await world.execute(request)
        assert result.error.value == "stale_binding"
        assert transport.action_endpoint_calls == 0

    asyncio.run(scenario())


def test_wot_currentness_probe_failure_is_not_sent() -> None:
    async def scenario() -> None:
        transport = FakeWotTransport()
        _, world, _, request = await _bound(transport)
        transport.probe_failure = True

        result = await world.execute(request)
        assert result.error.value == "currentness_unavailable"
        assert transport.action_endpoint_calls == 0

    asyncio.run(scenario())


def test_wot_reset_invalidates_old_request_without_probe_or_action() -> None:
    async def scenario() -> None:
        transport = FakeWotTransport()
        adapter, world, _, request = await _bound(transport)
        await adapter.reset(_task())

        result = await world.execute(request)
        assert result.error.value == "stale_binding"
        assert transport.probes == 0
        assert transport.action_endpoint_calls == 0

    asyncio.run(scenario())


def test_wot_rate_limit_rejects_second_send_without_sleep_or_action() -> None:
    async def scenario() -> None:
        now = [100.0]
        transport = FakeWotTransport(shared_td(min_interval_ms=1000))
        _, world, _, request = await _bound(transport, clock=lambda: now[0])
        first = await world.execute(request)
        assert first.transport_success
        second = await world.execute(request)
        assert second.error.value == "rate_limited"
        assert transport.action_endpoint_calls == 1

    asyncio.run(scenario())


def test_wot_transport_pre_send_and_unknown_map_without_retry() -> None:
    async def scenario(status, expected_error, endpoint_calls) -> None:
        transport = FakeWotTransport()
        transport.action_result = WotTransportResult(status, False, "fixture_failure")
        _, world, _, request = await _bound(transport)

        result = await world.execute(request)
        assert result.dispatch_status.value == status.value
        assert result.error.value == expected_error
        assert transport.action_endpoint_calls == endpoint_calls
        assert transport.action_port_calls == 1
        assert "credential" not in repr(result)

    asyncio.run(scenario(WotTransportStatus.NOT_SENT, "execution_failed", 0))
    asyncio.run(scenario(WotTransportStatus.SENT_UNKNOWN, "execution_failed", 1))


def test_wot_effectful_transport_exception_is_sent_unknown_without_retry() -> None:
    async def scenario() -> None:
        transport = FakeWotTransport()
        transport.raise_on_execute = True
        _, world, _, request = await _bound(transport)

        result = await world.execute(request)

        assert result.dispatch_status.value == "sent_unknown"
        assert transport.action_port_calls == 1
        assert transport.action_endpoint_calls == 0

    asyncio.run(scenario())


def test_wot_malformed_parameters_are_rejected_before_transport() -> None:
    async def scenario() -> None:
        td = shared_td()
        td["properties"]["expanded"]["readOnly"] = False
        td["properties"]["expanded"]["forms"][0]["op"] = ["readproperty", "writeproperty"]
        transport = FakeWotTransport(td)
        adapter = WotSurfaceAdapter(transport, deployment_scope=WotDeploymentScope.LOCAL_SIMULATION)
        world = UnifiedWorldEnvironment((adapter,))
        await world.reset(_task())
        observed = await world.observe("initial")
        option = next(item for item in ActionSpaceBuilder().build(_task(), observed).options if item.semantic_action == "set_value")
        valid = ActionSpaceBuilder().admit(option, {"value": True})
        request = ActionBinder().bind(valid, observed)
        invalid_selection = replace(valid, parameters={"value": "not-a-boolean"})
        invalid = BoundActionRequest(
            request.request_id,
            request.world_observation_id,
            ActionIntent("set_value", request.intent.target_id, {"value": "not-a-boolean"}),
            invalid_selection,
            request.binding,
        )

        result = await world.execute(invalid)
        assert result.error.value == "invalid_parameters"
        assert transport.action_endpoint_calls == 0

    asyncio.run(scenario())


def test_wot_partial_property_read_reports_truncated_coverage() -> None:
    class PartialTransport(FakeWotTransport):
        def read_property(self, route, scheme):
            if route.affordance_name == "unavailable":
                return WotTransportResult(WotTransportStatus.NOT_SENT, False, "read_failed")
            return super().read_property(route, scheme)

    async def scenario() -> None:
        td = shared_td()
        td["properties"]["unavailable"] = deepcopy(td["properties"]["expanded"])
        td["properties"]["unavailable"]["forms"][0]["href"] = "/properties/unavailable"
        transport = PartialTransport(td)
        adapter = WotSurfaceAdapter(transport, deployment_scope=WotDeploymentScope.LOCAL_SIMULATION)
        await adapter.reset(_task())
        observed = await adapter.observe("partial")
        assert observed.coverage.value == "truncated"
        assert len(observed.targets) >= 2  # one property, one action, plus the event description
        assert observed.artifacts["read_errors"] == ("unavailable:read_failed",)

    asyncio.run(scenario())


def test_wot_wrong_property_type_is_not_published_as_world_fact() -> None:
    async def scenario() -> None:
        transport = FakeWotTransport()
        transport.property_value = {"credential": "must-not-leak"}
        adapter = WotSurfaceAdapter(transport, deployment_scope=WotDeploymentScope.LOCAL_SIMULATION)
        await adapter.reset(_task())

        observed = await adapter.observe("invalid property")

        assert observed.coverage.value == "failed"
        assert not any(fact.key == "expanded" for fact in observed.facts)
        assert observed.artifacts["read_errors"] == ("expanded:schema_mismatch",)
        assert "must-not-leak" not in repr(observed)

    asyncio.run(scenario())


def test_wot_property_action_event_names_have_source_local_identity() -> None:
    async def scenario() -> None:
        td = shared_td()
        td["properties"]["enable"] = td["properties"].pop("expanded")
        td["events"] = {"enable": td["events"].pop("changed")}
        transport = FakeWotTransport(td)
        adapter = WotSurfaceAdapter(transport, deployment_scope=WotDeploymentScope.LOCAL_SIMULATION)
        await adapter.reset(_task())

        observed = await adapter.observe("same names")
        target_ids = {target.target_id for target in observed.targets}

        assert "wot:shared-state:property:enable" in target_ids
        assert "wot:shared-state:action:enable" in target_ids
        assert "wot:shared-state:event:enable" in target_ids

    asyncio.run(scenario())


def test_wot_missing_explicit_thing_identity_fails_closed() -> None:
    async def scenario() -> None:
        td = shared_td()
        td.pop("id")
        adapter = WotSurfaceAdapter(
            FakeWotTransport(td),
            deployment_scope=WotDeploymentScope.LOCAL_SIMULATION,
        )
        await adapter.reset(_task())
        with pytest.raises(ValueError, match="explicit thing identity"):
            await adapter.observe("missing identity")

    asyncio.run(scenario())

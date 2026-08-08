import json
from dataclasses import replace

from affordance_runtime.adapters.wot_security import SecurityScheme
from affordance_runtime.surfaces.wot.contracts import WotAffordanceBinding, WotTransportStatus
from affordance_runtime.surfaces.wot.transport import HttpWotTransport, MappingCredentialResolver


class Response:
    def __init__(self, payload, status: int = 200) -> None:
        self.payload = json.dumps(payload).encode()
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self.payload


def _route(security_ref: str = "api") -> WotAffordanceBinding:
    return WotAffordanceBinding(
        "shared-state",
        "sha256:td",
        "wot:1",
        "sha256:td",
        "action",
        "enable",
        "wot_shared-state_enable",
        "sha256:affordance",
        "http://fixture/actions/enable",
        "POST",
        "application/json",
        {},
        security_ref,
        0,
        "wot",
        "invoke",
        "activate",
        0,
    )


def test_http_wot_transport_late_binds_credential_only_at_request(monkeypatch) -> None:
    requests = []

    def urlopen(request, timeout):
        del timeout
        requests.append(request)
        return Response({"ok": True})

    monkeypatch.setattr("affordance_runtime.surfaces.wot.transport.urlopen", urlopen)
    resolver = MappingCredentialResolver({("shared-state", "api"): "runtime-only-secret"})
    transport = HttpWotTransport("http://fixture/td", resolver)
    scheme = SecurityScheme("api", "apikey", "header", "X-API-Key")

    result = transport.execute_affordance(_route(), scheme, {})

    assert result.status == WotTransportStatus.SENT
    assert result.transport_success
    assert requests[0].headers["X-api-key"] == "runtime-only-secret"
    assert "runtime-only-secret" not in repr(transport)
    assert "runtime-only-secret" not in repr(result)
    assert "X-API-Key" not in repr(result.evidence)


def test_http_wot_transport_missing_credential_is_not_sent(monkeypatch) -> None:
    calls = 0

    def urlopen(request, timeout):
        del request, timeout
        nonlocal calls
        calls += 1
        return Response({})

    monkeypatch.setattr("affordance_runtime.surfaces.wot.transport.urlopen", urlopen)
    transport = HttpWotTransport("http://fixture/td", MappingCredentialResolver({}))
    scheme = SecurityScheme("api", "apikey", "header", "X-API-Key")

    result = transport.execute_affordance(_route(), scheme, {})

    assert result.status == WotTransportStatus.NOT_SENT
    assert result.error_type == "credential_unavailable"
    assert calls == 0


def test_http_wot_transport_fetch_and_probe_td_without_old_action_contract(monkeypatch) -> None:
    requests = []

    def urlopen(request, timeout):
        del timeout
        requests.append(request)
        return Response({"id": "shared-state"})

    monkeypatch.setattr("affordance_runtime.surfaces.wot.transport.urlopen", urlopen)
    transport = HttpWotTransport("http://fixture/td")

    assert transport.fetch_thing_description() == {"id": "shared-state"}
    assert transport.probe_thing_revision() == {"id": "shared-state"}
    assert [request.full_url for request in requests] == ["http://fixture/td", "http://fixture/td"]


def test_http_wot_transport_rejects_unsupported_route_without_send(monkeypatch) -> None:
    calls = 0

    def urlopen(request, timeout):
        del request, timeout
        nonlocal calls
        calls += 1
        return Response({})

    monkeypatch.setattr("affordance_runtime.surfaces.wot.transport.urlopen", urlopen)
    transport = HttpWotTransport("http://fixture/td")
    scheme = SecurityScheme("api", "nosec", "", "")

    for route in (
        replace(_route("api"), href="mqtt://fixture/actions/enable"),
        replace(_route("api"), method="TRACE"),
        replace(_route("api"), content_type="text/plain"),
    ):
        assert not transport.supports(route)
        result = transport.execute_affordance(route, scheme, {})
        assert result.status == WotTransportStatus.NOT_SENT
        assert result.error_type == "unsupported_route"

    assert calls == 0


def test_http_wot_transport_unencodable_payload_is_not_sent(monkeypatch) -> None:
    calls = 0

    def urlopen(request, timeout):
        del request, timeout
        nonlocal calls
        calls += 1
        return Response({})

    monkeypatch.setattr("affordance_runtime.surfaces.wot.transport.urlopen", urlopen)
    transport = HttpWotTransport("http://fixture/td")
    scheme = SecurityScheme("api", "nosec", "", "")

    result = transport.execute_affordance(_route("api"), scheme, {"bad": object()})

    assert result.status == WotTransportStatus.NOT_SENT
    assert result.error_type == "payload_not_json"
    assert calls == 0

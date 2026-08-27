from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from interaction_shell.api import create_app
from interaction_shell.contracts import Capability, ControlOwner, RunStatus, ViewerState
from interaction_shell.demo_port import ContractDemoPort
from interaction_shell.manager import RunSessionManager
from interaction_shell.port import RuntimeSessionUnavailable
from interaction_shell.session_registry import SQLiteSessionRecoveryRegistry
from interaction_shell.viewer import ViewerHTTPResponse
from starlette.websockets import WebSocketDisconnect


@pytest.mark.asyncio
async def test_http_admission_is_not_task_success_and_auth_is_isolated():
    app = create_app(RunSessionManager(ContractDemoPort()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/sessions", json={})).json()
        snapshot = created["snapshot"]
        assert snapshot["event_epoch"]
        mismatched_epoch = await client.get(
            f"/sessions/{snapshot['session_id']}/events",
            headers={"X-Session-Key": created["session_key"]},
            params={"event_epoch": "wrong-event-epoch", "cursor": 0},
        )
        assert mismatched_epoch.status_code == 409
        response = await client.post(
            f"/sessions/{snapshot['session_id']}/tasks",
            headers={"X-Session-Key": created["session_key"]},
            json={
                "kind": "start_task",
                "command_id": "start",
                "expected_task_revision": 0,
                "expected_run_status": "idle",
                "task": "Choose one",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == "accepted"
        assert body["snapshot"]["run_status"] == "waiting_user"
        assert body["snapshot"]["completion"] is None
        forbidden = await client.get(f"/sessions/{snapshot['session_id']}")
        assert forbidden.status_code == 401


@pytest.mark.asyncio
async def test_session_open_unavailable_is_typed_service_response():
    class UnavailableOpenPort(ContractDemoPort):
        async def open(self, session_id, expires_at):
            del session_id, expires_at
            raise RuntimeSessionUnavailable("environment_factory_failed")

    app = create_app(RunSessionManager(UnavailableOpenPort()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/sessions", json={})
    assert response.status_code == 503
    assert response.json()["detail"] == "environment_factory_failed"


@pytest.mark.asyncio
async def test_http_revision_uses_dedicated_typed_endpoint():
    app = create_app(RunSessionManager(ContractDemoPort()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/sessions", json={})).json()
        snapshot = created["snapshot"]
        response = await client.post(
            f"/sessions/{snapshot['session_id']}/commands/revise",
            headers={"X-Session-Key": created["session_key"]},
            json={
                "kind": "revise_task",
                "command_id": "revise:http",
                "expected_task_revision": 0,
                "expected_run_status": "idle",
                "expected_checkpoint_id": None,
                "text": "Inspect the account and its owner",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "unsupported"
    assert body["capability"] == "revise_task"


@pytest.mark.asyncio
async def test_http_takeover_commands_use_dedicated_typed_endpoints():
    app = create_app(RunSessionManager(ContractDemoPort()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/sessions", json={})).json()
        session_id = created["snapshot"]["session_id"]
        headers = {"X-Session-Key": created["session_key"]}
        takeover = await client.post(
            f"/sessions/{session_id}/commands/takeover",
            headers=headers,
            json={
                "kind": "take_over",
                "command_id": "takeover:http",
                "expected_task_revision": 0,
                "expected_run_status": "idle",
                "checkpoint_id": "runtime-checkpoint:" + "a" * 64,
            },
        )
        returned = await client.post(
            f"/sessions/{session_id}/commands/return-control",
            headers=headers,
            json={
                "kind": "return_control",
                "command_id": "return:http",
                "expected_task_revision": 0,
                "expected_run_status": "idle",
                "control_lease_id": "user-control-lease:" + "u" * 32,
            },
        )

    assert takeover.status_code == 200
    assert takeover.json()["kind"] == "unsupported"
    assert takeover.json()["capability"] == "take_over"
    assert returned.status_code == 200
    assert returned.json()["kind"] == "unsupported"
    assert returned.json()["capability"] == "return_control"


@pytest.mark.asyncio
async def test_viewer_route_uses_http_only_session_auth_and_bounded_read_only_proxy():
    class FakeViewerGateway:
        def __init__(self) -> None:
            self.documents: list[tuple[str, bool]] = []
            self.ice: list[str] = []
            self.offers: list[tuple[str, bytes, str, str]] = []

        async def document(self, session_id: str, *, interactive: bool = False):
            self.documents.append((session_id, interactive))
            return ViewerHTTPResponse(200, b"<html>viewer</html>", "text/html")

        def input_websocket_url(self, session_id: str) -> str:
            return f"ws://provider.invalid/{session_id}"

        async def ice_servers(self, session_id: str):
            self.ice.append(session_id)
            return ViewerHTTPResponse(200, b'{"iceServers":[]}', "application/json")

        async def whep(self, session_id: str, body: bytes, content_type: str, region: str):
            self.offers.append((session_id, body, content_type, region))
            return ViewerHTTPResponse(201, b"answer", "application/sdp")

    gateway = FakeViewerGateway()
    app = create_app(RunSessionManager(ContractDemoPort()), viewer_gateway=gateway)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created_response = await client.post("/sessions", json={})
        created = created_response.json()
        session_id = created["snapshot"]["session_id"]
        cookie = created_response.headers["set-cookie"]
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
        assert f"Path=/viewer/{session_id}" in cookie

        viewer = await client.get(f"/viewer/{session_id}")
        assert viewer.status_code == 200
        assert viewer.text == "<html>viewer</html>"
        assert viewer.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'self'" in viewer.headers["content-security-policy"]

        wrong_nested_session = await client.get(
            f"/viewer/{session_id}/steel/v1/rtc/ice-servers/not-this-session"
        )
        assert wrong_nested_session.status_code == 404

        ice = await client.get(
            f"/viewer/{session_id}/steel/v1/rtc/ice-servers/{session_id}"
        )
        offer = await client.post(
            f"/viewer/{session_id}/steel/v1/rtc/whep/{session_id}?region=iad",
            content=b"offer",
            headers={"Content-Type": "application/sdp"},
        )
        assert ice.status_code == 200
        assert offer.status_code == 201

    async with AsyncClient(transport=transport, base_url="http://test") as outsider:
        unauthorized = await outsider.get(f"/viewer/{session_id}")
    assert unauthorized.status_code == 401
    assert gateway.documents == [(session_id, False)]
    assert gateway.ice == [session_id]
    assert gateway.offers == [(session_id, b"offer", "application/sdp", "iad")]


def test_viewer_input_websocket_rejects_old_socket_after_new_takeover_lease(monkeypatch):
    class FakeViewerGateway:
        def __init__(self) -> None:
            self.document_modes: list[bool] = []

        async def document(self, session_id: str, *, interactive: bool = False):
            del session_id
            self.document_modes.append(interactive)
            return ViewerHTTPResponse(200, b"<html>viewer</html>", "text/html")

        def input_websocket_url(self, session_id: str) -> str:
            return f"wss://connect.steel.dev/v1/sessions/{session_id}/input?token=private"

        async def ice_servers(self, session_id: str):
            del session_id
            return ViewerHTTPResponse(200, b'{}', "application/json")

        async def whep(self, session_id: str, body: bytes, content_type: str, region: str):
            del session_id, body, content_type, region
            return ViewerHTTPResponse(201, b"answer", "application/sdp")

    class FakeUpstream:
        def __init__(self) -> None:
            self.sent: list[str | bytes] = []
            self._replied = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def send(self, message):
            self.sent.append(message)

        def __aiter__(self):
            return self

        async def __anext__(self):
            while not self.sent:
                await asyncio.sleep(0)
            if not self._replied:
                self._replied = True
                return "provider-ack"
            await asyncio.Future()

    upstream = FakeUpstream()
    connected_urls: list[str] = []

    def fake_connect(url: str, **_kwargs):
        connected_urls.append(url)
        return upstream

    monkeypatch.setattr("websockets.asyncio.client.connect", fake_connect)
    gateway = FakeViewerGateway()
    manager = RunSessionManager(ContractDemoPort())
    app = create_app(manager, viewer_gateway=gateway)
    with TestClient(app) as client:
        created = client.post("/sessions", json={}).json()
        session_id = created["snapshot"]["session_id"]
        managed = manager.authenticate(session_id, created["session_key"])
        managed.runtime_handle.snapshot = managed.runtime_handle.snapshot.model_copy(
            update={
                "task_id": session_id,
                "task_revision": 1,
                "run_status": RunStatus.PAUSED,
                "capabilities": frozenset(
                    {Capability.RETURN_CONTROL, Capability.CLOSE_SESSION}
                ),
                "viewer": ViewerState(
                    status="available",
                    provider="steel",
                    protected_path=f"/viewer/{session_id}",
                    reason_code="",
                    read_only=False,
                ),
                "control_owner": ControlOwner.USER,
                "control_lease_id": "user-control-lease:" + "u" * 32,
            }
        )
        document = client.get(f"/viewer/{session_id}")
        assert document.status_code == 200
        assert gateway.document_modes == [True]

        with client.websocket_connect(f"/viewer/{session_id}/input") as websocket:
            websocket.send_text('{"type":"mousemove"}')
            assert websocket.receive_text() == "provider-ack"
            managed.runtime_handle.snapshot = managed.runtime_handle.snapshot.model_copy(
                update={
                    "capabilities": frozenset(
                        {Capability.RETURN_CONTROL, Capability.CLOSE_SESSION}
                    ),
                    "control_owner": ControlOwner.USER,
                    "control_lease_id": "user-control-lease:" + "v" * 32,
                }
            )
            websocket.send_text('{"type":"keydown"}')
            with pytest.raises(WebSocketDisconnect) as closed:
                websocket.receive_text()
            assert closed.value.code == 4409

    assert connected_urls == [
        f"wss://connect.steel.dev/v1/sessions/{session_id}/input?token=private"
    ]
    assert upstream.sent == ['{"type":"mousemove"}']


@pytest.mark.asyncio
async def test_http_restart_recovery_authenticates_and_old_epoch_requires_resync(tmp_path):
    checkpoint_id = "runtime-checkpoint:" + "c" * 64
    registry = SQLiteSessionRecoveryRegistry(tmp_path / "shell-recovery.sqlite3")
    first_port = ContractDemoPort()
    first_manager = RunSessionManager(first_port, registry)
    created = await first_manager.create()
    managed = first_manager.authenticate(
        created.snapshot.session_id,
        created.session_key,
    )
    managed.runtime_handle.snapshot = managed.runtime_handle.snapshot.model_copy(
        update={
            "task_id": created.snapshot.session_id,
            "task_revision": 1,
            "task_text": "Paused task",
            "run_status": RunStatus.PAUSED,
            "checkpoint_id": checkpoint_id,
            "resume_eligible": True,
            "capabilities": frozenset(
                {Capability.RESUME_TASK, Capability.CLOSE_SESSION}
            ),
        }
    )
    old_epoch = managed.runtime_handle.snapshot.event_epoch
    await first_manager.close_all()

    class RecoveringDemoPort(ContractDemoPort):
        async def recover(self, session_id, supplied_checkpoint_id, expires_at):
            handle = await self.open(session_id, expires_at)
            handle.snapshot = handle.snapshot.model_copy(
                update={
                    "task_id": session_id,
                    "task_revision": 1,
                    "task_text": "Paused task",
                    "run_status": RunStatus.PAUSED,
                    "checkpoint_id": supplied_checkpoint_id,
                    "resume_eligible": True,
                    "capabilities": frozenset(
                        {Capability.RESUME_TASK, Capability.CLOSE_SESSION}
                    ),
                }
            )
            return handle

    app = create_app(RunSessionManager(RecoveringDemoPort(), registry))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthorized = await client.post(
            f"/sessions/{created.snapshot.session_id}/recover",
            headers={"X-Session-Key": "wrong"},
            json={"checkpoint_id": checkpoint_id},
        )
        assert unauthorized.status_code == 403

        recovered = await client.post(
            f"/sessions/{created.snapshot.session_id}/recover",
            headers={"X-Session-Key": created.session_key},
            json={"checkpoint_id": checkpoint_id},
        )
        assert recovered.status_code == 200
        recovered_snapshot = recovered.json()["snapshot"]
        assert recovered_snapshot["session_id"] == created.snapshot.session_id
        assert recovered_snapshot["event_epoch"] != old_epoch
        assert recovered_snapshot["run_status"] == "paused"

        stale_stream = await client.get(
            f"/sessions/{created.snapshot.session_id}/events",
            headers={"X-Session-Key": created.session_key},
            params={"event_epoch": old_epoch, "cursor": 0},
        )
        assert stale_stream.status_code == 409
        assert stale_stream.json()["detail"] == (
            "event epoch mismatch; snapshot resync required"
        )

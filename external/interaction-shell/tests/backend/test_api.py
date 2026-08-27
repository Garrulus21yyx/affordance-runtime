from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from interaction_shell.api import create_app
from interaction_shell.demo_port import ContractDemoPort
from interaction_shell.manager import RunSessionManager
from interaction_shell.port import RuntimeSessionUnavailable


@pytest.mark.asyncio
async def test_unified_command_route_is_typed_and_auth_isolated():
    app = create_app(RunSessionManager(ContractDemoPort()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/sessions", json={})).json()
        session_id = created["snapshot"]["session_id"]
        headers = {"X-Session-Key": created["session_key"]}
        response = await client.post(
            f"/sessions/{session_id}/commands",
            headers=headers,
            json={"kind": "start_task", "command_id": "start", "expected_task_revision": 0, "expected_run_status": "idle", "task": "Choose one"},
        )
        forbidden = await client.get(f"/sessions/{session_id}")
        removed_v2 = await client.post(f"/sessions/{session_id}/tasks", headers=headers, json={})
    assert response.status_code == 200
    assert response.json()["kind"] == "accepted"
    assert response.json()["snapshot"]["completion"] is None
    assert forbidden.status_code == 401
    assert removed_v2.status_code == 404


@pytest.mark.asyncio
async def test_closed_command_schema_rejects_missing_or_unknown_kinds():
    app = create_app(RunSessionManager(ContractDemoPort()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/sessions", json={})).json()
        path = f"/sessions/{created['snapshot']['session_id']}/commands"
        headers = {"X-Session-Key": created["session_key"]}
        missing = await client.post(path, headers=headers, json={"command_id": "c"})
        unknown = await client.post(path, headers=headers, json={"kind": "generic", "command_id": "c"})
    assert missing.status_code == 422
    assert unknown.status_code == 422


@pytest.mark.asyncio
async def test_lookup_is_live_first_and_uses_closed_result():
    app = create_app(RunSessionManager(ContractDemoPort()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = (await client.post("/sessions", json={})).json()
        response = await client.get(
            f"/sessions/{created['snapshot']['session_id']}",
            headers={"X-Session-Key": created["session_key"]},
        )
    assert response.status_code == 200
    assert response.json()["kind"] == "live_session"
    assert response.json()["snapshot"]["schema_version"] == "interaction-shell.v3"


@pytest.mark.asyncio
async def test_sse_schema_anchor_and_runtime_events_share_typed_envelope():
    manager = RunSessionManager(ContractDemoPort())
    app = create_app(manager)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        schema_event = (await client.get("/schemas/shell-event")).json()
        created = (await client.post("/sessions", json={})).json()
        session_id = created["snapshot"]["session_id"]
        headers = {"X-Session-Key": created["session_key"]}
        await client.post(
            f"/sessions/{session_id}/commands",
            headers=headers,
            json={"kind": "start_task", "command_id": "start", "expected_task_revision": 0, "expected_run_status": "idle", "task": "Choose"},
        )
    events = await manager.events(session_id, created["session_key"], 0)
    assert schema_event["type"] == "CUSTOM"
    assert schema_event["name"] == "snapshot.updated"
    assert events[0].schema_version == "interaction-shell.v3"
    assert events[0].cursor == 1


def test_openapi_has_fixed_unique_operation_ids_and_one_command_operation():
    schema = create_app(RunSessionManager(ContractDemoPort())).openapi()
    operation_ids = [operation["operationId"] for path in schema["paths"].values() for operation in path.values() if isinstance(operation, dict) and "operationId" in operation]
    assert len(operation_ids) == len(set(operation_ids))
    assert "submitCommand" in operation_ids
    assert "/sessions/{session_id}/commands" in schema["paths"]
    assert not any(path.endswith(("/tasks", "/commands/revise", "/commands/takeover", "/commands/optional")) for path in schema["paths"])


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

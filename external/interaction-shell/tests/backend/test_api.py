from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from interaction_shell.api import create_app
from interaction_shell.demo_port import ContractDemoPort
from interaction_shell.manager import RunSessionManager
from interaction_shell.port import RuntimeSessionUnavailable


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

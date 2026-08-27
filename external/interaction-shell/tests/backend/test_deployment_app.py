from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from interaction_shell import deployment_app
from interaction_shell.steel_viewer import SteelViewerGateway
from interaction_shell.viewer import ViewerHTTPResponse

from affordance_runtime.app.public_session import PublicSessionOpenError, PublicSessionOpenStage
from tests.unit.agent.test_target_runtime_facade import _runtime


class FakeWorld:
    async def reset(self, task):
        raise AssertionError(task)

    async def revise_task(self, task):
        raise AssertionError(task)

    async def capture(self, request):
        raise AssertionError(request)

    def is_current(self, request):
        raise AssertionError(request)

    async def execute(self, request):
        raise AssertionError(request)


class FakeSurface:
    def __init__(self, identity: int) -> None:
        self.identity = identity
        self.goal_instruction = "Click the button."
        self.close_count = 0

    async def close(self):
        self.close_count += 1

    def current_task_state(self):
        raise AssertionError("unit composition does not evaluate a task")


class FakeTrace:
    def __init__(self, identity: int, *, flush_fails: bool = False) -> None:
        self.identity = identity
        self.flush_fails = flush_fails
        self.flush_count = 0

    def flush_viewer(self) -> None:
        self.flush_count += 1
        if self.flush_fails:
            raise RuntimeError("trace flush failed")


class FakeSteelTransport:
    def __init__(self) -> None:
        self.created: list[int] = []
        self.released: list[str] = []

    async def create_session(self, api_key: str, *, timeout_ms: int):
        assert api_key == "viewer-key"
        self.created.append(timeout_ms)
        serial = len(self.created)
        return (
            f"provider-{serial}",
            f"wss://connect.steel.dev?sessionId=provider-{serial}",
            f"https://api.steel.dev/v1/sessions/provider-{serial}/debug",
        )

    async def release_session(self, api_key: str, provider_session_id: str) -> None:
        assert api_key == "viewer-key"
        self.released.append(provider_session_id)

    async def viewer_document(self, debug_url: str, *, interactive: bool):
        del debug_url, interactive
        return ViewerHTTPResponse(500, b"", "text/plain")

    async def ice_servers(self, provider_session_id: str, rtc_token: str):
        del provider_session_id, rtc_token
        return ViewerHTTPResponse(500, b"", "text/plain")

    async def whep(
        self,
        provider_session_id: str,
        rtc_token: str,
        body: bytes,
        content_type: str,
        region: str,
    ):
        del provider_session_id, rtc_token, body, content_type, region
        return ViewerHTTPResponse(500, b"", "text/plain")


def _patch_composition(
    monkeypatch,
    *,
    fail_composition: bool = False,
    trace_flush_fails: bool = False,
    role_calls: list[dict[str, object]] | None = None,
):
    surfaces: list[FakeSurface] = []
    traces: list[FakeTrace] = []

    def open_surface(*_args, **_kwargs):
        surface = FakeSurface(len(surfaces) + 1)
        surfaces.append(surface)
        return surface

    def open_trace(*_args, **_kwargs):
        trace = FakeTrace(len(traces) + 1, flush_fails=trace_flush_fails)
        traces.append(trace)
        return trace

    monkeypatch.setattr(deployment_app.BrowserGymSurfaceAdapter, "open", open_surface)
    monkeypatch.setattr(deployment_app, "UnifiedWorldEnvironment", lambda _sources: FakeWorld())
    def open_roles(*_args, **kwargs):
        if role_calls is not None:
            role_calls.append(dict(kwargs))
        return SimpleNamespace(
            action_policy=object(),
            goal_compiler=object(),
            task_revision_compiler=object(),
        )

    monkeypatch.setattr(deployment_app, "model_roles_from_environment", open_roles)
    monkeypatch.setattr(
        deployment_app,
        "trace_recorder_from_environment",
        open_trace,
    )
    if fail_composition:
        monkeypatch.setattr(
            deployment_app,
            "compose_target_runtime",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("composition failed")),
        )
    else:
        monkeypatch.setattr(deployment_app, "compose_target_runtime", lambda *_args, **_kwargs: _runtime())
    return surfaces, traces


@pytest.mark.asyncio
async def test_deployment_session_close_releases_surface_and_trace_once(monkeypatch):
    surfaces, traces = _patch_composition(monkeypatch)
    factory = deployment_app.BrowserGymDeploymentSessionFactory(
        deployment_app.BrowserGymDeploymentSettings("browsergym/miniwob.click-test", 7, 10, 90),
        {"MINIWOB_URL": "http://example.test/miniwob/"},
    )
    session = await factory.open("session:close", datetime.now(UTC) + timedelta(minutes=5))

    await session.close()
    await session.close()

    assert [surface.close_count for surface in surfaces] == [1]
    assert [trace.flush_count for trace in traces] == [1]


@pytest.mark.asyncio
async def test_deployment_factory_opens_and_closes_disjoint_runtime_browser_sessions(monkeypatch):
    surfaces, traces = _patch_composition(monkeypatch)
    factory = deployment_app.BrowserGymDeploymentSessionFactory(
        deployment_app.BrowserGymDeploymentSettings("browsergym/miniwob.click-test", 7, 10, 90),
        {"MINIWOB_URL": "http://example.test/miniwob/"},
    )
    expiry = datetime.now(UTC) + timedelta(minutes=5)
    first, second = await asyncio.gather(
        factory.open("session:first", expiry),
        factory.open("session:second", expiry),
    )

    assert first.runtime is not second.runtime
    assert first.lease.environment is not second.lease.environment
    assert len(surfaces) == 2
    await first.close()
    assert [surface.close_count for surface in surfaces] == [1, 0]
    assert [trace.flush_count for trace in traces] == [1, 0]
    assert (await second.snapshot()).session_id == "session:second"
    await second.close()
    assert [surface.close_count for surface in surfaces] == [1, 1]
    assert [trace.flush_count for trace in traces] == [1, 1]


@pytest.mark.asyncio
async def test_deployment_sessions_use_disjoint_step_stores_and_conversation_ids(
    monkeypatch,
    tmp_path,
):
    role_calls: list[dict[str, object]] = []
    _patch_composition(monkeypatch, role_calls=role_calls)
    stores: list[object] = []

    def open_step_store(_checkpoint_store, _session_id):
        store = object()
        stores.append(store)
        return store

    monkeypatch.setattr(deployment_app, "_model_step_store", open_step_store)
    factory = deployment_app.BrowserGymDeploymentSessionFactory(
        deployment_app.BrowserGymDeploymentSettings(
            "browsergym/miniwob.click-test", 7, 10, 90
        ),
        {"MINIWOB_URL": "http://example.test/miniwob/"},
        deployment_app.SQLiteRuntimeCheckpointStore(tmp_path / "checkpoints.sqlite3"),
    )
    expiry = datetime.now(UTC) + timedelta(minutes=5)

    first, second = await asyncio.gather(
        factory.open("session:steps:first", expiry),
        factory.open("session:steps:second", expiry),
    )

    assert [call["conversation_id"] for call in role_calls] == [
        "session:steps:first",
        "session:steps:second",
    ]
    assert [call["action_step_store"] for call in role_calls] == stores
    assert stores[0] is not stores[1]
    await asyncio.gather(first.close(), second.close())


@pytest.mark.asyncio
async def test_steel_profile_binds_runtime_and_viewer_to_one_lease_and_cleans_once(monkeypatch):
    surface_open_calls: list[dict[str, object]] = []
    surfaces, traces = _patch_composition(monkeypatch)
    original_open = deployment_app.BrowserGymSurfaceAdapter.open

    def record_open(*args, **kwargs):
        surface_open_calls.append(dict(kwargs))
        return original_open(*args, **kwargs)

    monkeypatch.setattr(deployment_app.BrowserGymSurfaceAdapter, "open", record_open)
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway("viewer-key", transport)
    factory = deployment_app.BrowserGymDeploymentSessionFactory(
        deployment_app.BrowserGymDeploymentSettings(
            "browsergym/miniwob.click-test",
            7,
            10,
            90,
            "steel",
        ),
        {"MINIWOB_URL": "https://tasks.example.test/miniwob/"},
        viewer_gateway=gateway,
    )

    session = await factory.open("session:steel", datetime.now(UTC) + timedelta(minutes=5))

    assert gateway.project(session).kind == "available"
    assert gateway.project(session).protected_path == "/viewer/session:steel"
    assert surface_open_calls[0]["gym_factory"] is not None
    await session.close()
    await session.close()
    assert [surface.close_count for surface in surfaces] == [1]
    assert [trace.flush_count for trace in traces] == [1]
    assert transport.released == ["provider-1"]
    assert gateway.project(session).kind == "unavailable"


@pytest.mark.asyncio
async def test_steel_profile_composition_failure_releases_browser_and_trace(monkeypatch):
    surfaces, traces = _patch_composition(monkeypatch, fail_composition=True)
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway("viewer-key", transport)
    factory = deployment_app.BrowserGymDeploymentSessionFactory(
        deployment_app.BrowserGymDeploymentSettings(
            "browsergym/miniwob.click-test",
            7,
            10,
            90,
            "steel",
        ),
        {"MINIWOB_URL": "https://tasks.example.test/miniwob/"},
        viewer_gateway=gateway,
    )

    with pytest.raises(PublicSessionOpenError) as raised:
        await factory.open("session:steel:failed", datetime.now(UTC) + timedelta(minutes=5))

    assert raised.value.stage is PublicSessionOpenStage.SESSION
    assert [surface.close_count for surface in surfaces] == [1]
    assert [trace.flush_count for trace in traces] == [1]
    assert transport.released == ["provider-1"]


@pytest.mark.asyncio
async def test_steel_profile_rejects_loopback_source_before_provider_creation(monkeypatch):
    _surfaces, traces = _patch_composition(monkeypatch)
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway("viewer-key", transport)
    factory = deployment_app.BrowserGymDeploymentSessionFactory(
        deployment_app.BrowserGymDeploymentSettings(
            "browsergym/miniwob.click-test",
            7,
            10,
            90,
            "steel",
        ),
        {"MINIWOB_URL": "http://127.0.0.1:18888/miniwob/"},
        viewer_gateway=gateway,
    )

    with pytest.raises(PublicSessionOpenError) as raised:
        await factory.open("session:steel:local", datetime.now(UTC) + timedelta(minutes=5))

    assert raised.value.code == "environment_source_not_remote"
    assert transport.created == []
    assert [trace.flush_count for trace in traces] == [1]


@pytest.mark.asyncio
async def test_model_step_store_is_deterministic_and_isolated_per_session(tmp_path):
    step_persistence = pytest.importorskip(
        "pydantic_ai_harness.step_persistence"
    )
    checkpoint_store = deployment_app.SQLiteRuntimeCheckpointStore(
        tmp_path / "checkpoints.sqlite3"
    )
    first = deployment_app._model_step_store(checkpoint_store, "session:first")
    second = deployment_app._model_step_store(checkpoint_store, "session:second")
    assert first is not None
    assert second is not None

    await asyncio.gather(
        first.register_run(
            step_persistence.RunRecord(
                run_id="run:first",
                conversation_id="session:first",
            )
        ),
        second.register_run(
            step_persistence.RunRecord(
                run_id="run:second",
                conversation_id="session:second",
            )
        ),
    )

    assert [run.run_id for run in await first.list_runs()] == ["run:first"]
    assert [run.run_id for run in await second.list_runs()] == ["run:second"]
    reopened = deployment_app._model_step_store(checkpoint_store, "session:first")
    assert reopened is not None
    assert (await reopened.get_run(run_id="run:first")) is not None


@pytest.mark.asyncio
async def test_environment_open_failure_releases_created_trace(monkeypatch):
    surfaces, traces = _patch_composition(monkeypatch)
    monkeypatch.setattr(
        deployment_app.BrowserGymSurfaceAdapter,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("environment open failed")),
    )
    factory = deployment_app.BrowserGymDeploymentSessionFactory(
        deployment_app.BrowserGymDeploymentSettings("browsergym/miniwob.click-test", 7, 10, 90),
        {"MINIWOB_URL": "http://example.test/miniwob/"},
    )

    with pytest.raises(PublicSessionOpenError) as caught:
        await factory.open("session:open-failure", datetime.now(UTC) + timedelta(minutes=5))

    assert caught.value.stage is PublicSessionOpenStage.ENVIRONMENT
    assert surfaces == []
    assert [trace.flush_count for trace in traces] == [1]


@pytest.mark.asyncio
async def test_deployment_factory_cleans_browser_when_later_composition_fails(monkeypatch):
    surfaces, traces = _patch_composition(monkeypatch, fail_composition=True)
    factory = deployment_app.BrowserGymDeploymentSessionFactory(
        deployment_app.BrowserGymDeploymentSettings("browsergym/miniwob.click-test", 7, 10, 90),
        {"MINIWOB_URL": "http://example.test/miniwob/"},
    )
    with pytest.raises(PublicSessionOpenError) as caught:
        await factory.open("session:failure", datetime.now(UTC) + timedelta(minutes=5))
    assert caught.value.stage is PublicSessionOpenStage.SESSION
    assert len(surfaces) == 1
    assert surfaces[0].close_count == 1
    assert [trace.flush_count for trace in traces] == [1]


@pytest.mark.asyncio
async def test_trace_cleanup_failure_is_fail_open_for_surface_cleanup(monkeypatch):
    surfaces, traces = _patch_composition(monkeypatch, trace_flush_fails=True)
    factory = deployment_app.BrowserGymDeploymentSessionFactory(
        deployment_app.BrowserGymDeploymentSettings("browsergym/miniwob.click-test", 7, 10, 90),
        {"MINIWOB_URL": "http://example.test/miniwob/"},
    )
    session = await factory.open("session:trace-failure", datetime.now(UTC) + timedelta(minutes=5))

    await session.close()

    assert [surface.close_count for surface in surfaces] == [1]
    assert [trace.flush_count for trace in traces] == [1]


@pytest.mark.asyncio
async def test_cancelled_session_open_recovers_and_closes_late_browser(monkeypatch):
    _surfaces, traces = _patch_composition(monkeypatch)
    started = threading.Event()
    release = threading.Event()
    surface = FakeSurface(1)

    def blocked_open(*_args, **_kwargs):
        started.set()
        assert release.wait(timeout=2)
        return surface

    monkeypatch.setattr(deployment_app.BrowserGymSurfaceAdapter, "open", blocked_open)
    factory = deployment_app.BrowserGymDeploymentSessionFactory(
        deployment_app.BrowserGymDeploymentSettings("browsergym/miniwob.click-test", 7, 10, 90),
        {"MINIWOB_URL": "http://example.test/miniwob/"},
    )
    opening = asyncio.create_task(factory.open("session:cancelled", datetime.now(UTC) + timedelta(minutes=5)))
    assert await asyncio.to_thread(started.wait, 1)

    opening.cancel()
    await asyncio.sleep(0)
    assert not opening.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await opening

    assert surface.close_count == 1
    assert [trace.flush_count for trace in traces] == [1]


@pytest.mark.asyncio
async def test_local_browsergym_recovery_refuses_replacement_environment(monkeypatch):
    open_calls = 0

    async def forbidden_open(_settings):
        nonlocal open_calls
        open_calls += 1
        raise AssertionError("restart recovery must not open a replacement browser")

    monkeypatch.setattr(deployment_app, "_open_surface", forbidden_open)
    factory = deployment_app.BrowserGymDeploymentSessionFactory(
        deployment_app.BrowserGymDeploymentSettings(
            "browsergym/miniwob.click-test", 7, 10, 90
        ),
        {"MINIWOB_URL": "http://example.test/miniwob/"},
    )

    with pytest.raises(PublicSessionOpenError, match="environment_not_reconnectable"):
        await factory.recover(
            "session:lost-browser",
            "runtime-checkpoint:" + "d" * 64,
            datetime.now(UTC) + timedelta(minutes=5),
        )

    assert open_calls == 0


def test_deployment_health_separates_runtime_viewer_and_durable_resume(monkeypatch):
    _patch_composition(monkeypatch)
    monkeypatch.setattr(
        deployment_app,
        "browsergym_api_inventory",
        lambda: SimpleNamespace(
            available=True,
            accepted=True,
            registered_task_ids=("browsergym/miniwob.click-test",),
        ),
    )
    factory = deployment_app.BrowserGymDeploymentSessionFactory(
        deployment_app.BrowserGymDeploymentSettings("browsergym/miniwob.click-test", 7, 10, 90),
        {"MINIWOB_URL": "http://example.test/miniwob/"},
    )
    health = factory.health()
    assert health["runtime_execution"]["status"] == "available"
    assert health["viewer"]["status"] == "unavailable"
    assert health["durable_resume"]["status"] == "unavailable"
    assert health["durable_pause"]["status"] == "unavailable"


def test_deployment_health_advertises_configured_durable_pause_only(monkeypatch, tmp_path):
    _patch_composition(monkeypatch)
    monkeypatch.setattr(
        deployment_app,
        "browsergym_api_inventory",
        lambda: SimpleNamespace(
            available=True,
            accepted=True,
            registered_task_ids=("browsergym/miniwob.click-test",),
        ),
    )
    factory = deployment_app.BrowserGymDeploymentSessionFactory(
        deployment_app.BrowserGymDeploymentSettings(
            "browsergym/miniwob.click-test", 7, 10, 90
        ),
        {"MINIWOB_URL": "http://example.test/miniwob/"},
        deployment_app.SQLiteRuntimeCheckpointStore(tmp_path / "checkpoints.sqlite3"),
    )

    health = factory.health()

    assert health["durable_pause"] == {"status": "available", "reason_code": ""}
    assert health["durable_resume"] == {
        "status": "unavailable",
        "reason_code": "environment_reconnect_not_implemented",
    }

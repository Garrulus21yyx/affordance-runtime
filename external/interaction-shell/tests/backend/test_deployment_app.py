from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from interaction_shell import deployment_app

from affordance_runtime.agent.observability import NullRunTraceSink
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


def _patch_composition(monkeypatch, *, fail_composition: bool = False):
    surfaces: list[FakeSurface] = []

    def open_surface(*_args, **_kwargs):
        surface = FakeSurface(len(surfaces) + 1)
        surfaces.append(surface)
        return surface

    monkeypatch.setattr(deployment_app.BrowserGymSurfaceAdapter, "open", open_surface)
    monkeypatch.setattr(deployment_app, "UnifiedWorldEnvironment", lambda _sources: FakeWorld())
    monkeypatch.setattr(
        deployment_app,
        "model_roles_from_environment",
        lambda *_args, **_kwargs: SimpleNamespace(action_policy=object(), goal_compiler=object()),
    )
    monkeypatch.setattr(
        deployment_app,
        "trace_recorder_from_environment",
        lambda *_args, **_kwargs: NullRunTraceSink(),
    )
    if fail_composition:
        monkeypatch.setattr(
            deployment_app,
            "compose_target_runtime",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("composition failed")),
        )
    else:
        monkeypatch.setattr(deployment_app, "compose_target_runtime", lambda *_args, **_kwargs: _runtime())
    return surfaces


@pytest.mark.asyncio
async def test_deployment_factory_opens_and_closes_disjoint_runtime_browser_sessions(monkeypatch):
    surfaces = _patch_composition(monkeypatch)
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
    assert (await second.snapshot()).session_id == "session:second"
    await second.close()
    assert [surface.close_count for surface in surfaces] == [1, 1]


@pytest.mark.asyncio
async def test_deployment_factory_cleans_browser_when_later_composition_fails(monkeypatch):
    surfaces = _patch_composition(monkeypatch, fail_composition=True)
    factory = deployment_app.BrowserGymDeploymentSessionFactory(
        deployment_app.BrowserGymDeploymentSettings("browsergym/miniwob.click-test", 7, 10, 90),
        {"MINIWOB_URL": "http://example.test/miniwob/"},
    )
    with pytest.raises(PublicSessionOpenError) as caught:
        await factory.open("session:failure", datetime.now(UTC) + timedelta(minutes=5))
    assert caught.value.stage is PublicSessionOpenStage.SESSION
    assert len(surfaces) == 1
    assert surfaces[0].close_count == 1


@pytest.mark.asyncio
async def test_cancelled_session_open_recovers_and_closes_late_browser(monkeypatch):
    _patch_composition(monkeypatch)
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

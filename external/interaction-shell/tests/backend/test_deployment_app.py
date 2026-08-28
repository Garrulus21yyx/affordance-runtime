from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from interaction_shell import deployment_app
from interaction_shell.content_filtering import (
    ContentFilterProfile,
    CosmeticFilterExtensionAttestation,
)
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


class FakeBrowser:
    def __init__(self, identity: int) -> None:
        self.identity = identity
        self.close_count = 0

    def close(self):
        self.close_count += 1


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
        self.block_ads: list[bool] = []
        self.extension_ids: list[tuple[str, ...]] = []
        self.released: list[str] = []

    async def create_session(
        self,
        api_key: str,
        *,
        timeout_ms: int,
        block_ads: bool,
        extension_ids: tuple[str, ...],
    ):
        assert api_key == "viewer-key"
        self.created.append(timeout_ms)
        self.block_ads.append(block_ads)
        self.extension_ids.append(extension_ids)
        serial = len(self.created)
        return (
            f"provider-{serial}",
            f"wss://connect.steel.dev?sessionId=provider-{serial}",
            f"https://api.steel.dev/v1/sessions/provider-{serial}/debug",
        )

    async def extension_is_attested(self, api_key: str, attestation) -> bool:
        del attestation
        assert api_key == "viewer-key"
        return True

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
    trace_calls: list[dict[str, object]] | None = None,
):
    surfaces: list[FakeBrowser] = []
    traces: list[FakeTrace] = []

    async def open_surface(*_args, **_kwargs):
        surface = FakeBrowser(len(surfaces) + 1)
        surfaces.append(surface)
        return surface

    def open_trace(*_args, **kwargs):
        if trace_calls is not None:
            trace_calls.append(dict(kwargs))
        trace = FakeTrace(len(traces) + 1, flush_fails=trace_flush_fails)
        traces.append(trace)
        return trace

    monkeypatch.setattr(deployment_app, "_open_browser", open_surface)
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


def test_deployment_filter_profile_defaults_off_and_is_typed() -> None:
    settings = deployment_app.BrowserDeploymentSettings.from_environment({})

    assert settings.content_filter_profile is ContentFilterProfile.OFF


def test_deployment_accepts_network_filter_only_for_steel() -> None:
    settings = deployment_app.BrowserDeploymentSettings.from_environment(
        {
            "INTERACTION_SHELL_BROWSER_PROVIDER": "steel",
            "INTERACTION_SHELL_CONTENT_FILTER_PROFILE": "network_ads.v1",
        }
    )

    assert settings.content_filter_profile is ContentFilterProfile.NETWORK_ADS

    with pytest.raises(ValueError, match="local browser provider"):
        deployment_app.BrowserDeploymentSettings.from_environment(
            {"INTERACTION_SHELL_CONTENT_FILTER_PROFILE": "network_ads.v1"}
        )


def test_deployment_rejects_unknown_filter_profile() -> None:
    with pytest.raises(ValueError, match="INTERACTION_SHELL_CONTENT_FILTER_PROFILE"):
        deployment_app.BrowserDeploymentSettings.from_environment(
            {
                "INTERACTION_SHELL_BROWSER_PROVIDER": "steel",
                "INTERACTION_SHELL_CONTENT_FILTER_PROFILE": "best-effort",
            }
        )


def test_deployment_parses_strict_filter_extension_attestation_atomically() -> None:
    environment = {
        "INTERACTION_SHELL_BROWSER_PROVIDER": "steel",
        "INTERACTION_SHELL_CONTENT_FILTER_PROFILE": "ads_and_cosmetic.v1",
        "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_ID": "ext_ubol_pinned",
        "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_NAME": "uBOLite_2026_825_1619",
        "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_CREATED_AT": "2026-08-25T16:20:50Z",
        "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_UPDATED_AT": "2026-08-25T16:20:50Z",
        "INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_SHA256": "1" * 64,
    }

    settings = deployment_app.BrowserDeploymentSettings.from_environment(environment)

    assert settings.cosmetic_filter_extension == CosmeticFilterExtensionAttestation(
        "ext_ubol_pinned",
        "uBOLite_2026_825_1619",
        "2026-08-25T16:20:50Z",
        "2026-08-25T16:20:50Z",
        "1" * 64,
    )

    environment.pop("INTERACTION_SHELL_STEEL_COSMETIC_EXTENSION_UPDATED_AT")
    with pytest.raises(ValueError, match="attestation is incomplete"):
        deployment_app.BrowserDeploymentSettings.from_environment(environment)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "expected_rendered_dom_only"),
    [
        (ContentFilterProfile.OFF, False),
        (ContentFilterProfile.ADS_AND_COSMETIC, True),
    ],
)
async def test_browser_open_enables_rendered_projection_only_for_strict_filtering(
    monkeypatch,
    profile: ContentFilterProfile,
    expected_rendered_dom_only: bool,
) -> None:
    calls: list[dict[str, object]] = []
    browser = FakeBrowser(1)

    def launch(*_args, **kwargs):
        calls.append(dict(kwargs))
        return browser

    monkeypatch.setattr(deployment_app.ThreadBoundBrowserSession, "launch", launch)
    settings = deployment_app.BrowserDeploymentSettings(
        "about:blank",
        10,
        90,
        "steel",
        profile,
    )

    opened = await deployment_app._open_browser(settings)

    assert opened is browser
    assert calls[0]["rendered_dom_only"] is expected_rendered_dom_only


@pytest.mark.asyncio
async def test_deployment_session_close_releases_surface_and_trace_once(monkeypatch):
    surfaces, traces = _patch_composition(monkeypatch)
    factory = deployment_app.BrowserDeploymentSessionFactory(
        deployment_app.BrowserDeploymentSettings("about:blank", 10, 90),
        {},
    )
    session = await factory.open("session:close", datetime.now(UTC) + timedelta(minutes=5))

    await session.close()
    await session.close()

    assert [surface.close_count for surface in surfaces] == [1]
    assert [trace.flush_count for trace in traces] == [1]


@pytest.mark.asyncio
async def test_deployment_factory_opens_and_closes_disjoint_runtime_browser_sessions(monkeypatch):
    surfaces, traces = _patch_composition(monkeypatch)
    factory = deployment_app.BrowserDeploymentSessionFactory(
        deployment_app.BrowserDeploymentSettings("about:blank", 10, 90),
        {},
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
    factory = deployment_app.BrowserDeploymentSessionFactory(
        deployment_app.BrowserDeploymentSettings("about:blank", 10, 90),
        {},
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
    surfaces, traces = _patch_composition(monkeypatch)
    browser_open_calls: list[tuple[object, object]] = []

    async def record_open(_settings, gateway, lease):
        browser_open_calls.append((gateway, lease))
        browser = FakeBrowser(len(surfaces) + 1)
        surfaces.append(browser)
        return browser

    monkeypatch.setattr(deployment_app, "_open_browser", record_open)
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway("viewer-key", transport)
    factory = deployment_app.BrowserDeploymentSessionFactory(
        deployment_app.BrowserDeploymentSettings("about:blank", 10, 90, "steel"),
        {},
        viewer_gateway=gateway,
    )

    session = await factory.open("session:steel", datetime.now(UTC) + timedelta(minutes=5))

    assert gateway.project(session).kind == "available"
    assert gateway.project(session).protected_path == "/viewer/session:steel"
    assert len(browser_open_calls) == 1
    assert browser_open_calls[0][0] is gateway
    assert browser_open_calls[0][1].provider_session_id == "provider-1"
    assert transport.block_ads == [False]
    await session.close()
    await session.close()
    assert [surface.close_count for surface in surfaces] == [1]
    assert [trace.flush_count for trace in traces] == [1]
    assert transport.released == ["provider-1"]
    assert gateway.project(session).kind == "unavailable"


@pytest.mark.asyncio
async def test_strict_filter_unavailability_is_preserved_at_public_session_open(monkeypatch):
    surfaces, traces = _patch_composition(monkeypatch)
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway(
        "viewer-key",
        transport,
        content_filter_profile=ContentFilterProfile.ADS_AND_COSMETIC,
    )
    factory = deployment_app.BrowserDeploymentSessionFactory(
        deployment_app.BrowserDeploymentSettings(
            "about:blank",
            10,
            90,
            "steel",
            ContentFilterProfile.ADS_AND_COSMETIC,
        ),
        {},
        viewer_gateway=gateway,
    )

    with pytest.raises(PublicSessionOpenError) as raised:
        await factory.open("session:strict-filter", datetime.now(UTC) + timedelta(minutes=5))

    assert raised.value.stage is PublicSessionOpenStage.ENVIRONMENT
    assert raised.value.code == "content_filter_unavailable"
    assert transport.created == []
    assert surfaces == []
    assert [trace.flush_count for trace in traces] == [1]


@pytest.mark.asyncio
async def test_strict_filter_identity_is_attached_to_trace_and_exact_steel_lease(monkeypatch):
    trace_calls: list[dict[str, object]] = []
    surfaces, traces = _patch_composition(monkeypatch, trace_calls=trace_calls)
    extension = CosmeticFilterExtensionAttestation(
        "ext_ubol_pinned",
        "uBOLite_2026_825_1619",
        "2026-08-25T16:20:50Z",
        "2026-08-25T16:20:50Z",
        "1" * 64,
    )
    settings = deployment_app.BrowserDeploymentSettings(
        "about:blank",
        10,
        90,
        "steel",
        ContentFilterProfile.ADS_AND_COSMETIC,
        extension,
    )
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway(
        "viewer-key",
        transport,
        content_filter_profile=settings.content_filter_profile,
        cosmetic_filter_extension=settings.cosmetic_filter_extension,
    )
    factory = deployment_app.BrowserDeploymentSessionFactory(
        settings,
        {},
        viewer_gateway=gateway,
    )

    session = await factory.open(
        "session:strict-filter:ready",
        datetime.now(UTC) + timedelta(minutes=5),
    )

    assert trace_calls == [
        {
            "directory": None,
            "run_id": "interaction-shell:session:strict-filter:ready",
            "session_id": "session:strict-filter:ready",
            "analysis_identity": settings.content_filter_trace_identity,
        }
    ]
    assert transport.block_ads == [True]
    assert transport.extension_ids == [(extension.extension_id,)]
    await session.close()
    assert [surface.close_count for surface in surfaces] == [1]
    assert [trace.flush_count for trace in traces] == [1]


@pytest.mark.asyncio
async def test_steel_profile_composition_failure_releases_browser_and_trace(monkeypatch):
    surfaces, traces = _patch_composition(monkeypatch, fail_composition=True)
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway("viewer-key", transport)
    factory = deployment_app.BrowserDeploymentSessionFactory(
        deployment_app.BrowserDeploymentSettings("about:blank", 10, 90, "steel"),
        {},
        viewer_gateway=gateway,
    )

    with pytest.raises(PublicSessionOpenError) as raised:
        await factory.open("session:steel:failed", datetime.now(UTC) + timedelta(minutes=5))

    assert raised.value.stage is PublicSessionOpenStage.SESSION
    assert [surface.close_count for surface in surfaces] == [1]
    assert [trace.flush_count for trace in traces] == [1]
    assert transport.released == ["provider-1"]


def test_open_browser_request_factory_accepts_free_user_goal_without_hidden_task_match():
    create = deployment_app._request_factory(12)

    request = create("session:free", "Open https://example.com and report its title")

    assert request.instruction == "Open https://example.com and report its title"
    assert request.boundary.loop_budget.max_turns == 12
    assert request.source_ref == "interaction-shell:open-browser:goal"


@pytest.mark.asyncio
async def test_model_step_store_is_deterministic_and_isolated_per_session(tmp_path):
    step_persistence = pytest.importorskip("pydantic_ai_harness.step_persistence")
    checkpoint_store = deployment_app.SQLiteRuntimeCheckpointStore(tmp_path / "checkpoints.sqlite3")
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
        deployment_app,
        "_open_browser",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("environment open failed")),
    )
    factory = deployment_app.BrowserDeploymentSessionFactory(
        deployment_app.BrowserDeploymentSettings("about:blank", 10, 90),
        {},
    )

    with pytest.raises(PublicSessionOpenError) as caught:
        await factory.open("session:open-failure", datetime.now(UTC) + timedelta(minutes=5))

    assert caught.value.stage is PublicSessionOpenStage.ENVIRONMENT
    assert surfaces == []
    assert [trace.flush_count for trace in traces] == [1]


@pytest.mark.asyncio
async def test_deployment_factory_cleans_browser_when_later_composition_fails(monkeypatch):
    surfaces, traces = _patch_composition(monkeypatch, fail_composition=True)
    factory = deployment_app.BrowserDeploymentSessionFactory(
        deployment_app.BrowserDeploymentSettings("about:blank", 10, 90),
        {},
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
    factory = deployment_app.BrowserDeploymentSessionFactory(
        deployment_app.BrowserDeploymentSettings("about:blank", 10, 90),
        {},
    )
    session = await factory.open("session:trace-failure", datetime.now(UTC) + timedelta(minutes=5))

    await session.close()

    assert [surface.close_count for surface in surfaces] == [1]
    assert [trace.flush_count for trace in traces] == [1]


@pytest.mark.asyncio
async def test_cancelled_session_open_recovers_and_closes_late_browser(monkeypatch):
    original_open_browser = deployment_app._open_browser
    _surfaces, traces = _patch_composition(monkeypatch)
    started = threading.Event()
    release = threading.Event()
    surface = FakeBrowser(1)

    def blocked_open(*_args, **_kwargs):
        started.set()
        assert release.wait(timeout=2)
        return surface

    monkeypatch.setattr(deployment_app, "_open_browser", original_open_browser)
    monkeypatch.setattr(deployment_app.ThreadBoundBrowserSession, "launch", blocked_open)
    factory = deployment_app.BrowserDeploymentSessionFactory(
        deployment_app.BrowserDeploymentSettings("about:blank", 10, 90),
        {},
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
async def test_local_browser_recovery_refuses_replacement_environment(monkeypatch):
    open_calls = 0

    async def forbidden_open(_settings):
        nonlocal open_calls
        open_calls += 1
        raise AssertionError("restart recovery must not open a replacement browser")

    monkeypatch.setattr(deployment_app, "_open_browser", forbidden_open)
    factory = deployment_app.BrowserDeploymentSessionFactory(
        deployment_app.BrowserDeploymentSettings("about:blank", 10, 90),
        {},
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
    factory = deployment_app.BrowserDeploymentSessionFactory(
        deployment_app.BrowserDeploymentSettings("about:blank", 10, 90),
        {},
    )
    health = factory.health()
    assert health["runtime_execution"]["status"] == "available"
    assert health["viewer"]["status"] == "unavailable"
    assert health["durable_resume"]["status"] == "unavailable"
    assert health["durable_pause"]["status"] == "unavailable"


def test_deployment_health_advertises_configured_durable_pause_only(monkeypatch, tmp_path):
    _patch_composition(monkeypatch)
    factory = deployment_app.BrowserDeploymentSessionFactory(
        deployment_app.BrowserDeploymentSettings("about:blank", 10, 90),
        {},
        deployment_app.SQLiteRuntimeCheckpointStore(tmp_path / "checkpoints.sqlite3"),
    )

    health = factory.health()

    assert health["durable_pause"] == {"status": "available", "reason_code": ""}
    assert health["durable_resume"] == {
        "status": "unavailable",
        "reason_code": "environment_reconnect_not_implemented",
    }

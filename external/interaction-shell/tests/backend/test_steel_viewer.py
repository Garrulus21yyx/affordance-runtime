from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from interaction_shell.content_filtering import (
    PINNED_UBOL_COMPLETE_PATCH_ID,
    PINNED_UBOL_VERSION,
    ContentFilterProfile,
    CosmeticFilterExtensionAttestation,
)
from interaction_shell.steel_viewer import (
    HTTPXSteelViewerTransport,
    SteelBrowserLease,
    SteelViewerGateway,
)
from interaction_shell.viewer import ViewerHTTPResponse, ViewerUnavailable


def _cosmetic_extension() -> CosmeticFilterExtensionAttestation:
    return CosmeticFilterExtensionAttestation(
        "ext_ubol_pinned",
        "uBOLite_2026_825_1619",
        "2026-08-25T16:20:50Z",
        "2026-08-25T16:20:50Z",
        "1" * 64,
    )


class FakeSteelTransport:
    def __init__(self) -> None:
        self.created: list[int] = []
        self.block_ads: list[bool] = []
        self.extension_ids: list[tuple[str, ...]] = []
        self.extension_attestations: list[CosmeticFilterExtensionAttestation] = []
        self.extension_attested = True
        self.released: list[str] = []
        self.ice_calls: list[tuple[str, str]] = []
        self.whep_calls: list[tuple[str, str, bytes, str, str]] = []
        self.document_status = 200
        self.ice_status = 200
        self.document_modes: list[bool] = []

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

    async def extension_is_attested(
        self,
        api_key: str,
        attestation: CosmeticFilterExtensionAttestation,
    ) -> bool:
        assert api_key == "viewer-key"
        self.extension_attestations.append(attestation)
        return self.extension_attested

    async def release_session(self, api_key: str, provider_session_id: str) -> None:
        assert api_key == "viewer-key"
        self.released.append(provider_session_id)

    async def viewer_document(
        self,
        debug_url: str,
        *,
        interactive: bool,
    ) -> ViewerHTTPResponse:
        self.document_modes.append(interactive)
        provider_session_id = debug_url.split("/")[-2]
        token = f"rtc-token-for-{provider_session_id}"
        input_token = f"input-token-for-{provider_session_id}"
        document = f"""
        <!doctype html><script src="https://js.sentry-cdn.com/probe.js"></script>
        <script>
        const sessionId = '{provider_session_id}';
        const apiBaseUrl = 'https://api.steel.dev';
        const rtcToken = '{token}';
        const wsUrl = 'wss://connect.steel.dev/v1/sessions/{provider_session_id}/input?token={input_token}';
        const interactive = '{str(interactive).lower()}' === 'true';
        fetch(`${{apiBaseUrl}}/v1/rtc/ice-servers/${{sessionId}}`);
        </script>
        """
        return ViewerHTTPResponse(self.document_status, document.encode(), "text/html")

    async def ice_servers(self, provider_session_id: str, rtc_token: str):
        self.ice_calls.append((provider_session_id, rtc_token))
        return ViewerHTTPResponse(self.ice_status, b'{"iceServers":[]}', "application/json")

    async def whep(
        self,
        provider_session_id: str,
        rtc_token: str,
        body: bytes,
        content_type: str,
        region: str,
    ):
        self.whep_calls.append((provider_session_id, rtc_token, body, content_type, region))
        return ViewerHTTPResponse(201, b"answer", "application/sdp")


@pytest.mark.asyncio
async def test_gateway_projects_one_secret_free_read_only_route_and_proxies_rtc() -> None:
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway("viewer-key", transport)
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    lease = await gateway.open("shell-session", expires_at)
    handle = SimpleNamespace()
    gateway.attach(handle, lease)

    state = gateway.project(handle)
    assert state.kind == "available"
    assert state.protected_path == "/viewer/shell-session"
    assert state.input_mode == "native"

    document = await gateway.document("shell-session")
    decoded = document.content.decode()
    assert "shell-session" in decoded
    for private in (
        "provider-1",
        "rtc-token-for-provider-1",
        "api.steel.dev",
        "connect.steel.dev",
        "viewer-key",
    ):
        assert private not in decoded
    assert "const interactive = false;" in decoded
    assert "const wsUrl = null;" in decoded
    assert "window.location.origin" in decoded
    assert transport.document_modes == [False]

    interactive_document = await gateway.document("shell-session", interactive=True)
    interactive_decoded = interactive_document.content.decode()
    assert "const interactive = true;" in interactive_decoded
    assert "/viewer/shell-session/input" in interactive_decoded
    assert "input-token-for-provider-1" not in interactive_decoded
    assert gateway.input_websocket_url("shell-session") == (
        "wss://connect.steel.dev/v1/sessions/provider-1/input?token=input-token-for-provider-1"
    )
    assert transport.document_modes == [False, True]

    ice = await gateway.ice_servers("shell-session")
    whep = await gateway.whep("shell-session", b"offer", "application/sdp", "iad")
    assert ice.status_code == 200
    assert whep.status_code == 201
    assert transport.ice_calls == [("provider-1", "rtc-token-for-provider-1")]
    assert transport.whep_calls == [("provider-1", "rtc-token-for-provider-1", b"offer", "application/sdp", "iad")]
    with pytest.raises(ViewerUnavailable) as unsupported_region:
        await gateway.whep("shell-session", b"offer", "application/sdp", "unknown-region")
    assert unsupported_region.value.code == "viewer_region_unsupported"

    await gateway.release(lease)
    await gateway.release(lease)
    assert transport.released == ["provider-1"]
    assert gateway.project(handle).kind == "unavailable"


@pytest.mark.asyncio
async def test_gateway_adapts_long_shell_ttl_to_provider_session_limit() -> None:
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway(
        "viewer-key",
        transport,
        maximum_session_timeout_ms=900_000,
    )
    shell_expiry = datetime.now(UTC) + timedelta(minutes=30)

    before_open = datetime.now(UTC)
    lease = await gateway.open("shell-session", shell_expiry)
    after_open = datetime.now(UTC)

    assert transport.created == [900_000]
    assert lease.expires_at < shell_expiry
    assert before_open + timedelta(milliseconds=900_000) <= lease.expires_at
    assert lease.expires_at <= after_open + timedelta(milliseconds=900_000)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile", "expected_block_ads"),
    [
        (ContentFilterProfile.OFF, False),
        (ContentFilterProfile.NETWORK_ADS, True),
    ],
)
async def test_gateway_maps_filter_profile_to_explicit_steel_network_policy(
    profile: ContentFilterProfile,
    expected_block_ads: bool,
) -> None:
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway(
        "viewer-key",
        transport,
        content_filter_profile=profile,
    )

    await gateway.open("shell-session", datetime.now(UTC) + timedelta(minutes=5))

    assert transport.block_ads == [expected_block_ads]


@pytest.mark.asyncio
async def test_off_profile_keeps_provisioned_extension_dormant() -> None:
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway(
        "viewer-key",
        transport,
        content_filter_profile=ContentFilterProfile.OFF,
        cosmetic_filter_extension=_cosmetic_extension(),
    )

    lease = await gateway.open(
        "shell-session",
        datetime.now(UTC) + timedelta(minutes=5),
    )

    assert transport.extension_attestations == []
    assert transport.extension_ids == [()]
    assert transport.block_ads == [False]
    assert lease.content_filter is not None
    assert lease.content_filter.profile is ContentFilterProfile.OFF


@pytest.mark.asyncio
async def test_strict_filter_profile_fails_before_steel_provider_activation() -> None:
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway(
        "viewer-key",
        transport,
        content_filter_profile=ContentFilterProfile.ADS_AND_COSMETIC,
    )

    with pytest.raises(ViewerUnavailable) as raised:
        await gateway.open("shell-session", datetime.now(UTC) + timedelta(minutes=5))

    assert raised.value.code == "content_filter_unavailable"
    assert transport.created == []
    assert transport.block_ads == []


@pytest.mark.asyncio
async def test_strict_filter_attests_and_attaches_the_exact_pinned_extension() -> None:
    transport = FakeSteelTransport()
    extension = _cosmetic_extension()
    gateway = SteelViewerGateway(
        "viewer-key",
        transport,
        content_filter_profile=ContentFilterProfile.ADS_AND_COSMETIC,
        cosmetic_filter_extension=extension,
    )

    lease = await gateway.open(
        "shell-session",
        datetime.now(UTC) + timedelta(minutes=5),
    )

    assert transport.extension_attestations == [extension]
    assert transport.block_ads == [True]
    assert transport.extension_ids == [(extension.extension_id,)]
    assert lease.content_filter is not None
    assert lease.content_filter.profile is ContentFilterProfile.ADS_AND_COSMETIC
    assert lease.content_filter.engine_id == "ublock-origin-lite"
    assert lease.content_filter.engine_version == (
        f"{PINNED_UBOL_VERSION}+{PINNED_UBOL_COMPLETE_PATCH_ID}"
    )
    assert lease.content_filter.ruleset_digest == f"sha256:{'1' * 64}"
    assert lease.content_filter.activation_latency_ms >= 0
    assert lease.content_filter.blocked_request_count is None
    assert lease.content_filter.cosmetic_rule_count is None


@pytest.mark.asyncio
async def test_strict_filter_rejects_changed_extension_metadata_before_session_create() -> None:
    transport = FakeSteelTransport()
    transport.extension_attested = False
    gateway = SteelViewerGateway(
        "viewer-key",
        transport,
        content_filter_profile=ContentFilterProfile.ADS_AND_COSMETIC,
        cosmetic_filter_extension=_cosmetic_extension(),
    )

    with pytest.raises(ViewerUnavailable) as raised:
        await gateway.open("shell-session", datetime.now(UTC) + timedelta(minutes=5))

    assert raised.value.code == "content_filter_unavailable"
    assert transport.created == []


@pytest.mark.asyncio
@pytest.mark.parametrize("block_ads", [False, True])
async def test_http_transport_never_relies_on_steel_block_ads_default(
    monkeypatch,
    block_ads: bool,
) -> None:
    transport = HTTPXSteelViewerTransport()
    request_bodies: list[object] = []

    async def request(method, url, **kwargs):
        assert method == "POST"
        assert url == "https://api.steel.dev/v1/sessions"
        request_bodies.append(kwargs["json"])
        return SimpleNamespace(
            status_code=201,
            json=lambda: {
                "id": "provider-session",
                "websocketUrl": "wss://connect.steel.dev?sessionId=provider-session",
                "debugUrl": "https://api.steel.dev/v1/sessions/provider-session/debug",
            },
        )

    monkeypatch.setattr(transport, "_request", request)

    await transport.create_session(
        "viewer-key",
        timeout_ms=90_000,
        block_ads=block_ads,
        extension_ids=(),
    )

    assert request_bodies == [
        {
            "debugConfig": {"interactive": True, "systemCursor": False},
            "timeout": 90_000,
            "inactivityTimeout": 90_000,
            "blockAds": block_ads,
        }
    ]


@pytest.mark.asyncio
async def test_http_transport_attests_exact_extension_metadata(monkeypatch) -> None:
    transport = HTTPXSteelViewerTransport()
    extension = _cosmetic_extension()

    async def request(method, url, **kwargs):
        assert method == "GET"
        assert url == "https://api.steel.dev/v1/extensions"
        assert kwargs["headers"] == {"steel-api-key": "viewer-key"}
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "count": 1,
                "extensions": [
                    {
                        "id": extension.extension_id,
                        "name": extension.name,
                        "createdAt": extension.created_at,
                        "updatedAt": extension.updated_at,
                    }
                ],
            },
        )

    monkeypatch.setattr(transport, "_request", request)

    assert await transport.extension_is_attested("viewer-key", extension) is True


def test_gateway_rejects_provider_timeout_below_supported_minimum() -> None:
    with pytest.raises(ValueError, match="at least 60000"):
        SteelViewerGateway(
            "viewer-key",
            FakeSteelTransport(),
            maximum_session_timeout_ms=59_999,
        )


@pytest.mark.asyncio
async def test_read_only_document_revokes_the_cached_provider_input_locator() -> None:
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway("viewer-key", transport)
    lease = await gateway.open(
        "shell-session",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    handle = SimpleNamespace()
    gateway.attach(handle, lease)

    await gateway.document("shell-session", interactive=True)
    assert gateway.input_websocket_url("shell-session")
    await gateway.document("shell-session", interactive=False)

    with pytest.raises(ViewerUnavailable, match="viewer_input_not_initialized"):
        gateway.input_websocket_url("shell-session")
    await gateway.release(lease)


@pytest.mark.asyncio
async def test_gateway_keeps_two_browser_and_viewer_leases_isolated() -> None:
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway("viewer-key", transport)
    expiry = datetime.now(UTC) + timedelta(minutes=5)
    first = await gateway.open("shell:first", expiry)
    second = await gateway.open("shell:second", expiry)
    first_handle, second_handle = SimpleNamespace(), SimpleNamespace()
    gateway.attach(first_handle, first)
    gateway.attach(second_handle, second)

    await gateway.document("shell:first")
    await gateway.document("shell:second")
    await gateway.release(first)

    assert gateway.project(first_handle).kind == "unavailable"
    assert gateway.project(second_handle).kind == "available"
    await gateway.ice_servers("shell:second")
    assert transport.ice_calls[-1] == ("provider-2", "rtc-token-for-provider-2")
    await gateway.release(second)
    assert transport.released == ["provider-1", "provider-2"]


@pytest.mark.asyncio
async def test_provider_viewer_loss_does_not_release_the_runtime_browser_lease() -> None:
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway("viewer-key", transport)
    lease = await gateway.open("shell-session", datetime.now(UTC) + timedelta(minutes=5))
    handle = SimpleNamespace()
    gateway.attach(handle, lease)
    await gateway.document("shell-session")
    transport.ice_status = 410

    response = await gateway.ice_servers("shell-session")

    assert response.status_code == 410
    assert gateway.project(handle).reason_code == "viewer_session_lost"
    assert transport.released == []
    await gateway.release(lease)


@pytest.mark.asyncio
async def test_client_specific_whep_failure_does_not_poison_browser_lease() -> None:
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway("viewer-key", transport)
    lease = await gateway.open("shell-session", datetime.now(UTC) + timedelta(minutes=5))
    handle = SimpleNamespace()
    gateway.attach(handle, lease)
    await gateway.document("shell-session")

    original_whep = transport.whep

    async def rejected_offer(*args, **kwargs):
        del args, kwargs
        return ViewerHTTPResponse(400, b"unsupported offer", "text/plain")

    transport.whep = rejected_offer
    response = await gateway.whep("shell-session", b"offer", "application/sdp", "iad")

    assert response.status_code == 400
    assert gateway.project(handle).kind == "available"
    transport.whep = original_whep
    assert (await gateway.whep("shell-session", b"offer", "application/sdp", "iad")).status_code == 201
    await gateway.release(lease)


@pytest.mark.asyncio
async def test_expired_viewer_lease_fails_typed_without_provider_lookup() -> None:
    transport = FakeSteelTransport()
    gateway = SteelViewerGateway("viewer-key", transport)
    lease = SteelBrowserLease(
        "shell-session",
        "provider-session",
        "wss://connect.steel.dev?sessionId=provider-session",
        "https://api.steel.dev/v1/sessions/provider-session/debug",
        datetime.now(UTC) - timedelta(seconds=1),
    )
    handle = SimpleNamespace()
    gateway.attach(handle, lease)

    assert gateway.project(handle).reason_code == "viewer_session_expired"
    with pytest.raises(ViewerUnavailable) as raised:
        await gateway.document("shell-session")
    assert raised.value.status_code == 410
    await gateway.release(lease)


def test_steel_playwright_facade_reuses_exact_remote_context() -> None:
    pages = [FakePage()]
    context = FakeContext(pages)
    browser = FakeBrowser(context)
    chromium = FakeChromium(browser)
    owner = SimpleNamespace(selectors=object(), chromium=chromium)
    lease = SteelBrowserLease(
        "shell-session",
        "provider-session",
        "wss://connect.steel.dev?sessionId=provider-session",
        "https://api.steel.dev/v1/sessions/provider-session/debug",
        datetime.now(UTC) + timedelta(minutes=5),
    )
    gateway = SteelViewerGateway("viewer-key", FakeSteelTransport())

    facade = gateway.environment_playwright_factory(lease)(owner)
    connected = facade.chromium.launch(headless=True)
    claimed = connected.new_context(viewport={"width": 332, "height": 214})
    page = claimed.new_page()

    assert chromium.endpoint.startswith("wss://connect.steel.dev?")
    assert "sessionId=provider-session" in chromium.endpoint
    assert "apiKey=viewer-key" in chromium.endpoint
    assert pages[0].close_count == 0
    assert page is pages[0]
    assert page.viewport == {"width": 332, "height": 214}
    assert connected._browser is browser  # noqa: SLF001 - identity witness


class FakePage:
    def __init__(self) -> None:
        self.close_count = 0
        self.viewport = None

    def close(self) -> None:
        self.close_count += 1

    def set_viewport_size(self, viewport) -> None:
        self.viewport = viewport


class FakeContext:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages

    def new_page(self) -> FakePage:
        page = FakePage()
        self.pages.append(page)
        return page


class FakeBrowser:
    def __init__(self, context: FakeContext) -> None:
        self.contexts = [context]

    def close(self) -> None:
        return None


class FakeChromium:
    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser
        self.endpoint = ""

    def connect_over_cdp(self, endpoint: str) -> FakeBrowser:
        self.endpoint = endpoint
        return self.browser

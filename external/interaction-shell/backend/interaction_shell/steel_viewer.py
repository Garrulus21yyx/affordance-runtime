"""Deployment-private Steel browser lease and protected read-only viewer projection."""

from __future__ import annotations

import json
import logging
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from affordance_runtime.app.public_session import PublicRuntimeSessionHandle

from .contracts import ViewerState
from .viewer import ViewerHTTPResponse, ViewerUnavailable

logger = logging.getLogger(__name__)

_STEEL_API_ORIGIN = "https://api.steel.dev"
_STEEL_API_HOST = "api.steel.dev"
_STEEL_CDP_HOST = "connect.steel.dev"
_MAX_VIEWER_DOCUMENT_BYTES = 2 * 1024 * 1024
_MAX_RTC_BODY_BYTES = 2 * 1024 * 1024


SteelViewerUnavailable = ViewerUnavailable


@dataclass
class SteelBrowserLease:
    shell_session_id: str
    provider_session_id: str
    websocket_url: str
    debug_url: str
    expires_at: datetime
    rtc_token: str = ""
    unavailable_reason: str = ""
    released: bool = False


class SteelViewerTransport(Protocol):
    async def create_session(
        self,
        api_key: str,
        *,
        timeout_ms: int,
    ) -> tuple[str, str, str]: ...

    async def release_session(self, api_key: str, provider_session_id: str) -> None: ...

    async def viewer_document(self, debug_url: str) -> ViewerHTTPResponse: ...

    async def ice_servers(
        self,
        provider_session_id: str,
        rtc_token: str,
    ) -> ViewerHTTPResponse: ...

    async def whep(
        self,
        provider_session_id: str,
        rtc_token: str,
        body: bytes,
        content_type: str,
    ) -> ViewerHTTPResponse: ...


class HTTPXSteelViewerTransport:
    """Small official-REST adapter; all reusable credentials remain server-side."""

    def __init__(self, *, timeout_s: float = 30.0) -> None:
        self._timeout_s = timeout_s

    async def create_session(
        self,
        api_key: str,
        *,
        timeout_ms: int,
    ) -> tuple[str, str, str]:
        response = await self._request(
            "POST",
            f"{_STEEL_API_ORIGIN}/v1/sessions",
            headers={"steel-api-key": api_key},
            json={
                "debugConfig": {"interactive": False, "systemCursor": False},
                "timeout": timeout_ms,
                "inactivityTimeout": min(timeout_ms, 300_000),
            },
        )
        if response.status_code != 201:
            raise SteelViewerUnavailable("viewer_provider_session_create_failed")
        try:
            payload = response.json()
            provider_session_id = _required_text(payload, "id")
            websocket_url = _validated_provider_url(
                _required_text(payload, "websocketUrl"),
                scheme="wss",
                host=_STEEL_CDP_HOST,
            )
            debug_url = _validated_provider_url(
                _required_text(payload, "debugUrl"),
                scheme="https",
                host=_STEEL_API_HOST,
            )
        except (TypeError, ValueError) as exc:
            raise SteelViewerUnavailable("viewer_provider_session_invalid") from exc
        return provider_session_id, websocket_url, debug_url

    async def release_session(self, api_key: str, provider_session_id: str) -> None:
        response = await self._request(
            "POST",
            f"{_STEEL_API_ORIGIN}/v1/sessions/{provider_session_id}/release",
            headers={"steel-api-key": api_key},
        )
        if response.status_code not in {200, 404, 410}:
            raise SteelViewerUnavailable("viewer_provider_session_release_failed")

    async def viewer_document(self, debug_url: str) -> ViewerHTTPResponse:
        separator = "&" if "?" in debug_url else "?"
        response = await self._request(
            "GET",
            f"{debug_url}{separator}interactive=false",
            follow_redirects=True,
        )
        return _bounded_response(response, _MAX_VIEWER_DOCUMENT_BYTES)

    async def ice_servers(
        self,
        provider_session_id: str,
        rtc_token: str,
    ) -> ViewerHTTPResponse:
        response = await self._request(
            "GET",
            f"{_STEEL_API_ORIGIN}/v1/rtc/ice-servers/{provider_session_id}",
            headers={"Authorization": f"Bearer {rtc_token}"},
        )
        return _bounded_response(response, _MAX_RTC_BODY_BYTES)

    async def whep(
        self,
        provider_session_id: str,
        rtc_token: str,
        body: bytes,
        content_type: str,
    ) -> ViewerHTTPResponse:
        if len(body) > _MAX_RTC_BODY_BYTES:
            raise SteelViewerUnavailable("viewer_request_too_large", 413)
        response = await self._request(
            "POST",
            f"{_STEEL_API_ORIGIN}/v1/rtc/whep/{provider_session_id}",
            headers={
                "Authorization": f"Bearer {rtc_token}",
                "Content-Type": content_type,
            },
            content=body,
        )
        return _bounded_response(response, _MAX_RTC_BODY_BYTES)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json: object | None = None,
        content: bytes | None = None,
        follow_redirects: bool = False,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                return await client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    content=content,
                    follow_redirects=follow_redirects,
                )
        except httpx.HTTPError:
            # Provider URLs may contain reusable locators. Never retain them in
            # the public exception chain or application logs.
            raise SteelViewerUnavailable("viewer_provider_unavailable") from None


class SteelViewerGateway:
    """Own the mapping from an opaque Runtime handle to one Steel browser lease."""

    def __init__(
        self,
        api_key: str,
        transport: SteelViewerTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Steel viewer requires a nonempty API key")
        self.__api_key = api_key
        self._transport = transport or HTTPXSteelViewerTransport()
        self._leases: dict[str, SteelBrowserLease] = {}
        self._handle_sessions: dict[int, str] = {}

    async def open(self, session_id: str, expires_at: datetime) -> SteelBrowserLease:
        remaining_ms = max(60_000, int((expires_at - datetime.now(UTC)).total_seconds() * 1000))
        provider_session_id, websocket_url, debug_url = await self._transport.create_session(
            self.__api_key,
            timeout_ms=remaining_ms,
        )
        return SteelBrowserLease(
            session_id,
            provider_session_id,
            websocket_url,
            debug_url,
            expires_at,
        )

    def attach(
        self,
        handle: PublicRuntimeSessionHandle,
        lease: SteelBrowserLease,
    ) -> None:
        if lease.shell_session_id in self._leases or id(handle) in self._handle_sessions:
            raise RuntimeError("viewer lease is already attached")
        self._leases[lease.shell_session_id] = lease
        self._handle_sessions[id(handle)] = lease.shell_session_id

    async def release(self, lease: SteelBrowserLease) -> None:
        if lease.released:
            return
        lease.released = True
        self._leases.pop(lease.shell_session_id, None)
        for handle_id, session_id in tuple(self._handle_sessions.items()):
            if secrets.compare_digest(session_id, lease.shell_session_id):
                self._handle_sessions.pop(handle_id, None)
        try:
            await self._transport.release_session(self.__api_key, lease.provider_session_id)
        except Exception:
            logger.exception("Steel viewer lease cleanup failed for shell session")

    def project(self, handle: PublicRuntimeSessionHandle) -> ViewerState:
        session_id = self._handle_sessions.get(id(handle))
        lease = self._leases.get(session_id) if session_id is not None else None
        if lease is None or lease.released:
            return ViewerState(reason_code="viewer_session_unavailable")
        if datetime.now(UTC) >= lease.expires_at:
            return ViewerState(reason_code="viewer_session_expired")
        if lease.unavailable_reason:
            return ViewerState(reason_code=lease.unavailable_reason)
        return ViewerState(
            status="available",
            provider="steel",
            protected_path=f"/viewer/{lease.shell_session_id}",
            reason_code="",
            read_only=True,
        )

    def environment_playwright_factory(self, lease: SteelBrowserLease):
        endpoint = _cdp_endpoint(lease.websocket_url, self.__api_key)

        def create(owner_playwright: object) -> object:
            return _SteelEnvironmentPlaywright(owner_playwright, endpoint)

        return create

    async def document(self, session_id: str) -> ViewerHTTPResponse:
        lease = self._active_lease(session_id)
        response = await self._transport.viewer_document(lease.debug_url)
        if response.status_code != 200:
            self._record_provider_failure(lease, response.status_code)
            raise SteelViewerUnavailable(lease.unavailable_reason)
        if not response.content_type.startswith("text/html"):
            lease.unavailable_reason = "viewer_provider_document_invalid"
            raise SteelViewerUnavailable(lease.unavailable_reason)
        try:
            source = response.content.decode("utf-8")
            document, rtc_token = _protect_steel_document(
                source,
                session_id,
                lease.provider_session_id,
            )
        except (UnicodeDecodeError, ValueError) as exc:
            lease.unavailable_reason = "viewer_provider_document_invalid"
            raise SteelViewerUnavailable(lease.unavailable_reason) from exc
        lease.rtc_token = rtc_token
        return ViewerHTTPResponse(200, document.encode("utf-8"), "text/html; charset=utf-8")

    async def ice_servers(self, session_id: str) -> ViewerHTTPResponse:
        lease = self._lease_with_rtc_token(session_id)
        response = await self._transport.ice_servers(
            lease.provider_session_id,
            lease.rtc_token,
        )
        if response.status_code != 200:
            self._record_provider_failure(lease, response.status_code)
        return response

    async def whep(
        self,
        session_id: str,
        body: bytes,
        content_type: str,
    ) -> ViewerHTTPResponse:
        lease = self._lease_with_rtc_token(session_id)
        response = await self._transport.whep(
            lease.provider_session_id,
            lease.rtc_token,
            body,
            content_type,
        )
        if response.status_code not in {200, 201}:
            self._record_provider_failure(lease, response.status_code)
        return response

    def _active_lease(self, session_id: str) -> SteelBrowserLease:
        lease = self._leases.get(session_id)
        if lease is None or lease.released:
            raise SteelViewerUnavailable("viewer_session_unavailable", 404)
        if datetime.now(UTC) >= lease.expires_at:
            raise SteelViewerUnavailable("viewer_session_expired", 410)
        if lease.unavailable_reason:
            raise SteelViewerUnavailable(lease.unavailable_reason)
        return lease

    def _lease_with_rtc_token(self, session_id: str) -> SteelBrowserLease:
        lease = self._active_lease(session_id)
        if not lease.rtc_token:
            raise SteelViewerUnavailable("viewer_document_not_initialized", 409)
        return lease

    @staticmethod
    def _record_provider_failure(lease: SteelBrowserLease, status_code: int) -> None:
        lease.unavailable_reason = (
            "viewer_session_lost" if status_code in {404, 410} else "viewer_provider_unavailable"
        )


class _SteelEnvironmentPlaywright:
    __slots__ = ("_owner", "chromium", "selectors")

    def __init__(self, owner: object, endpoint: str) -> None:
        self._owner = owner
        typed_owner = cast(Any, owner)
        self.selectors = typed_owner.selectors
        self.chromium = _SteelChromium(typed_owner.chromium, endpoint)

    def __getattr__(self, name: str) -> object:
        return getattr(self._owner, name)


class _SteelChromium:
    __slots__ = ("_chromium", "_endpoint")

    def __init__(self, chromium: Any, endpoint: str) -> None:
        self._chromium = chromium
        self._endpoint = endpoint

    def launch(self, **_local_launch_options: object) -> object:
        try:
            browser = self._chromium.connect_over_cdp(self._endpoint)
            return _SteelBrowser(browser)
        except Exception:  # noqa: BLE001 - hide the credential-bearing CDP endpoint
            raise RuntimeError("Steel browser connection failed") from None


class _SteelBrowser:
    __slots__ = ("_browser", "_context_claimed")

    def __init__(self, browser: Any) -> None:
        self._browser = browser
        self._context_claimed = False

    def new_context(self, **options: object) -> object:
        if self._context_claimed:
            raise RuntimeError("Steel BrowserGym session already claimed its context")
        contexts = tuple(cast(Any, self._browser).contexts)
        if len(contexts) != 1:
            raise RuntimeError("Steel browser did not expose exactly one default context")
        unsupported = {
            name: value
            for name, value in options.items()
            if name not in {"viewport", "no_viewport", "record_video_dir", "record_video_size"}
            and value is not None
        }
        if unsupported:
            raise RuntimeError("Steel browser context does not support requested overrides")
        if options.get("record_video_dir") is not None:
            raise RuntimeError("Steel browser context cannot enable local Playwright video recording")
        viewport = options.get("viewport")
        self._context_claimed = True
        return _SteelContext(contexts[0], viewport if isinstance(viewport, dict) else None)

    def close(self) -> None:
        self._browser.close()

    def __getattr__(self, name: str) -> object:
        return getattr(self._browser, name)


class _SteelContext:
    __slots__ = ("_context", "_page_claimed", "_viewport")

    def __init__(self, context: Any, viewport: dict[str, object] | None) -> None:
        self._context = context
        self._viewport = viewport
        self._page_claimed = False

    def new_page(self) -> object:
        if self._page_claimed:
            raise RuntimeError("Steel BrowserGym context already owns its task page")
        pages = tuple(cast(Any, self._context).pages)
        if len(pages) > 1:
            raise RuntimeError("Steel browser exposed more than one unclaimed task page")
        # Steel's sole initial page is also the provider session keepalive.
        # Closing it before opening another page terminates the remote browser,
        # so BrowserGym claims that page instead of replacing it.
        page = pages[0] if pages else self._context.new_page()
        if self._viewport is not None:
            page.set_viewport_size(self._viewport)
        self._page_claimed = True
        return page

    def __getattr__(self, name: str) -> object:
        return getattr(self._context, name)


def _required_text(payload: object, name: str) -> str:
    if not isinstance(payload, dict):
        raise TypeError("provider response must be an object")
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"provider response omitted {name}")
    return value


def _validated_provider_url(value: str, *, scheme: str, host: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != scheme or parsed.hostname != host or parsed.username or parsed.password:
        raise ValueError("provider returned an unexpected endpoint")
    return value


def _cdp_endpoint(websocket_url: str, api_key: str) -> str:
    parsed = urlparse(_validated_provider_url(websocket_url, scheme="wss", host=_STEEL_CDP_HOST))
    query = [(name, value) for name, value in parse_qsl(parsed.query) if name != "apiKey"]
    query.append(("apiKey", api_key))
    return urlunparse(parsed._replace(query=urlencode(query)))


def _bounded_response(response: httpx.Response, maximum_bytes: int) -> ViewerHTTPResponse:
    content = response.content
    if len(content) > maximum_bytes:
        raise SteelViewerUnavailable("viewer_provider_response_too_large")
    return ViewerHTTPResponse(
        response.status_code,
        content,
        response.headers.get("content-type", "application/octet-stream"),
    )


def _protect_steel_document(
    source: str,
    shell_session_id: str,
    provider_session_id: str,
) -> tuple[str, str]:
    assignments = {
        "session": re.compile(r"const\s+sessionId\s*=\s*(['\"])(?P<value>.*?)\1\s*;"),
        "api": re.compile(r"const\s+apiBaseUrl\s*=\s*(['\"])(?P<value>.*?)\1\s*;"),
        "rtc": re.compile(r"const\s+rtcToken\s*=\s*(['\"])(?P<value>.*?)\1\s*;"),
        "websocket": re.compile(r"const\s+wsUrl\s*=\s*(['\"])(?P<value>.*?)\1\s*;"),
        "interactive": re.compile(r"const\s+interactive\s*=.*?;"),
    }
    matches = {name: tuple(pattern.finditer(source)) for name, pattern in assignments.items()}
    if any(len(found) != 1 for found in matches.values()):
        raise ValueError("Steel viewer document contract changed")
    if matches["session"][0].group("value") != provider_session_id:
        raise ValueError("Steel viewer document session changed")
    rtc_token = matches["rtc"][0].group("value")
    if not rtc_token or len(rtc_token) > 8192:
        raise ValueError("Steel viewer document omitted its RTC token")

    document = assignments["session"].sub(
        f"const sessionId = {json.dumps(shell_session_id)};",
        source,
    )
    proxy_base = f"/viewer/{shell_session_id}/steel"
    document = assignments["api"].sub(
        f"const apiBaseUrl = window.location.origin + {json.dumps(proxy_base)};",
        document,
    )
    document = assignments["rtc"].sub("const rtcToken = '';", document)
    document = assignments["websocket"].sub("const wsUrl = null;", document)
    document = assignments["interactive"].sub("const interactive = false;", document)
    document = re.sub(
        r"<script\b[^>]*\bsrc=(['\"])[^'\"]+\1[^>]*>\s*</script>",
        "",
        document,
        flags=re.IGNORECASE,
    )
    forbidden = (provider_session_id, rtc_token, "api.steel.dev", "connect.steel.dev", "app.steel.dev")
    if any(value in document for value in forbidden):
        raise ValueError("Steel viewer document retained a private provider locator")
    return document, rtc_token

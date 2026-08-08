"""Narrow WoT HTTP and credential late-binding boundary."""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from affordance_runtime.adapters.wot_security import SecurityScheme, build_auth
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.surfaces.wot.contracts import (
    WotAffordanceBinding,
    WotTransportResult,
    WotTransportStatus,
)


class CredentialResolver(Protocol):
    def resolve(self, thing_id: str, security_scheme_ref: str) -> str | None: ...


class WotTransportPort(Protocol):
    def reset(self) -> None: ...

    def fetch_thing_description(self) -> dict[str, Any]: ...

    def probe_thing_revision(self) -> dict[str, Any]: ...

    def supports(self, route: WotAffordanceBinding) -> bool: ...

    def read_property(
        self,
        route: WotAffordanceBinding,
        scheme: SecurityScheme,
    ) -> WotTransportResult: ...

    def execute_affordance(
        self,
        route: WotAffordanceBinding,
        scheme: SecurityScheme,
        parameters: dict[str, Any],
    ) -> WotTransportResult: ...


@dataclass(frozen=True)
class MappingCredentialResolver:
    credentials: Mapping[tuple[str, str], str] = field(default_factory=dict, repr=False)

    def resolve(self, thing_id: str, security_scheme_ref: str) -> str | None:
        return self.credentials.get((thing_id, security_scheme_ref))


@dataclass
class HttpWotTransport:
    thing_description_url: str
    credential_resolver: CredentialResolver | None = field(default=None, repr=False)
    timeout_s: float = 5.0

    def reset(self) -> None:
        pass

    def fetch_thing_description(self) -> dict[str, Any]:
        result = self._request(self.thing_description_url, "GET", None, None, None, effectful=False)
        if not result.transport_success or not isinstance(result.value, Mapping):
            raise RuntimeError(result.error_type or "thing_description_unavailable")
        return to_json_compatible(result.value)

    def probe_thing_revision(self) -> dict[str, Any]:
        return self.fetch_thing_description()

    def supports(self, route: WotAffordanceBinding) -> bool:
        return (
            urlsplit(route.href).scheme.lower() in {"http", "https"}
            and route.method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
            and route.content_type.lower().split(";", maxsplit=1)[0].strip() == "application/json"
        )

    def read_property(
        self,
        route: WotAffordanceBinding,
        scheme: SecurityScheme,
    ) -> WotTransportResult:
        return self._request(route.href, route.method, route, scheme, None, effectful=False)

    def execute_affordance(
        self,
        route: WotAffordanceBinding,
        scheme: SecurityScheme,
        parameters: dict[str, Any],
    ) -> WotTransportResult:
        if not self.supports(route):
            return WotTransportResult(WotTransportStatus.NOT_SENT, False, "unsupported_route")
        payload: object | None = parameters
        if route.primitive_action == "write_property":
            payload = parameters.get("value")
        return self._request(route.href, route.method, route, scheme, payload, effectful=True)

    def _request(
        self,
        url: str,
        method: str,
        route: WotAffordanceBinding | None,
        scheme: SecurityScheme | None,
        payload: object | None,
        *,
        effectful: bool,
    ) -> WotTransportResult:
        credential = self._credential(route, scheme)
        if scheme is not None and scheme.requires_credential and credential is None:
            return WotTransportResult(WotTransportStatus.NOT_SENT, False, "credential_unavailable")
        headers, query = build_auth(scheme, credential)
        request_url = _with_query(url, query)
        try:
            body = None if payload is None else json.dumps(payload).encode()
        except (TypeError, ValueError):
            return WotTransportResult(WotTransportStatus.NOT_SENT, False, "payload_not_json")
        if body is not None:
            headers = {**headers, "Content-Type": route.content_type if route else "application/json"}
        request = Request(request_url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                raw = response.read()
                try:
                    value = json.loads(raw) if raw else None
                except json.JSONDecodeError:
                    if not effectful:
                        return WotTransportResult(
                            WotTransportStatus.NOT_SENT,
                            False,
                            "invalid_json_response",
                        )
                    value = None
                return WotTransportResult(
                    WotTransportStatus.SENT,
                    True,
                    value=value,
                    evidence={"status_code": int(getattr(response, "status", 200))},
                )
        except HTTPError as exc:
            return WotTransportResult(
                WotTransportStatus.SENT,
                False,
                f"http_{exc.code}",
                evidence={"status_code": exc.code},
            )
        except (URLError, TimeoutError, socket.timeout) as exc:
            status = WotTransportStatus.SENT_UNKNOWN if effectful else WotTransportStatus.NOT_SENT
            return WotTransportResult(status, False, type(exc).__name__)
        except (TypeError, ValueError) as exc:
            return WotTransportResult(WotTransportStatus.NOT_SENT, False, type(exc).__name__)

    def _credential(
        self,
        route: WotAffordanceBinding | None,
        scheme: SecurityScheme | None,
    ) -> str | None:
        if route is None or scheme is None or not scheme.requires_credential:
            return None
        if self.credential_resolver is None:
            return None
        return self.credential_resolver.resolve(route.thing_id, route.security_scheme_ref)


def _with_query(url: str, query: Mapping[str, str]) -> str:
    if not query:
        return url
    parts = urlsplit(url)
    merged = "&".join(item for item in (parts.query, urlencode(query)) if item)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, merged, parts.fragment))

"""Bounded asynchronous transport for registered HTTP JSON state sources."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.request import Request, urlopen


class HttpJsonTransportPort(Protocol):
    async def fetch_json(self, endpoint: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class UrllibHttpJsonTransport:
    timeout_s: float = 5.0
    max_response_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        if not 0 < self.timeout_s <= 30 or not 1 <= self.max_response_bytes <= 8 * 1_048_576:
            raise ValueError("HTTP JSON transport bounds are invalid")

    async def fetch_json(self, endpoint: str) -> Mapping[str, Any]:
        return await asyncio.to_thread(self._fetch_json, endpoint)

    def _fetch_json(self, endpoint: str) -> Mapping[str, Any]:
        request = Request(endpoint, headers={"Accept": "application/json"})  # noqa: S310 - registered URL
        with urlopen(request, timeout=self.timeout_s) as response:  # noqa: S310 - registered URL
            content_type = response.headers.get_content_type()
            if content_type != "application/json":
                raise ValueError("registered HTTP state source did not return JSON")
            body = response.read(self.max_response_bytes + 1)
        if len(body) > self.max_response_bytes:
            raise ValueError("registered HTTP state response exceeds its bound")
        value = json.loads(
            body.decode("utf-8"),
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("registered HTTP state contains a non-finite number")
            ),
        )
        if not isinstance(value, Mapping):
            raise ValueError("registered HTTP state root must be a JSON object")
        return value

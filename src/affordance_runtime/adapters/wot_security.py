"""Pure WoT security and rate-limit contracts.

Credentials deliberately do not live in these parsed contracts.  A Thing
Description contributes only a security-scheme reference and public transport
metadata; the executor resolves the credential at the network boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

_WINDOW_SECONDS = {
    "s": 1,
    "sec": 1,
    "second": 1,
    "min": 60,
    "minute": 60,
    "h": 3_600,
    "hour": 3_600,
}
_RATE_RE = re.compile(r"^\s*(\d+)\s*/\s*([a-z]+)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class SecurityScheme:
    name: str
    scheme: str
    location: str = "header"
    field_name: str = "Authorization"

    @property
    def requires_credential(self) -> bool:
        return self.scheme != "nosec"


@dataclass(frozen=True)
class RateLimit:
    max_requests: int
    window_seconds: int

    def __post_init__(self) -> None:
        if self.max_requests < 0 or self.window_seconds <= 0:
            raise ValueError("rate limit requires non-negative requests and a positive window")

    @property
    def min_interval_ms(self) -> float:
        if self.max_requests == 0:
            return float("inf")
        return self.window_seconds * 1_000.0 / self.max_requests

    def to_public_dict(self) -> dict[str, int | float]:
        return {
            "max_requests": self.max_requests,
            "window_seconds": self.window_seconds,
            "min_interval_ms": self.min_interval_ms,
        }


def parse_rate_limit(raw: Any) -> RateLimit | None:
    """Parse common TD rate-limit extension shapes without side effects."""

    try:
        if isinstance(raw, str):
            match = _RATE_RE.match(raw)
            if match is None:
                return None
            count, unit = int(match.group(1)), match.group(2).lower()
            window = _WINDOW_SECONDS.get(unit) or _WINDOW_SECONDS.get(unit.rstrip("s"))
            return RateLimit(count, window) if window else None
        if isinstance(raw, Mapping):
            if "window_seconds" in raw and "max_requests" in raw:
                return RateLimit(int(raw["max_requests"]), int(raw["window_seconds"]))
            if "max" in raw and "window" in raw:
                unit = str(raw["window"]).lower()
                window = _WINDOW_SECONDS.get(unit) or _WINDOW_SECONDS.get(unit.rstrip("s"))
                return RateLimit(int(raw["max"]), window) if window else None
    except (TypeError, ValueError):
        return None
    return None


def parse_security_definitions(td: Mapping[str, Any]) -> dict[str, SecurityScheme]:
    schemes: dict[str, SecurityScheme] = {}
    definitions = td.get("securityDefinitions")
    if not isinstance(definitions, Mapping):
        return schemes
    for raw_name, raw_definition in definitions.items():
        if not isinstance(raw_definition, Mapping):
            continue
        name = str(raw_name)
        scheme = str(raw_definition.get("scheme") or "nosec").lower()
        location = str(raw_definition.get("in") or "header").lower()
        default_field = "Authorization" if location == "header" else "access_token"
        schemes[name] = SecurityScheme(
            name=name,
            scheme=scheme,
            location=location,
            field_name=str(raw_definition.get("name") or default_field),
        )
    return schemes


def active_security_ref(
    declaration: Any,
    schemes: Mapping[str, SecurityScheme],
    *,
    fallback: str = "",
) -> str:
    names = [declaration] if isinstance(declaration, str) else list(declaration or [])
    return next((str(name) for name in names if str(name) in schemes), fallback)


def build_auth(
    scheme: SecurityScheme | None,
    credential: str | None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Build ephemeral request auth; callers must not persist the result."""

    if scheme is None or not scheme.requires_credential or not credential:
        return {}, {}
    if scheme.scheme == "bearer":
        return {scheme.field_name: f"Bearer {credential}"}, {}
    if scheme.scheme == "basic":
        return {scheme.field_name: f"Basic {credential}"}, {}
    if scheme.scheme == "apikey" and scheme.location == "query":
        return {}, {scheme.field_name: credential}
    return {scheme.field_name: credential}, {}

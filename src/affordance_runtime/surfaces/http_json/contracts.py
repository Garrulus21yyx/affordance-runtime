"""Trusted registration and bounded projection contracts for HTTP JSON state."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeAlias
from urllib.parse import urlsplit

JsonPathSegment: TypeAlias = str | int

_PUBLIC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,239}$")
_PUBLIC_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


class HttpJsonAuthority(StrEnum):
    """Closed assertion that the configured endpoint owns the projected state."""

    REGISTERED_STATE_API = "registered_state_api"


@dataclass(frozen=True)
class HttpJsonFactProjection:
    subject_id: str
    role: str
    label: str
    predicate: str
    path: tuple[JsonPathSegment, ...]

    def __post_init__(self) -> None:
        if not _PUBLIC_ID.fullmatch(self.subject_id):
            raise ValueError("HTTP JSON projection requires a bounded public subject ID")
        if not self.role.strip() or len(self.role) > 120 or not self.label.strip() or len(self.label) > 240:
            raise ValueError("HTTP JSON projection requires a bounded role and label")
        if not _PUBLIC_NAME.fullmatch(self.predicate):
            raise ValueError("HTTP JSON projection requires a bounded public predicate")
        path = tuple(self.path)
        if not path or len(path) > 16:
            raise ValueError("HTTP JSON projection path must contain 1 to 16 segments")
        if any(
            type(segment) not in {str, int}
            or isinstance(segment, str) and (not segment.strip() or len(segment) > 120)
            or isinstance(segment, int) and segment < 0
            for segment in path
        ):
            raise ValueError("HTTP JSON projection path contains an unsupported segment")
        object.__setattr__(self, "path", path)


@dataclass(frozen=True)
class HttpJsonSourceRegistration:
    """Private endpoint plus explicit authority and public projection allowlist."""

    source_id: str
    endpoint: str = field(repr=False)
    projections: tuple[HttpJsonFactProjection, ...]
    authority: HttpJsonAuthority

    def __post_init__(self) -> None:
        if not _PUBLIC_NAME.fullmatch(self.source_id):
            raise ValueError("HTTP JSON registration requires a bounded source ID")
        parsed = urlsplit(self.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("HTTP JSON endpoint must be an HTTP(S) URL without embedded credentials")
        if parsed.fragment:
            raise ValueError("HTTP JSON endpoint cannot contain a fragment")
        projections = tuple(self.projections)
        if not projections or len(projections) > 256:
            raise ValueError("HTTP JSON registration requires 1 to 256 projections")
        keys = tuple((item.subject_id, item.predicate) for item in projections)
        if len(set(keys)) != len(keys):
            raise ValueError("HTTP JSON projections must have unique subject predicates")
        identities: dict[str, tuple[str, str]] = {}
        for projection in projections:
            prior = identities.setdefault(
                projection.subject_id,
                (projection.role, projection.label),
            )
            if prior != (projection.role, projection.label):
                raise ValueError("HTTP JSON subject role and label must be stable")
        if not isinstance(self.authority, HttpJsonAuthority):
            raise TypeError("HTTP JSON registration requires typed source authority")
        object.__setattr__(self, "projections", projections)


class HttpJsonProjectionErrorCode(StrEnum):
    MISSING_KEY = "missing_key"
    INDEX_OUT_OF_RANGE = "index_out_of_range"
    PATH_TYPE_MISMATCH = "path_type_mismatch"


@dataclass(frozen=True)
class HttpJsonProjectionError(ValueError):
    code: HttpJsonProjectionErrorCode
    path: tuple[JsonPathSegment, ...]

    def __str__(self) -> str:
        return f"HTTP JSON projection failed: {self.code.value}"

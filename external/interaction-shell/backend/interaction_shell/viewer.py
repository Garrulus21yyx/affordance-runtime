"""Optional deployment Viewer boundary without provider-specific imports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, Protocol, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictAvailabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SurfaceChannelUnavailable(_StrictAvailabilityModel):
    kind: Literal["unavailable"] = "unavailable"
    reason_code: str = Field(min_length=1, max_length=128)


class SurfaceChannelAvailable(_StrictAvailabilityModel):
    kind: Literal["available"] = "available"
    surface_kind: Literal["web", "mobile", "desktop", "generic"]
    presentation: Literal["live_media", "snapshot"]
    protected_path: str = Field(min_length=1, max_length=512)
    input_mode: Literal["native"] | None = None

    @field_validator("protected_path")
    @classmethod
    def require_secret_free_same_origin_path(cls, value: str) -> str:
        if not value.startswith("/") or any(marker in value for marker in ("?", "#", "://")):
            raise ValueError("surface path must be same-origin and secret-free")
        return value


SurfaceAvailability: TypeAlias = Annotated[
    SurfaceChannelUnavailable | SurfaceChannelAvailable,
    Field(discriminator="kind"),
]


@dataclass(frozen=True)
class ViewerHTTPResponse:
    status_code: int
    content: bytes
    content_type: str


class ViewerGateway(Protocol):
    async def document(
        self,
        session_id: str,
        *,
        interactive: bool = False,
    ) -> ViewerHTTPResponse: ...

    def input_websocket_url(self, session_id: str) -> str: ...

    async def ice_servers(self, session_id: str) -> ViewerHTTPResponse: ...

    async def whep(
        self,
        session_id: str,
        body: bytes,
        content_type: str,
        region: str,
    ) -> ViewerHTTPResponse: ...


class ViewerUnavailable(RuntimeError):
    def __init__(self, code: str, status_code: int = 502) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)

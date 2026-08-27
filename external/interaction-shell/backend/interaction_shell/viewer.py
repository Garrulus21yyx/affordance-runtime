"""Optional deployment Viewer boundary without provider-specific imports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ViewerHTTPResponse:
    status_code: int
    content: bytes
    content_type: str


class ViewerGateway(Protocol):
    async def document(self, session_id: str) -> ViewerHTTPResponse: ...

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

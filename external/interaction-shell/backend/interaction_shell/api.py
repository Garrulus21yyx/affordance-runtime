from __future__ import annotations

import asyncio
import hashlib
import inspect
import os
import secrets
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from ag_ui.core import CustomEvent
from ag_ui.encoder import EventEncoder
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, WebSocket
from fastapi.responses import HTMLResponse, StreamingResponse

from .contracts import (
    AnswerQuestion,
    ApproveAction,
    CloseSession,
    CommandAdmission,
    CreateSessionRequest,
    CreateSessionResponse,
    OptionalCommand,
    RecoverSessionRequest,
    RecoverSessionResponse,
    RejectAction,
    ResumeTask,
    ReturnControl,
    ReviseTask,
    RuntimeSessionSnapshot,
    ShellEvent,
    StartTask,
    TakeOver,
)
from .diagnosis import (
    BenchmarkResultExport,
    CaseDiagnosis,
    CaseDiagnosisProjector,
    PublicTraceExport,
)
from .manager import (
    RunSessionManager,
    SessionNotFound,
    SessionUnauthorized,
    ViewerInputRejected,
)
from .port import RuntimeSessionUnavailable
from .unavailable_port import UnavailableRuntimeSessionPort
from .viewer import ViewerGateway, ViewerUnavailable


class DiagnosisRequest(BenchmarkResultExport):
    trace: PublicTraceExport


def _event_position(value: str) -> tuple[str | None, int]:
    epoch, separator, raw_cursor = value.rpartition(":")
    if not separator:
        epoch, raw_cursor = "", value
    if not raw_cursor.isdecimal():
        raise ValueError("event position cursor must be a nonnegative integer")
    return (epoch or None), int(raw_cursor)


HealthProvider = Callable[[], Mapping[str, object] | Awaitable[Mapping[str, object]]]


def create_app(
    manager: RunSessionManager | None = None,
    *,
    health_provider: HealthProvider | None = None,
    viewer_gateway: ViewerGateway | None = None,
) -> FastAPI:
    shell = manager or RunSessionManager(UnavailableRuntimeSessionPort())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        await shell.close_all()

    app = FastAPI(title="Affordance Interaction Shell", version="0.1.0", lifespan=lifespan)
    app.state.manager = shell
    app.state.diagnoses = {}

    def key(value: Annotated[str | None, Header(alias="X-Session-Key")] = None) -> str:
        if not value:
            raise HTTPException(401, "missing session key")
        return value

    def map_auth(exc: Exception) -> HTTPException:
        return HTTPException(404 if isinstance(exc, SessionNotFound) else 403, "session unavailable")

    @app.get("/health")
    async def health() -> dict[str, object]:
        if health_provider is None:
            return {"status": "ok"}
        value = health_provider()
        if inspect.isawaitable(value):
            value = await value
        return dict(value)

    async def authorize_viewer(request: Request | WebSocket, session_id: str) -> RuntimeSessionSnapshot:
        session_key = request.cookies.get(_viewer_cookie_name(session_id))
        if not session_key:
            raise HTTPException(401, "missing viewer session")
        try:
            return await shell.snapshot(session_id, session_key)
        except (SessionNotFound, SessionUnauthorized) as exc:
            raise map_auth(exc) from exc

    if viewer_gateway is not None:

        @app.get("/viewer/{session_id}", response_class=HTMLResponse)
        async def viewer_document(request: Request, session_id: str) -> Response:
            snapshot = await authorize_viewer(request, session_id)
            try:
                document = await viewer_gateway.document(
                    session_id,
                    interactive=(
                        snapshot.control_owner.value == "user"
                        and snapshot.viewer.status == "available"
                        and not snapshot.viewer.read_only
                    ),
                )
            except ViewerUnavailable as exc:
                raise HTTPException(exc.status_code, exc.code) from exc
            return Response(
                content=document.content,
                status_code=document.status_code,
                media_type=document.content_type,
                headers=_viewer_security_headers(),
            )

        @app.websocket("/viewer/{session_id}/input")
        async def viewer_input(websocket: WebSocket, session_id: str) -> None:
            session_key = websocket.cookies.get(_viewer_cookie_name(session_id))
            try:
                snapshot = await authorize_viewer(websocket, session_id)
            except HTTPException as exc:
                await websocket.close(code=4401 if exc.status_code == 401 else 4403)
                return
            if (
                snapshot.control_owner.value != "user"
                or snapshot.viewer.status != "available"
                or snapshot.viewer.read_only
                or snapshot.control_lease_id is None
                or session_key is None
            ):
                await websocket.close(code=4409)
                return
            connected_lease_id = snapshot.control_lease_id
            try:
                upstream_url = viewer_gateway.input_websocket_url(session_id)
            except ViewerUnavailable:
                await websocket.close(code=4410)
                return
            await websocket.accept()
            try:
                from websockets.asyncio.client import connect
                from websockets.typing import Origin

                async with connect(
                    upstream_url,
                    origin=Origin("https://api.steel.dev"),
                    open_timeout=10,
                    close_timeout=5,
                    max_size=2 * 1024 * 1024,
                ) as upstream:

                    async def client_to_provider() -> None:
                        while True:
                            message = await websocket.receive()
                            if message["type"] == "websocket.disconnect":
                                return

                            async def forward(frame=message) -> None:
                                if frame.get("text") is not None:
                                    await upstream.send(frame["text"])
                                elif frame.get("bytes") is not None:
                                    await upstream.send(frame["bytes"])

                            try:
                                await shell.forward_viewer_input(
                                    session_id,
                                    session_key,
                                    connected_lease_id,
                                    forward,
                                )
                            except (SessionNotFound, SessionUnauthorized):
                                await websocket.close(code=4403)
                                return
                            except ViewerInputRejected:
                                await websocket.close(code=4409)
                                return

                    async def provider_to_client() -> None:
                        async for message in upstream:
                            if isinstance(message, str):
                                await websocket.send_text(message)
                            else:
                                await websocket.send_bytes(message)

                    tasks = {
                        asyncio.create_task(client_to_provider()),
                        asyncio.create_task(provider_to_client()),
                    }
                    done, pending = await asyncio.wait(
                        tasks,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    for task in done:
                        task.result()
            except Exception:  # noqa: BLE001 - never expose provider input locators
                try:
                    await websocket.close(code=1011)
                except RuntimeError:
                    pass

        @app.get("/viewer/{session_id}/steel/v1/rtc/ice-servers/{rtc_session_id}")
        async def viewer_ice_servers(
            request: Request,
            session_id: str,
            rtc_session_id: str,
        ) -> Response:
            await authorize_viewer(request, session_id)
            _require_same_viewer_session(session_id, rtc_session_id)
            try:
                upstream = await viewer_gateway.ice_servers(session_id)
            except ViewerUnavailable as exc:
                raise HTTPException(exc.status_code, exc.code) from exc
            if upstream.status_code != 200:
                raise HTTPException(502, "viewer_provider_unavailable")
            return Response(
                upstream.content,
                media_type=upstream.content_type,
                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
            )

        @app.post("/viewer/{session_id}/steel/v1/rtc/whep/{rtc_session_id}")
        async def viewer_whep(
            request: Request,
            session_id: str,
            rtc_session_id: str,
        ) -> Response:
            await authorize_viewer(request, session_id)
            _require_same_viewer_session(session_id, rtc_session_id)
            content_type = request.headers.get("content-type", "")
            if not content_type.lower().startswith("application/sdp"):
                raise HTTPException(415, "viewer_whep_requires_sdp")
            body = await request.body()
            if len(body) > 2 * 1024 * 1024:
                raise HTTPException(413, "viewer_request_too_large")
            region = request.query_params.get("region", "")
            try:
                upstream = await viewer_gateway.whep(
                    session_id,
                    body,
                    content_type,
                    region,
                )
            except ViewerUnavailable as exc:
                raise HTTPException(exc.status_code, exc.code) from exc
            if upstream.status_code not in {200, 201}:
                raise HTTPException(502, "viewer_provider_unavailable")
            return Response(
                upstream.content,
                status_code=upstream.status_code,
                media_type=upstream.content_type,
                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
            )

    @app.get("/schemas/shell-event", response_model=ShellEvent)
    async def shell_event_schema() -> ShellEvent:
        """Concrete versioned schema anchor used by OpenAPI TypeScript generation."""
        return ShellEvent(
            session_id="schema",
            event_epoch="schema-event-epoch",
            cursor=1,
            type="schema.example",
        )

    @app.get("/diagnostics", response_model=list[CaseDiagnosis])
    async def list_diagnostics():
        return list(app.state.diagnoses.values())

    @app.get("/diagnostics/{case_id}", response_model=CaseDiagnosis)
    async def get_diagnostic(case_id: str):
        if case_id not in app.state.diagnoses:
            raise HTTPException(404, "diagnosis not found")
        return app.state.diagnoses[case_id]

    @app.post("/diagnostics", response_model=CaseDiagnosis, status_code=201)
    async def project_diagnostic(body: DiagnosisRequest):
        result = BenchmarkResultExport.model_validate(body.model_dump(exclude={"trace"}))
        diagnosis = CaseDiagnosisProjector().project(result, body.trace)
        app.state.diagnoses[diagnosis.case_id] = diagnosis
        return diagnosis

    @app.post("/sessions", response_model=CreateSessionResponse, status_code=201)
    async def create_session(body: CreateSessionRequest, response: Response) -> CreateSessionResponse:
        try:
            created = await shell.create(body.ttl_seconds)
        except RuntimeSessionUnavailable as exc:
            raise HTTPException(503, exc.code) from exc
        if viewer_gateway is not None:
            _set_viewer_cookie(response, created)
        return created

    @app.post(
        "/sessions/{session_id}/recover",
        response_model=RecoverSessionResponse,
    )
    async def recover_session(
        session_id: str,
        body: RecoverSessionRequest,
        response: Response,
        session_key: str = Depends(key),
    ) -> RecoverSessionResponse:
        try:
            recovered = await shell.recover(
                session_id,
                session_key,
                body.checkpoint_id,
            )
        except (SessionNotFound, SessionUnauthorized) as exc:
            raise map_auth(exc) from exc
        except RuntimeSessionUnavailable as exc:
            status = 409 if exc.code in {
                "checkpoint_already_resumed",
                "checkpoint_mismatch",
            } else 503
            raise HTTPException(status, exc.code) from exc
        if viewer_gateway is not None:
            _set_viewer_cookie_from_values(
                response,
                session_id,
                session_key,
                recovered.snapshot.expires_at,
            )
        return recovered

    @app.get("/sessions/{session_id}", response_model=RuntimeSessionSnapshot)
    async def get_snapshot(session_id: str, session_key: str = Depends(key)):
        try:
            return await shell.snapshot(session_id, session_key)
        except (SessionNotFound, SessionUnauthorized) as exc:
            raise map_auth(exc) from exc

    @app.get("/sessions/{session_id}/events")
    async def subscribe_events(
        request: Request,
        session_id: str,
        session_key: str = Depends(key),
        cursor: int = 0,
        event_epoch: str | None = None,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ):
        try:
            requested_epoch, after = _event_position(last_event_id) if last_event_id else (event_epoch, cursor)
            snapshot = await shell.snapshot(session_id, session_key)
        except (SessionNotFound, SessionUnauthorized) as exc:
            raise map_auth(exc) from exc
        except ValueError as exc:
            raise HTTPException(400, "invalid event position") from exc
        if requested_epoch is not None and requested_epoch != snapshot.event_epoch:
            raise HTTPException(409, "event epoch mismatch; snapshot resync required")

        async def stream():
            current = after
            idle = 0
            encoder = EventEncoder("text/event-stream")
            while not await request.is_disconnected():
                events = await shell.events(session_id, session_key, current)
                if events:
                    idle = 0
                    for event in events:
                        current = event.cursor
                        agui = CustomEvent(
                            name=event.type,
                            value=event.model_dump(mode="json"),
                        )
                        yield (
                            f"id: {event.event_epoch}:{event.cursor}\n"
                            f"event: {event.type}\n{encoder.encode(agui)}"
                        )
                else:
                    idle += 1
                    if idle >= 15:
                        yield ": keepalive\n\n"
                        idle = 0
                await asyncio.sleep(0.1)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Content-Encoding": "identity",
                "X-Accel-Buffering": "no",
            },
        )

    async def command(session_id: str, session_key: str, body):
        try:
            return await shell.admit(session_id, session_key, body)
        except (SessionNotFound, SessionUnauthorized) as exc:
            raise map_auth(exc) from exc
        except RuntimeSessionUnavailable as exc:
            raise HTTPException(503, exc.code) from exc

    @app.post("/sessions/{session_id}/tasks", response_model=CommandAdmission)
    async def start(session_id: str, body: StartTask, session_key: str = Depends(key)):
        return await command(session_id, session_key, body)

    @app.post("/sessions/{session_id}/commands/answer", response_model=CommandAdmission)
    async def answer(session_id: str, body: AnswerQuestion, session_key: str = Depends(key)):
        return await command(session_id, session_key, body)

    @app.post("/sessions/{session_id}/commands/approve", response_model=CommandAdmission)
    async def approve(session_id: str, body: ApproveAction, session_key: str = Depends(key)):
        return await command(session_id, session_key, body)

    @app.post("/sessions/{session_id}/commands/reject", response_model=CommandAdmission)
    async def reject(session_id: str, body: RejectAction, session_key: str = Depends(key)):
        return await command(session_id, session_key, body)

    @app.post("/sessions/{session_id}/commands/resume", response_model=CommandAdmission)
    async def resume(session_id: str, body: ResumeTask, session_key: str = Depends(key)):
        return await command(session_id, session_key, body)

    @app.post("/sessions/{session_id}/commands/revise", response_model=CommandAdmission)
    async def revise(session_id: str, body: ReviseTask, session_key: str = Depends(key)):
        return await command(session_id, session_key, body)

    @app.post("/sessions/{session_id}/commands/takeover", response_model=CommandAdmission)
    async def take_over(session_id: str, body: TakeOver, session_key: str = Depends(key)):
        return await command(session_id, session_key, body)

    @app.post("/sessions/{session_id}/commands/return-control", response_model=CommandAdmission)
    async def return_control(
        session_id: str,
        body: ReturnControl,
        session_key: str = Depends(key),
    ):
        return await command(session_id, session_key, body)

    @app.post("/sessions/{session_id}/commands/close", response_model=CommandAdmission)
    async def close(session_id: str, body: CloseSession, session_key: str = Depends(key)):
        return await command(session_id, session_key, body)

    @app.post("/sessions/{session_id}/commands/optional", response_model=CommandAdmission)
    async def optional(session_id: str, body: OptionalCommand, session_key: str = Depends(key)):
        return await command(session_id, session_key, body)

    return app


def _viewer_cookie_name(session_id: str) -> str:
    digest = hashlib.sha256(session_id.encode()).hexdigest()[:20]
    return f"interaction_shell_viewer_{digest}"


def _set_viewer_cookie(response: Response, created: CreateSessionResponse) -> None:
    _set_viewer_cookie_from_values(
        response,
        created.snapshot.session_id,
        created.session_key,
        created.snapshot.expires_at,
    )


def _set_viewer_cookie_from_values(
    response: Response,
    session_id: str,
    session_key: str,
    expires_at: datetime,
) -> None:
    remaining = max(0, int((expires_at - datetime.now(expires_at.tzinfo)).total_seconds()))
    response.set_cookie(
        _viewer_cookie_name(session_id),
        session_key,
        max_age=remaining,
        expires=expires_at,
        path=f"/viewer/{session_id}",
        secure=os.getenv("INTERACTION_SHELL_SECURE_COOKIES", "").lower() == "true",
        httponly=True,
        samesite="strict",
    )


def _require_same_viewer_session(session_id: str, rtc_session_id: str) -> None:
    if not secrets.compare_digest(session_id, rtc_session_id):
        raise HTTPException(404, "viewer session unavailable")


def _viewer_security_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "Content-Security-Policy": (
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "connect-src 'self' stun: turn: turns:; img-src data:; media-src blob:; "
            "frame-ancestors 'self'"
        ),
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
    }


if os.getenv("INTERACTION_SHELL_DEMO", "").lower() == "true":
    from .demo_port import ContractDemoPort

    app = create_app(RunSessionManager(ContractDemoPort()))
else:
    app = create_app()

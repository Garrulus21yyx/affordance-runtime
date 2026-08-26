from __future__ import annotations

import asyncio
import os
from typing import Annotated

from ag_ui.core import CustomEvent
from ag_ui.encoder import EventEncoder
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from .contracts import (
    AnswerQuestion,
    ApproveAction,
    CloseSession,
    CommandAdmission,
    CreateSessionRequest,
    CreateSessionResponse,
    OptionalCommand,
    RejectAction,
    RuntimeSessionSnapshot,
    ShellEvent,
    StartTask,
)
from .diagnosis import (
    BenchmarkResultExport,
    CaseDiagnosis,
    CaseDiagnosisProjector,
    PublicTraceExport,
)
from .manager import RunSessionManager, SessionNotFound, SessionUnauthorized
from .unavailable_port import UnavailableRuntimeSessionPort


class DiagnosisRequest(BenchmarkResultExport):
    trace: PublicTraceExport


def create_app(manager: RunSessionManager | None = None) -> FastAPI:
    shell = manager or RunSessionManager(UnavailableRuntimeSessionPort())
    app = FastAPI(title="Affordance Interaction Shell", version="0.1.0")
    app.state.manager = shell
    app.state.diagnoses = {}

    def key(value: Annotated[str | None, Header(alias="X-Session-Key")] = None) -> str:
        if not value:
            raise HTTPException(401, "missing session key")
        return value

    def map_auth(exc: Exception) -> HTTPException:
        return HTTPException(404 if isinstance(exc, SessionNotFound) else 403, "session unavailable")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/schemas/shell-event", response_model=ShellEvent)
    async def shell_event_schema() -> ShellEvent:
        """Concrete versioned schema anchor used by OpenAPI TypeScript generation."""
        return ShellEvent(session_id="schema", cursor=1, type="schema.example")

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
    async def create_session(body: CreateSessionRequest) -> CreateSessionResponse:
        return await shell.create(body.ttl_seconds)

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
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ):
        after = int(last_event_id) if last_event_id else cursor
        try:
            shell.authenticate(session_id, session_key)
        except (SessionNotFound, SessionUnauthorized) as exc:
            raise map_auth(exc) from exc

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
                        yield f"id: {event.cursor}\nevent: {event.type}\n{encoder.encode(agui)}"
                else:
                    idle += 1
                    if idle >= 15:
                        yield ": keepalive\n\n"
                        idle = 0
                await asyncio.sleep(0.1)

        return StreamingResponse(stream(), media_type="text/event-stream")

    async def command(session_id: str, session_key: str, body):
        try:
            return await shell.admit(session_id, session_key, body)
        except (SessionNotFound, SessionUnauthorized) as exc:
            raise map_auth(exc) from exc

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

    @app.post("/sessions/{session_id}/commands/close", response_model=CommandAdmission)
    async def close(session_id: str, body: CloseSession, session_key: str = Depends(key)):
        return await command(session_id, session_key, body)

    @app.post("/sessions/{session_id}/commands/optional", response_model=CommandAdmission)
    async def optional(session_id: str, body: OptionalCommand, session_key: str = Depends(key)):
        return await command(session_id, session_key, body)

    return app


if os.getenv("INTERACTION_SHELL_DEMO", "").lower() == "true":
    from .demo_port import ContractDemoPort

    app = create_app(RunSessionManager(ContractDemoPort()))
else:
    app = create_app()

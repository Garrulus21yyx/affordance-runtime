"""Opt-in no-model live witness for Steel takeover and return control.

Run with the BrowserGym Python after loading the main project ``.env``::

    PYTHONPATH=src:external/interaction-shell/backend \
      /home/yang/.venvs/affordance-browsergym-py312/bin/python \
      scripts/phase8_steel_takeover_witness.py

The witness creates one short-lived Steel lease. It never logs provider
credentials or locators, never calls a model, and never runs a benchmark.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx
import uvicorn
from interaction_shell.api import create_app
from interaction_shell.core_runtime_port import CoreRuntimeSessionPort
from interaction_shell.manager import RunSessionManager
from interaction_shell.steel_viewer import SteelViewerGateway, _cdp_endpoint
from playwright.async_api import async_playwright
from websockets.asyncio.client import connect

from affordance_runtime.agent import AskUser
from affordance_runtime.app import (
    RuntimeEnvironmentLease,
    SQLiteRuntimeCheckpointStore,
    TargetRuntimeSession,
    compose_target_runtime,
)
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.world import (
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)

_TTL_SECONDS = 180


class _UnusedActionOutcomeProjector:
    async def evaluate(
        self,
        task,
        before,
        request,
        result,
        after,
        public_world_delta,
    ) -> None:
        del task, before, request, result, after, public_world_delta
        raise AssertionError("live takeover witness must not dispatch an Agent action")


@dataclass
class _SettledAskPolicy:
    calls: int = 0
    active_task_identity: tuple[str, int] | None = None

    def bind_checkpoint_history_identity(
        self,
        *,
        task_id: str,
        task_revision: int,
    ) -> None:
        identity = (task_id, task_revision)
        if self.active_task_identity not in {None, identity}:
            raise ValueError("history identity mismatch")
        self.active_task_identity = identity

    async def decide(self, context):
        self.calls += 1
        self.active_task_identity = (
            context.task.task_id,
            context.goal_plan.task_revision,
        )
        return AskUser(
            context.context_id,
            "Take control and activate the page",
            ("manual_control",),
        )

    def export_checkpoint_history(self) -> dict[str, object]:
        return {
            "format": "pydantic-ai.messages.v1",
            "messages": [],
            "active_task_identity": list(self.active_task_identity or ()),
        }


class _ClickEvaluator:
    async def evaluate(self, task, observation) -> TaskEvaluation:
        clicked = next(
            (fact for fact in observation.facts if fact.subject_id == "page" and fact.predicate == "clicked"),
            None,
        )
        complete = clicked is not None and clicked.value is True
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            (TaskEvaluationStatus.COMPLETE if complete else TaskEvaluationStatus.INCOMPLETE),
            "same Steel page reports whether manual input activated the target",
            completion_evidence_refs=((clicked.fact_id,) if complete else ()),
        )


class _SteelPageEnvironment:
    """Acquire a production-shaped World from the same live Steel page."""

    def __init__(self, page) -> None:
        self._page = page
        self._task = None
        self._serial = 0
        self._inner = ScriptedEnvironment(initial_observation=self._world(False))
        self.capture_calls = 0

    def _world(self, clicked: bool):
        self._serial += 1
        observation_id = f"observation:steel-takeover:{self._serial}"
        target = SemanticTarget(
            "page",
            "document",
            "Steel takeover witness page",
        )
        fact = StateFact(
            f"fact:steel-takeover:clicked:{self._serial}",
            "page",
            "clicked",
            clicked,
            observation_id,
        )
        source = SurfaceObservation(
            observation_id,
            "steel-live",
            f"revision:{observation_id}",
            ObservationSourceProfile.dom(),
            (target,),
            (fact,),
            (),
            CoverageState.COMPLETE,
        )
        fused = WorldFusion().fuse((source,))
        if fused.observation is None:
            raise RuntimeError(fused.reason_code)
        return fused.observation

    @property
    def final_response_codec(self):
        return self._inner.final_response_codec

    @property
    def observation_capabilities(self):
        return self._inner.observation_capabilities

    async def reset(self, task):
        self._task = task
        clicked = bool(await self._page.evaluate("window.__phase8Clicked === true"))
        self._inner = ScriptedEnvironment(initial_observation=self._world(clicked))
        return await self._inner.reset(task)

    async def revise_task(self, task) -> None:
        self._task = task
        await self._inner.revise_task(task)

    async def capture(self, request):
        if self._task is None:
            raise RuntimeError("Steel witness environment is not initialized")
        clicked = bool(await self._page.evaluate("window.__phase8Clicked === true"))
        world = self._world(clicked)
        fresh = ScriptedEnvironment(
            initial_observation=world,
            independent_observations=(world,),
        )
        await fresh.reset(self._task)
        acquisition = await fresh.capture(request)
        self._inner = fresh
        self.capture_calls += 1
        return acquisition

    def is_current(self, request):
        return self._inner.is_current(request)

    async def execute(self, request):
        del request
        raise AssertionError("live takeover witness must not dispatch an Agent action")


class _LiveFactory:
    def __init__(self, gateway: SteelViewerGateway, store) -> None:
        self.gateway = gateway
        self.store = store
        self.policy = _SettledAskPolicy()
        self.lease = None
        self.page = None
        self.environment = None
        self.cleanup_calls = 0

    async def open(self, session_id, expires_at):
        lease = await self.gateway.open(session_id, expires_at)
        playwright = await async_playwright().start()
        browser = None
        cleaned = False
        try:
            browser = await playwright.chromium.connect_over_cdp(_cdp_endpoint(lease.websocket_url, _viewer_key()))
            if len(browser.contexts) != 1:
                raise RuntimeError("Steel witness requires exactly one browser context")
            context = browser.contexts[0]
            if len(context.pages) > 1:
                raise RuntimeError("Steel witness requires at most one initial page")
            page = context.pages[0] if context.pages else await context.new_page()
            await page.set_viewport_size({"width": 1280, "height": 720})
            await page.set_content(
                """
                <!doctype html><html><head><style>
                html,body,#target{margin:0;width:100%;height:100%;}
                #target{border:0;font:48px sans-serif;background:#1677ff;color:white;}
                </style></head><body>
                <button id="target"
                  onclick="window.__phase8Clicked=true;this.textContent='activated'">
                  activate takeover witness
                </button>
                <script>window.__phase8Clicked=false;</script>
                </body></html>
                """
            )
            environment = _SteelPageEnvironment(page)
            runtime = compose_target_runtime(
                self.policy,
                _UnusedActionOutcomeProjector(),
                _ClickEvaluator(),
                goal_compiler=NotRequiredGoalCompiler("phase8_live_takeover_witness"),
            )

            async def cleanup() -> None:
                nonlocal cleaned
                if cleaned:
                    return
                cleaned = True
                self.cleanup_calls += 1
                try:
                    if browser is not None:
                        await browser.close()
                finally:
                    try:
                        await playwright.stop()
                    finally:
                        await self.gateway.release(lease)

            handle = TargetRuntimeSession(
                runtime,
                RuntimeEnvironmentLease(environment, cleanup),
                session_id,
                expires_at,
                checkpoint_store=self.store,
            )
            self.gateway.attach(handle, lease)
            self.lease = lease
            self.page = page
            self.environment = environment
            return handle
        except BaseException:
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass
            try:
                await playwright.stop()
            finally:
                await self.gateway.release(lease)
            raise

    async def recover(self, session_id, checkpoint_id, expires_at):
        del session_id, checkpoint_id, expires_at
        raise RuntimeError("live takeover witness does not exercise restart recovery")


async def _wait_snapshot(client, session_id, headers, expected, timeout=10.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        response = await client.get(f"/sessions/{session_id}", headers=headers)
        response.raise_for_status()
        snapshot = response.json()
        if snapshot["run_status"] == expected:
            return snapshot
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"session did not reach {expected}")
        await asyncio.sleep(0.05)


def _viewer_key() -> str:
    key = os.getenv("Viewer_API_KEY", "").strip() or os.getenv("STEEL_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Steel viewer credential is unavailable")
    return key


def _reserve_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def _run_witness(client, factory: _LiveFactory, store, port: int) -> None:
    created_response = await client.post(
        "/sessions",
        json={"ttl_seconds": _TTL_SECONDS},
    )
    created_response.raise_for_status()
    created = created_response.json()
    session_id = created["snapshot"]["session_id"]
    headers = {"X-Session-Key": created["session_key"]}

    start = await client.post(
        f"/sessions/{session_id}/tasks",
        headers=headers,
        json={
            "kind": "start_task",
            "command_id": "phase8:start",
            "expected_task_revision": 0,
            "expected_run_status": "idle",
            "task": "Let the user activate the target, then verify it",
        },
    )
    start.raise_for_status()
    waiting = await _wait_snapshot(client, session_id, headers, "waiting_user")
    _require(factory.policy.calls == 1, "policy must run once before takeover")

    paused_response = await client.post(
        f"/sessions/{session_id}/commands/optional",
        headers=headers,
        json={
            "kind": "pause_task",
            "command_id": "phase8:pause",
            "expected_task_revision": waiting["task_revision"],
            "expected_run_status": waiting["run_status"],
        },
    )
    paused_response.raise_for_status()
    paused = paused_response.json()["snapshot"]
    _require(
        paused["run_status"] == "paused" and bool(paused["checkpoint_id"]),
        "pause must publish a durable checkpoint",
    )

    takeover_response = await client.post(
        f"/sessions/{session_id}/commands/takeover",
        headers=headers,
        json={
            "kind": "take_over",
            "command_id": "phase8:takeover",
            "expected_task_revision": paused["task_revision"],
            "expected_run_status": paused["run_status"],
            "checkpoint_id": paused["checkpoint_id"],
        },
    )
    takeover_response.raise_for_status()
    controlled = takeover_response.json()["snapshot"]
    _require(
        controlled["control_owner"] == "user" and not controlled["viewer"]["read_only"],
        "Runtime must grant interactive user control",
    )

    viewer_response = await client.get(f"/viewer/{session_id}")
    viewer_response.raise_for_status()
    protected_document = viewer_response.text
    _require(
        not any(marker in protected_document for marker in ("connect.steel.dev", "api.steel.dev", _viewer_key())),
        "protected document must not expose provider locators",
    )

    cookie_header = "; ".join(f"{cookie.name}={cookie.value}" for cookie in client.cookies.jar)
    async with connect(
        f"ws://127.0.0.1:{port}/viewer/{session_id}/input",
        origin=f"http://127.0.0.1:{port}",
        additional_headers={"Cookie": cookie_header},
        open_timeout=15,
        close_timeout=5,
    ) as websocket:
        # Steel does not admit input until its first session-status frame. The
        # provider document naturally observes this before a person can click.
        provider_status = await asyncio.wait_for(websocket.recv(), timeout=10)
        status_payload = json.loads(provider_status)
        _require(
            isinstance(status_payload, dict) and status_payload.get("type") in {"connected", "welcome"},
            "Steel input channel did not publish its ready status",
        )
        await websocket.send(
            json.dumps(
                {
                    "type": "mouseEvent",
                    "event": {
                        "action": "click",
                        "x": 640,
                        "y": 360,
                        "button": "left",
                        "modifiers": 0,
                    },
                },
                separators=(",", ":"),
            )
        )
        deadline = asyncio.get_running_loop().time() + 10
        while not bool(await factory.page.evaluate("window.__phase8Clicked === true")):
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("native Steel input did not activate the same page")
            await asyncio.sleep(0.05)

        returned_response = await client.post(
            f"/sessions/{session_id}/commands/return-control",
            headers=headers,
            json={
                "kind": "return_control",
                "command_id": "phase8:return",
                "expected_task_revision": controlled["task_revision"],
                "expected_run_status": controlled["run_status"],
                "control_lease_id": controlled["control_lease_id"],
            },
        )
        returned_response.raise_for_status()
        returned = returned_response.json()["snapshot"]

    consumed = await store.checkpoint_resume_outcome(
        session_id,
        paused["checkpoint_id"],
    )
    _require(
        returned["run_status"] == "done" and returned["control_owner"] == "agent",
        "return must complete from the fresh post-user World",
    )
    _require(
        factory.policy.calls == 1,
        "terminal fresh evaluation must precede a second policy call",
    )
    _require(
        factory.environment.capture_calls == 1,
        "return must capture exactly one fresh World",
    )
    _require(
        consumed is not None and consumed.command_id == "phase8:takeover",
        "takeover must consume the exact paused checkpoint",
    )

    print("phase8_live_witness passed")
    print(f"start_boundary {waiting['run_status']}")
    print(f"durable_pause {paused['run_status']} {bool(paused['checkpoint_id'])}")
    print(f"control_owner_during_input {controlled['control_owner']}")
    print("same_steel_page_changed True")
    print(f"return_status {returned['run_status']}")
    print(f"return_control_owner {returned['control_owner']}")
    print(f"fresh_world_captures {factory.environment.capture_calls}")
    print(f"action_policy_calls {factory.policy.calls}")
    print("checkpoint_consumed_by_takeover True")
    print("provider_locators_public False")


async def main() -> None:
    _viewer_key()
    os.environ["INTERACTION_SHELL_SECURE_COOKIES"] = "false"
    with tempfile.TemporaryDirectory(prefix="phase8-takeover-") as directory:
        gateway = SteelViewerGateway(_viewer_key())
        store = SQLiteRuntimeCheckpointStore(Path(directory) / "checkpoints.sqlite3")
        factory = _LiveFactory(gateway, store)
        manager = RunSessionManager(CoreRuntimeSessionPort(factory, gateway.project))
        app = create_app(manager, viewer_gateway=gateway)
        port = _reserve_port()
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                log_level="error",
                access_log=False,
            )
        )
        server_task = asyncio.create_task(server.serve())
        try:
            deadline = asyncio.get_running_loop().time() + 10
            while not server.started:
                if server_task.done():
                    await server_task
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError("witness API did not start")
                await asyncio.sleep(0.05)
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}",
                timeout=20,
            ) as client:
                await _run_witness(client, factory, store, port)
            deadline = asyncio.get_running_loop().time() + 10
            while factory.lease is not None and not factory.lease.released:
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError("Steel lease was not released")
                await asyncio.sleep(0.05)
            print(f"cleanup_calls {factory.cleanup_calls}")
            print(f"steel_lease_released {bool(factory.lease and factory.lease.released)}")
        finally:
            await manager.close_all()
            server.should_exit = True
            await asyncio.wait_for(server_task, timeout=15)


if __name__ == "__main__":
    asyncio.run(main())

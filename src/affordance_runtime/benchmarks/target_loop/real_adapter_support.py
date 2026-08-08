"""Real production-adapter compositions for the fixed internal harness."""

from __future__ import annotations

import json
import queue
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from typing import cast
from urllib.parse import quote

from PIL import Image

from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.evaluation import CriterionEvaluationStatus
from affordance_runtime.evaluation.semantic_contracts import SemanticCriterionProposal
from affordance_runtime.execution import ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.surfaces.base import SurfaceAdapter
from affordance_runtime.surfaces.dom import DomSurfaceAdapter
from affordance_runtime.surfaces.visual import VisualSurfaceAdapter
from affordance_runtime.surfaces.wot import WotDeploymentScope
from affordance_runtime.surfaces.wot.adapter import WotSurfaceAdapter
from affordance_runtime.surfaces.wot.transport import HttpWotTransport
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.visual_grounding import VisualRegion
from affordance_runtime.world import WorldObservation
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment

_DOM_HTML = """
<!doctype html><html><body><main>
  <button id="shared" aria-expanded="false"
    onclick="this.setAttribute('aria-expanded', 'true')">Enable shared state</button>
</main></body></html>
"""

_VISUAL_HTML = """
<!doctype html><html><body style="margin:0;background:white">
  <button id="shared" aria-expanded="false" style="position:absolute;left:160px;top:120px;
    width:240px;height:100px;border:0;background:rgb(220,40,60);color:white"
    onclick="this.style.background='rgb(35, 180, 80)';this.setAttribute('aria-expanded','true')">
    Enable shared state
  </button>
</body></html>
"""


@dataclass
class ManagedRealEnvironment:
    inner: UnifiedWorldEnvironment
    close_callback: object
    instrumentation: BenchmarkInstrumentation
    wot_state: WotFixtureState | None = None
    _closed: bool = field(default=False, init=False)

    async def reset(self, task: TaskGoal) -> None:
        return await self.inner.reset(task)

    async def observe(self, reason: str) -> WorldObservation:
        return await self.inner.observe(reason)

    async def execute(self, request: BoundActionRequest) -> ActionResult:
        return await self.inner.execute(request)

    def is_current(self, request: BoundActionRequest) -> bool:
        return self.inner.is_current(request)

    async def close(self):
        if self._closed:
            return
        self._closed = True
        if self.wot_state is not None:
            self.instrumentation.custom_metrics.update({
                "td_requests": self.wot_state.td_calls,
                "property_reads": self.wot_state.property_calls,
                "wot_action_calls": self.wot_state.action_calls,
            })
        self.close_callback()


@dataclass
class CountingAdapter:
    wrapped: SurfaceAdapter
    instrumentation: BenchmarkInstrumentation
    dispatch_metric: str

    @property
    def surface(self) -> str:
        return self.wrapped.surface

    async def reset(self, task: TaskGoal) -> None:
        return await self.wrapped.reset(task)

    async def observe(self, reason: str):
        return await self.wrapped.observe(reason)

    def is_current(self, request: BoundActionRequest) -> bool:
        return self.wrapped.is_current(request)

    async def execute(self, request: BoundActionRequest) -> ActionResult:
        result = await self.wrapped.execute(request)
        if result.dispatch_status != DispatchStatus.NOT_SENT:
            self.instrumentation.increment(self.dispatch_metric)
        return result


class ScreenshotOnlySharedStateProposer:
    provider = "internal-fixture"
    model = "pixel-segmentation"
    prompt_version = "visual-only-v1"
    acquisition_exhaustive = True

    def __init__(self, instrumentation: BenchmarkInstrumentation) -> None:
        self.instrumentation = instrumentation

    def propose(self, request):
        self.instrumentation.increment("visual_proposer_calls")
        image = Image.open(BytesIO(request.image_bytes)).convert("RGB")
        pixels = image.load()
        matches = [
            (x, y, pixels[x, y])
            for y in range(image.height)
            for x in range(image.width)
            if pixels[x, y] in {(220, 40, 60), (35, 180, 80)}
        ]
        if not matches:
            raise ValueError("visual fixture could not locate its rendered semantic region")
        xs, ys = [item[0] for item in matches], [item[1] for item in matches]
        checked = matches[len(matches) // 2][2] == (35, 180, 80)
        box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
        return [VisualRegion(
            (box[0] / image.width, box[1] / image.height,
             (box[2] - box[0]) / image.width, (box[3] - box[1]) / image.height),
            "Shared state", 1.0, True, "button", "point_activate", {"expanded": checked},
        )]


@dataclass
class WotFixtureState:
    expanded: bool = False
    td_calls: int = 0
    property_calls: int = 0
    action_calls: int = 0


class ThreadBoundBrowserSession:
    """Keep the existing synchronous BrowserSession on its owning thread."""

    def __init__(self, url: str) -> None:
        self._commands: queue.Queue[tuple[str, tuple, dict, Future] | None] = queue.Queue()
        self._ready: Future = Future()
        self._thread = threading.Thread(target=self._run, args=(url,), daemon=True)
        self._thread.start()
        self._ready.result(timeout=30)

    def _run(self, url: str) -> None:
        try:
            session = BrowserSession.launch(url, lease_ttl_ms=30_000)
            self._ready.set_result(True)
        except BaseException as exc:
            self._ready.set_exception(exc)
            return
        while (command := self._commands.get()) is not None:
            name, args, kwargs, outcome = command
            try:
                outcome.set_result(getattr(session, name)(*args, **kwargs))
            except BaseException as exc:
                outcome.set_exception(exc)
        session.close()

    def _call(self, name: str, *args, **kwargs):
        outcome: Future = Future()
        self._commands.put((name, args, kwargs, outcome))
        return outcome.result(timeout=30)

    def reset(self):
        return self._call("reset")

    def capture(self, **kwargs):
        return self._call("capture", **kwargs)

    def probe_dom_target(self, target_id):
        return self._call("probe_dom_target", target_id)

    def click(self, selector):
        return self._call("click", selector)

    def fill(self, selector, text):
        return self._call("fill", selector, text)

    def select_option(self, selector, value):
        return self._call("select_option", selector, value)

    def capture_visual_frame(self, observation_id):
        return self._call("capture_visual_frame", observation_id)

    def click_xy(self, x, y):
        return self._call("click_xy", x, y)

    def close(self) -> None:
        self._commands.put(None)
        self._thread.join(timeout=30)


def real_adapter_task() -> TaskGoal:
    return TaskGoal(
        "enable-real-shared", "Enable shared state", allowed_effects=("shared_state_enabled",),
        success_criteria=({"id": "expanded", "predicate": "expanded", "value": True},),
        risk_profile=RiskProfile.LOW,
    )


def real_visual_task() -> TaskGoal:
    return TaskGoal(
        "enable-real-visual", "Enable shared state", allowed_effects=("shared_state_enabled",),
        success_criteria=({
            "id": "expanded", "adjudicator": "semantic", "kind": "semantic_rubric",
            "rubric": "The shared-state visual control is expanded.",
            "evidence_scope_target_ids": ["region:0"],
        },),
        risk_profile=RiskProfile.LOW,
    )


class VisualStateCriterionJudge:
    async def evaluate(self, request):
        evidence = next(
            item for item in request.evidence_catalog.items
            if item.subject_id == "region:0" and item.predicate == "expanded"
        )
        status = (
            CriterionEvaluationStatus.SATISFIED
            if evidence.public_value is True
            else CriterionEvaluationStatus.UNSATISFIED
        )
        return (SemanticCriterionProposal(
            "expanded", status, (evidence.evidence_ref,), "visual state compared deterministically",
        ),)


def real_dom_environment(instrumentation: BenchmarkInstrumentation) -> WorldEnvironment:
    session = ThreadBoundBrowserSession("data:text/html," + quote(_DOM_HTML))
    adapter = CountingAdapter(
        DomSurfaceAdapter(cast(BrowserSession, session)), instrumentation, "dom_click_calls",
    )
    return ManagedRealEnvironment(
        UnifiedWorldEnvironment((cast(SurfaceAdapter, adapter),)), session.close, instrumentation,
    )


def real_visual_environment(instrumentation: BenchmarkInstrumentation) -> WorldEnvironment:
    session = ThreadBoundBrowserSession("data:text/html," + quote(_VISUAL_HTML))
    proposer = ScreenshotOnlySharedStateProposer(instrumentation)
    adapter = CountingAdapter(
        VisualSurfaceAdapter(cast(BrowserSession, session), proposer), instrumentation, "pointer_calls",
    )
    return ManagedRealEnvironment(
        UnifiedWorldEnvironment((cast(SurfaceAdapter, adapter),)), session.close, instrumentation,
    )


def real_wot_environment(instrumentation: BenchmarkInstrumentation) -> WorldEnvironment:
    state, server, thread = _start_wot_server()
    td_url = f"http://127.0.0.1:{server.server_address[1]}/td"
    adapter = CountingAdapter(
        WotSurfaceAdapter(
            HttpWotTransport(td_url), deployment_scope=WotDeploymentScope.LOCAL_SIMULATION,
        ),
        instrumentation,
        "wot_action_calls",
    )

    def close() -> None:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    return ManagedRealEnvironment(
        UnifiedWorldEnvironment((cast(SurfaceAdapter, adapter),)), close, instrumentation, state,
    )


def _start_wot_server() -> tuple[WotFixtureState, ThreadingHTTPServer, threading.Thread]:
    state = WotFixtureState()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/td":
                state.td_calls += 1
                return self._json(_thing_description(self.server.server_address[1]))
            if self.path == "/properties/expanded":
                state.property_calls += 1
                return self._json(state.expanded)
            self.send_error(404)

        def do_POST(self):  # noqa: N802
            if self.path == "/actions/enable":
                state.action_calls += 1
                state.expanded = True
                return self._json({"enabled": True})
            self.send_error(404)

        def _json(self, value):
            body = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return state, server, thread


def _thing_description(port: int) -> dict[str, object]:
    return {
        "id": "shared-state", "title": "Shared State", "base": f"http://127.0.0.1:{port}",
        "securityDefinitions": {"public": {"scheme": "nosec"}}, "security": "public",
        "properties": {"expanded": {
            "type": "boolean", "readOnly": True,
            "forms": [{"href": "/properties/expanded", "op": "readproperty"}],
        }},
        "actions": {"enable": {
            "forms": [{"href": "/actions/enable", "op": "invokeaction"}],
        }},
    }

from io import BytesIO
from urllib.parse import quote

from PIL import Image

from affordance_runtime.agent import AgentLoop, AgentLoopStatus
from affordance_runtime.evaluation import TaskEvaluationStatus
from affordance_runtime.surfaces.dom.browser_session import BrowserSession
from affordance_runtime.surfaces.visual import VisualSurfaceAdapter
from affordance_runtime.surfaces.visual.grounding import VisualGroundingPoint, VisualRegion
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment
from tests.support.agent.target_agent_loop_support import (
    FirstOfferedActionPolicy,
    SharedStateActionEvaluator,
    SharedStateTaskEvaluator,
    run_immediate,
    shared_state_task,
)
from tests.support.model.model_policy_support import first_action_model_policy


class ScreenshotOnlySharedStateProposer:
    provider = "test"
    model = "pixel-segmentation"
    prompt_version = "visual-only-v1"

    def __init__(self) -> None:
        self.calls = 0

    def propose(self, request):
        self.calls += 1
        image = Image.open(BytesIO(request.image_bytes)).convert("RGB")
        pixels = image.load()
        matches = [
            (x, y, pixels[x, y])
            for y in range(image.height)
            for x in range(image.width)
            if pixels[x, y] in {(220, 40, 60), (35, 180, 80)}
        ]
        assert matches
        xs = [item[0] for item in matches]
        ys = [item[1] for item in matches]
        checked = matches[len(matches) // 2][2] == (35, 180, 80)
        left, top, right, bottom = min(xs), min(ys), max(xs) + 1, max(ys) + 1
        return [
            VisualRegion(
                (left / image.width, top / image.height, (right - left) / image.width, (bottom - top) / image.height),
                "Shared state",
                1.0,
                True,
                "button",
                "point_activate",
                {"expanded": checked},
            )
        ]


class ScreenshotOnlySharedStateGrounder:
    provider = "test"
    model = "pixel-center"
    prompt_version = "visual-point-v1"

    def ground(self, request):
        image = Image.open(BytesIO(request.image_bytes)).convert("RGB")
        pixels = image.load()
        matches = [
            (x, y)
            for y in range(image.height)
            for x in range(image.width)
            if pixels[x, y] in {(220, 40, 60), (35, 180, 80)}
        ]
        assert matches
        xs = [item[0] for item in matches]
        ys = [item[1] for item in matches]
        return VisualGroundingPoint(
            ((min(xs) + max(xs) + 1) / (2 * image.width),
             (min(ys) + max(ys) + 1) / (2 * image.height)),
            normalized=True,
        )


def test_real_browser_visual_only_short_loop_completes_with_one_semantic_action() -> None:
    html = """
    <!doctype html><html><body style="margin:0;background:white">
      <button id="shared" aria-expanded="false" style="position:absolute;left:160px;top:120px;
        width:240px;height:100px;border:0;background:rgb(220,40,60);color:white"
        onclick="this.style.background='rgb(35, 180, 80)';this.setAttribute('aria-expanded','true')">
        Enable shared state
      </button>
    </body></html>
    """
    session = BrowserSession.launch("data:text/html," + quote(html), lease_ttl_ms=30_000)
    try:
        proposer = ScreenshotOnlySharedStateProposer()
        environment = UnifiedWorldEnvironment((
            VisualSurfaceAdapter(session, proposer, ScreenshotOnlySharedStateGrounder()),
        ))
        task = shared_state_task()
        loop = AgentLoop(FirstOfferedActionPolicy(), SharedStateActionEvaluator(), SharedStateTaskEvaluator())

        result = run_immediate((loop).run(environment, task))

        assert result.status == AgentLoopStatus.DONE
        assert result.observation_count == 2
        assert result.execution_count == 1
        assert result.currentness_probe_count == 1
        assert len(result.control_transitions) == 1
        assert result.control_transitions[0].before_observation_id != result.control_transitions[0].after_observation_id
        assert result.control_transitions[0].task_evaluation.status == TaskEvaluationStatus.COMPLETE
        assert environment.adapters[0].surface == "visual"
        assert proposer.calls == 2
    finally:
        session.close()


def test_real_browser_visual_model_policy_completes_through_strict_structured_decision() -> None:
    html = """
    <!doctype html><html><body style="margin:0;background:white">
      <button id="shared" aria-expanded="false" style="position:absolute;left:160px;top:120px;
        width:240px;height:100px;border:0;background:rgb(220,40,60);color:white"
        onclick="this.style.background='rgb(35, 180, 80)';this.setAttribute('aria-expanded','true')">
        Enable shared state
      </button>
    </body></html>
    """
    session = BrowserSession.launch("data:text/html," + quote(html), lease_ttl_ms=30_000)
    try:
        proposer = ScreenshotOnlySharedStateProposer()
        environment = UnifiedWorldEnvironment((
            VisualSurfaceAdapter(session, proposer, ScreenshotOnlySharedStateGrounder()),
        ))
        policy = first_action_model_policy()
        loop = AgentLoop(policy, SharedStateActionEvaluator(), SharedStateTaskEvaluator())

        result = run_immediate((loop).run(environment, shared_state_task()))

        assert result.status == AgentLoopStatus.DONE
        assert result.execution_count == 1
        assert policy.port.calls == 1
        request = policy.port.requests[0].serialized_context
        assert "action_point" not in request and "screenshot_digest" not in request
    finally:
        session.close()

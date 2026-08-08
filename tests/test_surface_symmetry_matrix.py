from contextlib import contextmanager
from dataclasses import replace
from urllib.parse import quote

import pytest
from target_agent_loop_support import (
    FirstOfferedActionPolicy,
    SharedStateActionEvaluator,
    SharedStateTaskEvaluator,
    run_immediate,
    shared_state_task,
)
from test_visual_agent_loop_e2e import ScreenshotOnlySharedStateProposer
from test_wot_agent_loop_e2e import shared_state_server

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus
from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.confirmation import ConfirmationDecision, ConfirmationDecisionKind
from affordance_runtime.evaluation import TaskEvaluationStatus
from affordance_runtime.surfaces.dom import DomSurfaceAdapter
from affordance_runtime.surfaces.visual import VisualSurfaceAdapter
from affordance_runtime.surfaces.wot import WotDeploymentScope
from affordance_runtime.surfaces.wot.adapter import WotSurfaceAdapter
from affordance_runtime.surfaces.wot.transport import HttpWotTransport
from affordance_runtime.task import RiskProfile
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


class CountingSession:
    def __init__(self, session: BrowserSession) -> None:
        self.session = session
        self.dom_clicks = 0
        self.pointer_clicks = 0
        self.dom_probes = 0
        self.selectors = []
        self.points = []

    def __getattr__(self, name):
        return getattr(self.session, name)

    def probe_dom_target(self, source_target_id):
        self.dom_probes += 1
        return self.session.probe_dom_target(source_target_id)

    def click(self, selector):
        self.dom_clicks += 1
        self.selectors.append(selector)
        return self.session.click(selector)

    def click_xy(self, x, y):
        self.pointer_clicks += 1
        self.points.append((x, y))
        return self.session.click_xy(x, y)


@contextmanager
def profile_environment(profile: str):
    if profile == "wot":
        with shared_state_server() as (fixture, td_url):
            environment = UnifiedWorldEnvironment(
                (
                    WotSurfaceAdapter(
                        HttpWotTransport(td_url),
                        deployment_scope=WotDeploymentScope.LOCAL_SIMULATION,
                    ),
                )
            )
            yield environment, {
                "actions": lambda: fixture.action_calls,
                "models": lambda: 0,
                "rebind": lambda: setattr(fixture, "action_path", "/actions/enable-current"),
                "private": lambda: fixture.action_path,
            }
        return

    html = _dom_html() if profile == "dom" else _visual_html()
    session = BrowserSession.launch("data:text/html," + quote(html), lease_ttl_ms=30_000)
    counted = CountingSession(session)
    try:
        if profile == "dom":
            environment = UnifiedWorldEnvironment((DomSurfaceAdapter(counted),))  # type: ignore[arg-type]
            metrics = {
                "actions": lambda: counted.dom_clicks,
                "models": lambda: 0,
                "rebind": lambda: counted.evaluate("document.querySelector('button').id='shared-current'"),
                "private": lambda: counted.selectors[-1],
            }
        else:
            proposer = ScreenshotOnlySharedStateProposer()
            environment = UnifiedWorldEnvironment(
                (VisualSurfaceAdapter(counted, proposer),)  # type: ignore[arg-type]
            )
            metrics = {
                "actions": lambda: counted.pointer_clicks,
                "models": lambda: proposer.calls,
                "rebind": lambda: counted.evaluate(
                    "const b=document.querySelector('button');b.style.left='260px';b.style.top='220px'"
                ),
                "private": lambda: counted.points[-1],
            }
        yield environment, metrics
    finally:
        session.close()


def _dom_html() -> str:
    return """
    <!doctype html><html><body><main>
      <button id="shared" aria-expanded="false"
        onclick="this.setAttribute('aria-expanded', 'true')">Enable shared state</button>
    </main></body></html>
    """


def _visual_html() -> str:
    return """
    <!doctype html><html><body style="margin:0;background:white">
      <button aria-expanded="false" style="position:absolute;left:160px;top:120px;
        width:240px;height:100px;border:0;background:rgb(220,40,60);color:white"
        onclick="this.style.background='rgb(35, 180, 80)';this.setAttribute('aria-expanded','true')">
        Enable shared state
      </button>
    </body></html>
    """


@pytest.mark.parametrize(
    ("profile", "expected_model_calls"),
    [("dom", 0), ("visual", 2), ("wot", 0)],
)
def test_dom_visual_wot_share_one_agent_contract_with_adapter_only_variation(
    profile: str,
    expected_model_calls: int,
) -> None:
    with profile_environment(profile) as (environment, metrics):
        task = shared_state_task()
        loop = AgentLoop(
            FirstOfferedActionPolicy(),
            SharedStateActionEvaluator(),
            SharedStateTaskEvaluator(),
        )

        result = run_immediate(AgentEpisodeRunner(loop).run(environment, task))

        assert result.status == AgentLoopStatus.DONE
        assert result.observation_count == 2
        assert result.execution_count == 1
        assert result.currentness_probe_count == 1
        assert len(result.turns) == 1
        assert result.turns[0].before_observation_id != result.turns[0].after_observation_id
        assert result.turns[0].task_evaluation.status == TaskEvaluationStatus.COMPLETE
        assert result.turns[0].action_evaluation is not None
        assert metrics["actions"]() == 1
        assert metrics["models"]() == expected_model_calls
        representation = repr(result.turns)
        assert all(private not in representation for private in ("selector", "action_point", "href", "credential"))


@pytest.mark.parametrize("profile", ["dom", "visual", "wot"])
def test_dom_visual_wot_confirmation_uses_fresh_private_binding(profile: str) -> None:
    with profile_environment(profile) as (environment, metrics):
        task = replace(shared_state_task(), risk_profile=RiskProfile.MEDIUM)
        runner = AgentEpisodeRunner(
            AgentLoop(
                FirstOfferedActionPolicy(),
                SharedStateActionEvaluator(),
                SharedStateTaskEvaluator(),
            )
        )
        session = run_immediate(runner.start(environment, task))
        paused = run_immediate(session.run_until_pause())

        assert paused.status == AgentLoopStatus.WAITING_CONFIRMATION
        assert paused.execution_count == 0
        confirmation = paused.confirmation_request
        assert confirmation is not None
        assert metrics["actions"]() == 0
        old_private_representation = repr(confirmation)

        metrics["rebind"]()
        decision = ConfirmationDecision(
            confirmation.confirmation_id,
            confirmation.subject_id,
            ConfirmationDecisionKind.CONFIRM,
        )
        result = run_immediate(session.resolve_confirmation(decision))

        assert result.status == AgentLoopStatus.DONE
        assert result.execution_count == 1
        assert metrics["actions"]() == 1
        assert metrics["private"]()
        assert all(
            private not in old_private_representation
            for private in ("selector", "action_point", "bbox", "href", "method", "credential")
        )

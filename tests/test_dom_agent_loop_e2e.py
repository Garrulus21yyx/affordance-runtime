from urllib.parse import quote

from target_agent_loop_support import (
    FirstOfferedActionPolicy,
    SharedStateActionEvaluator,
    SharedStateTaskEvaluator,
    run_immediate,
    shared_state_task,
)

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus
from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.evaluation import TaskEvaluationStatus
from affordance_runtime.surfaces.dom import DomSurfaceAdapter
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


def test_real_browser_dom_short_loop_completes_with_one_semantic_action() -> None:
    html = """
    <!doctype html><html><body><main>
      <button id="shared" aria-expanded="false"
        onclick="this.setAttribute('aria-expanded', 'true')">Enable shared state</button>
    </main></body></html>
    """
    session = BrowserSession.launch("data:text/html," + quote(html), lease_ttl_ms=30_000)
    try:
        environment = UnifiedWorldEnvironment((DomSurfaceAdapter(session),))
        task = shared_state_task()
        loop = AgentLoop(FirstOfferedActionPolicy(), SharedStateActionEvaluator(), SharedStateTaskEvaluator())

        result = run_immediate(AgentEpisodeRunner(loop).run(environment, task))

        assert result.status == AgentLoopStatus.DONE
        assert result.observation_count == 2
        assert result.execution_count == 1
        assert result.currentness_probe_count == 1
        assert len(result.turns) == 1
        assert result.turns[0].before_observation_id != result.turns[0].after_observation_id
        assert result.turns[0].task_evaluation.status == TaskEvaluationStatus.COMPLETE
    finally:
        session.close()

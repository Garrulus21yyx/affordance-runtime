from urllib.parse import quote

from model_policy_support import first_action_model_policy
from target_agent_loop_support import (
    FirstOfferedActionPolicy,
    SharedStateActionEvaluator,
    SharedStateTaskEvaluator,
    run_immediate,
    shared_state_task,
)

from affordance_runtime.agent import (
    AgentLoop,
    AgentLoopStatus,
)
from affordance_runtime.app import (
    compose_target_runtime,
)
from affordance_runtime.evaluation import (
    ProductionActionEvaluator,
    ProductionTaskEvaluator,
    TaskEvaluationStatus,
)
from affordance_runtime.surfaces.dom import DomSurfaceAdapter
from affordance_runtime.surfaces.dom.browser_session import BrowserSession
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

        result = run_immediate((loop).run(environment, task))

        assert result.status == AgentLoopStatus.DONE
        assert result.observation_count == 2
        assert result.execution_count == 1
        assert result.currentness_probe_count == 1
        assert len(result.turns) == 1
        assert result.turns[0].before_observation_id != result.turns[0].after_observation_id
        assert result.turns[0].task_evaluation.status == TaskEvaluationStatus.COMPLETE
    finally:
        session.close()


def test_real_browser_dom_model_policy_completes_through_strict_structured_decision() -> None:
    html = """
    <!doctype html><html><body><main>
      <button id="shared" aria-expanded="false"
        onclick="this.setAttribute('aria-expanded', 'true')">Enable shared state</button>
    </main></body></html>
    """
    session = BrowserSession.launch("data:text/html," + quote(html), lease_ttl_ms=30_000)
    try:
        environment = UnifiedWorldEnvironment((DomSurfaceAdapter(session),))
        policy = first_action_model_policy()
        loop = AgentLoop(policy, SharedStateActionEvaluator(), SharedStateTaskEvaluator())

        result = run_immediate((loop).run(environment, shared_state_task()))

        assert result.status == AgentLoopStatus.DONE
        assert result.execution_count == 1
        assert policy.port.calls == 1
        assert "selector" not in policy.port.requests[0].serialized_context
    finally:
        session.close()


def test_product_target_runtime_confirms_dom_activation_from_structural_evidence() -> None:
    html = """
    <!doctype html><html><body><main>
      <button id="shared" aria-expanded="false"
        onclick="this.setAttribute('aria-expanded', 'true')">Enable shared state</button>
    </main></body></html>
    """
    session = BrowserSession.launch("data:text/html," + quote(html), lease_ttl_ms=30_000)
    try:
        environment = UnifiedWorldEnvironment((DomSurfaceAdapter(session),))
        runtime = compose_target_runtime(
            FirstOfferedActionPolicy(),
            ProductionActionEvaluator(),
            ProductionTaskEvaluator(),
        )

        result = run_immediate(runtime.run_task(environment, shared_state_task()))

        assert result.status is AgentLoopStatus.DONE
        assert result.execution_count == 1
        assert result.turns[0].action_evaluation.status.value == "effect_confirmed"
        assert result.turns[0].action_evaluation.evidence["verification_profile"] == (
            "structural_target_diff_v1"
        )
        assert result.turns[0].action_evaluation.evidence_refs
    finally:
        session.close()

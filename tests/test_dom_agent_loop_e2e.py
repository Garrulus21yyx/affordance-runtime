from urllib.parse import quote

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus, SelectAction
from affordance_runtime.browser_session import BrowserSession
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.surfaces.dom import DomSurfaceAdapter
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


class FirstOfferedActionPolicy:
    async def decide(self, task, world, action_space, recent_turns, optional_plan):
        del task, recent_turns, optional_plan
        assert "selector" not in repr(world)
        return SelectAction(action_space.options[0].action_id)


class SharedStateTaskEvaluator:
    async def evaluate(self, task, observation):
        del task
        enabled = any(target.label == "Shared state enabled" for target in observation.targets)
        return TaskEvaluation(
            TaskEvaluationStatus.COMPLETE if enabled else TaskEvaluationStatus.INCOMPLETE,
            "shared state is enabled" if enabled else "shared state remains disabled",
        )


class LabelChangeActionEvaluator:
    async def evaluate(self, task, before, intent, result, after):
        del task, intent, result
        before_labels = {target.label for target in before.targets}
        after_labels = {target.label for target in after.targets}
        changed = before_labels != after_labels
        return ActionEvaluation(
            ActionEvaluationStatus.VERIFIED if changed else ActionEvaluationStatus.NOT_VERIFIED,
            "DOM label changed" if changed else "DOM label did not change",
        )


def _run_immediate(coroutine):
    """Drive the loop whose test adapters intentionally perform no async I/O."""

    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("real DOM test unexpectedly yielded asynchronous work")


def test_real_browser_dom_short_loop_completes_with_one_semantic_action() -> None:
    html = """
    <!doctype html><html><body><main>
      <button id="shared" onclick="this.textContent='Shared state enabled'">Enable shared state</button>
    </main></body></html>
    """
    session = BrowserSession.launch("data:text/html," + quote(html), lease_ttl_ms=30_000)
    try:
        environment = UnifiedWorldEnvironment((DomSurfaceAdapter(session),))
        task = TaskGoal(
            "enable-shared",
            "Enable shared state",
            allowed_effects=("shared_state_enabled",),
            success_criteria=({"target_id": "shared", "label": "Shared state enabled"},),
            risk_profile=RiskProfile.LOW,
        )
        loop = AgentLoop(FirstOfferedActionPolicy(), LabelChangeActionEvaluator(), SharedStateTaskEvaluator())

        result = _run_immediate(AgentEpisodeRunner(loop).run(environment, task))

        assert result.status == AgentLoopStatus.DONE
        assert result.observation_count == 2
        assert result.execution_count == 1
        assert len(result.turns) == 1
        assert result.turns[0].before_observation_id != result.turns[0].after_observation_id
        assert result.turns[0].task_evaluation.status == TaskEvaluationStatus.COMPLETE
    finally:
        session.close()

from __future__ import annotations

import asyncio
import os

import pytest

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus, SelectAction
from affordance_runtime.benchmarks.external_breadth.campaign_contracts import MiniWobTaskOutcome
from affordance_runtime.benchmarks.external_breadth.classification import classify_case
from affordance_runtime.benchmarks.external_smoke.browsergym_action_evaluator import (
    BrowserGymMechanicalActionEvaluator,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_environment import (
    BrowserGymMiniWobEnvironment,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_verifier import (
    verifier_snapshot_from_current_probe,
)
from affordance_runtime.benchmarks.external_smoke.environment import (
    ExternalEnvironmentTaskEvaluator,
    ExternalVerifierReason,
    ExternalVerifierStatus,
)
from affordance_runtime.benchmarks.target_loop.case_projection import project_case_result
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.evaluation import TaskEvaluationStatus, TaskOutcomeKind
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution import DispatchStatus
from affordance_runtime.world import ObservationRequestKind, WorldObservationRequest

pytestmark = pytest.mark.skipif(
    not os.environ.get("MINIWOB_URL"),
    reason="fixed MiniWoB source is unavailable",
)


class ActivateByLabelPolicy:
    def __init__(self, label: str = "") -> None:
        self.label = label.casefold()
        self.calls = 0

    async def decide(self, context):
        self.calls += 1
        targets = {item.target_id: item for item in context.world.targets}
        instruction = context.task.instruction.casefold()
        options = tuple(
            item for item in context.actions.options
            if item.semantic_action == "activate"
            and (
                self.label in targets[item.target_id].label.casefold()
                if self.label
                else bool(targets[item.target_id].label)
                and targets[item.target_id].label.casefold() in instruction
            )
        )
        assert options, "real witness omitted the expected public activation"
        return SelectAction(context.context_id, options[0].action_id)


def _open(task_id: str):
    return BrowserGymMiniWobEnvironment.open(
        task_id, 7, admitted_task_ids=frozenset({task_id}), max_turns=3,
    )


def test_real_login_user_popup_negative_terminal_is_canonical_and_absorbing() -> None:
    async def scenario() -> None:
        task_id = "browsergym/miniwob.login-user-popup"
        environment, task = _open(task_id)
        policy = ActivateByLabelPolicy("ok")
        loop = AgentLoop(
            policy,
            BrowserGymMechanicalActionEvaluator(),
            ExternalEnvironmentTaskEvaluator(task_id, environment),
        )
        try:
            session = await AgentEpisodeRunner(loop).start(environment, task)
            result = await session.run_until_pause()
            repeated = await session.run_until_pause()

            assert repeated is result
            assert result.status is AgentLoopStatus.BLOCKED
            assert result.runtime_failure is None
            assert result.task_outcome is not None
            assert result.task_outcome.kind is TaskOutcomeKind.TERMINAL_FAILURE
            assert result.task_outcome.code == "verified_terminal_task_failure"
            assert result.control_transition_total_count == 1
            transition = result.control_transitions[0]
            assert transition.execution is not None
            assert transition.execution.dispatch_status is DispatchStatus.SENT
            assert transition.task_evaluation is not None
            assert transition.task_evaluation.status is TaskEvaluationStatus.BLOCKED
            assert transition.task_evaluation.completion_evidence_refs == ()
            assert WorldEvidenceIndex.from_observation(result.final_observation).resolve(
                result.task_outcome.evidence_refs[0]
            )
            assert environment.step_calls == 1
            assert policy.calls == 1
            case = project_case_result(
                "login-user-popup-negative", result, BenchmarkInstrumentation(), 1.0, "",
            )
            classified = classify_case(case)
            assert classified.outcome is MiniWobTaskOutcome.TASK_FAILED
            assert classified.source == "canonical_task_outcome"
        finally:
            await environment.close()

    asyncio.run(scenario())


def test_real_success_reset_and_read_only_sources_keep_distinct_permissions() -> None:
    async def scenario() -> None:
        task_id = "browsergym/miniwob.click-button"
        environment, task = _open(task_id)
        evaluator = ExternalEnvironmentTaskEvaluator(task_id, environment)
        try:
            initial = await environment.reset(task)
            assert initial.observation is not None
            initial_evaluation = await evaluator.evaluate(task, initial.observation)
            assert initial_evaluation.status is TaskEvaluationStatus.INCOMPLETE
            assert initial_evaluation.outcome is not None
            assert initial_evaluation.outcome.kind is TaskOutcomeKind.RUNNING_INCOMPLETE

            captured = await environment.capture(WorldObservationRequest(
                ObservationRequestKind.CURRENTNESS_REFRESH,
                "read-only official verifier witness",
            ))
            assert captured.observation is not None
            captured_evaluation = await evaluator.evaluate(task, captured.observation)
            assert captured_evaluation.status is TaskEvaluationStatus.INCOMPLETE
            assert environment.step_calls == 0

        finally:
            await environment.close()

        success_environment, success_task = _open(task_id)
        success_policy = ActivateByLabelPolicy()
        try:
            result = await AgentEpisodeRunner(AgentLoop(
                success_policy,
                BrowserGymMechanicalActionEvaluator(),
                ExternalEnvironmentTaskEvaluator(task_id, success_environment),
            )).run(success_environment, success_task)
            assert result.status is AgentLoopStatus.DONE
            assert result.task_outcome is not None
            assert result.task_outcome.kind is TaskOutcomeKind.TERMINAL_SUCCESS
            assert result.runtime_failure is None
            assert success_environment.step_calls == 1
        finally:
            await success_environment.close()

    asyncio.run(scenario())


def test_pinned_malformed_read_only_probe_is_typed_unavailable() -> None:
    snapshot = verifier_snapshot_from_current_probe(
        task_run_id="run:pinned",
        observation_id="observation:pinned",
        source_observation_id="observation:pinned",
        probe={"ready": True, "done": True},
    )
    assert snapshot.status is ExternalVerifierStatus.UNAVAILABLE
    assert snapshot.reason is ExternalVerifierReason.MISSING_FACTS
    assert snapshot.evidence_refs == ()

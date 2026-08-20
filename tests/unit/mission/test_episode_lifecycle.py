from __future__ import annotations

import asyncio
from dataclasses import dataclass

from affordance_runtime.agent import YieldSubtask
from affordance_runtime.agent.decision_capability import DecisionCapability
from affordance_runtime.agent.run_state import RunStatus
from affordance_runtime.app import compose_target_runtime
from affordance_runtime.evaluation import ProductionActionOutcomeProjector, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.mission import (
    AuditorDecision,
    ManagerAssessment,
    ManagerDecision,
    ManagerRequestMode,
    ManagerRoute,
    MissionOutcome,
    MissionSupervisor,
    SubtaskContract,
)
from affordance_runtime.model.policy.contracts import ModelInvocationResult
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    FakeBrowserGym,
    ax_node,
    open_fake,
    raw_observation,
)


class UnknownEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.UNKNOWN,
            "native verifier not terminal",
        )


@dataclass
class YieldPolicy:
    kind: str = "outcome_proposed"

    @property
    def supported_decisions(self):
        return frozenset({DecisionCapability.YIELD_SUBTASK})

    async def decide(self, context):
        return YieldSubtask(context.context_id, self.kind, "episode boundary")


@dataclass
class ManagerScript:
    decisions: list[ManagerDecision]

    def __post_init__(self):
        self.requests = []

    async def decide(self, request):
        self.requests.append(request)
        return ModelInvocationResult(output=self.decisions.pop(0))


@dataclass
class AuditorScript:
    decision: AuditorDecision

    def __post_init__(self):
        self.requests = []

    async def audit(self, request):
        self.requests.append(request)
        return ModelInvocationResult(output=self.decision)


def _runtime(kind="outcome_proposed"):
    return compose_target_runtime(
        YieldPolicy(kind),
        ProductionActionOutcomeProjector(),
        UnknownEvaluator(),
        runtime_controls=("yield_subtask",),
    )


def _env_task():
    raw = raw_observation(
        ax_node("input", "textbox", "Answer", value="Done"),
        ax_node("button", "button", "Continue"),
        goal="Complete the long task.",
    )
    fake = FakeBrowserGym(raw)
    env, task = open_fake(fake)
    return fake, env, task


def _initial(contract):
    return ManagerDecision(
        ManagerAssessment.NOT_APPLICABLE,
        ManagerRoute.EXECUTE_SUBTASK,
        subtask=contract,
    )


def test_normal_episode_calls_initial_manager_and_one_combined_review_without_auditor() -> None:
    _, env, task = _env_task()
    contract = SubtaskContract("Read answer", "Answer is visible")
    manager = ManagerScript(
        [
            _initial(contract),
            ManagerDecision(
                ManagerAssessment.SATISFIED,
                ManagerRoute.BLOCKED,
                reason="Review completed; stop this synthetic witness.",
            ),
        ]
    )

    result = asyncio.run(MissionSupervisor(manager, None, max_rounds=1).run(_runtime(), env, task))

    assert result.manager_calls == 2
    assert result.auditor_calls == 0
    assert [request.mode for request in manager.requests] == [
        ManagerRequestMode.INITIAL_PLAN,
        ManagerRequestMode.REVIEW_AND_ROUTE,
    ]
    review = manager.requests[1]
    assert review.active_subtask == contract
    assert review.review_world is not None
    assert review.evidence_bundle.observation_id == review.review_world.observation_id


def test_stall_review_accepts_materially_changed_subtask() -> None:
    _, env, task = _env_task()
    first = SubtaskContract("Try route A", "Answer appears", episode_turn_budget=1)
    changed = SubtaskContract("Try route B", "Report table appears", episode_turn_budget=1)
    manager = ManagerScript(
        [
            _initial(first),
            ManagerDecision(
                ManagerAssessment.UNSATISFIED,
                ManagerRoute.EXECUTE_SUBTASK,
                subtask=changed,
            ),
        ]
    )

    result = asyncio.run(
        MissionSupervisor(manager, None, max_rounds=1).run(_runtime("stalled"), env, task)
    )

    assert result.outcome is MissionOutcome.ROUND_BUDGET_EXHAUSTED
    assert result.manager_calls == 2


def test_repeated_failed_strategy_returns_typed_strategy_not_changed_without_third_episode() -> None:
    _, env, task = _env_task()
    contract = SubtaskContract("Try route A", "Answer appears", episode_turn_budget=1)
    manager = ManagerScript(
        [
            _initial(contract),
            ManagerDecision(
                ManagerAssessment.UNSATISFIED,
                ManagerRoute.EXECUTE_SUBTASK,
                subtask=contract,
            ),
        ]
    )

    result = asyncio.run(
        MissionSupervisor(manager, None, max_rounds=3).run(_runtime("stalled"), env, task)
    )

    assert result.outcome is MissionOutcome.STRATEGY_NOT_CHANGED
    assert result.manager_calls == 2
    assert result.state.status is RunStatus.BLOCKED


def test_manager_satisfied_assessment_never_becomes_native_task_success() -> None:
    _, env, task = _env_task()
    contract = SubtaskContract("Read answer", "Answer is visible")
    manager = ManagerScript(
        [
            _initial(contract),
            ManagerDecision(ManagerAssessment.SATISFIED, ManagerRoute.BLOCKED),
        ]
    )

    result = asyncio.run(MissionSupervisor(manager, None, max_rounds=1).run(_runtime(), env, task))

    assert result.status is RunStatus.BLOCKED
    assert result.outcome is not MissionOutcome.TASK_COMPLETE


def test_explicit_strict_exceptional_claim_calls_optional_auditor_at_most_once() -> None:
    _, env, task = _env_task()
    contract = SubtaskContract(
        "Inspect irreversible result",
        "The durable claim is visible",
        related_audit_ids=("claim:durable",),
    )
    manager = ManagerScript(
        [
            _initial(contract),
            ManagerDecision(ManagerAssessment.SATISFIED, ManagerRoute.BLOCKED),
        ]
    )
    auditor = AuditorScript(
        AuditorDecision(ManagerAssessment.SATISFIED, reason="Strict claim is supported.")
    )

    result = asyncio.run(
        MissionSupervisor(
            manager,
            auditor,
            max_rounds=1,
            strict_verification=True,
        ).run(_runtime(), env, task)
    )

    assert result.auditor_calls == 1
    assert len(auditor.requests) == 1

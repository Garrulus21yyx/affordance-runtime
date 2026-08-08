import asyncio
from dataclasses import dataclass

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus, SelectAction
from affordance_runtime.confirmation import ConfirmationDecision, ConfirmationDecisionKind
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution import ActionError, ActionResult, DispatchStatus
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    ActionBinding,
    ActionRisk,
    CoverageState,
    SemanticTarget,
    StateFact,
    WorldObservation,
)


def _world(identity: str, enabled: bool, selector: str, *, risk: ActionRisk = ActionRisk.MEDIUM) -> WorldObservation:
    target = SemanticTarget("shared", "button", "Shared state", {"enabled": enabled})
    binding = ActionBinding(
        f"binding:{identity}",
        identity,
        identity,
        f"revision:{identity}",
        f"fingerprint:{identity}",
        target.target_id,
        target.target_id,
        "dom",
        "dom",
        "activate",
        "click",
        "local_reversible",
        ("shared_state_enabled",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"selector": selector},
        risk=risk,
    )
    fact = StateFact(f"fact:{identity}:enabled", target.target_id, "enabled", enabled, identity)
    return WorldObservation(identity, (target,), (fact,), (binding,), {"dom": CoverageState.COMPLETE})


def _task() -> TaskGoal:
    return TaskGoal(
        "shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=RiskProfile.MEDIUM,
    )


@dataclass
class FirstPolicy:
    calls: int = 0

    async def decide(self, context):
        task, world, action_space = context.task, context.world, context.actions
        recent_turns, optional_plan = context.history.items, context.progress.plan_summary
        del task, world, recent_turns, optional_plan
        self.calls += 1
        return SelectAction(context.context_id, action_space.options[0].action_id)


class TaskEvaluator:
    async def evaluate(self, task, observation):
        done = bool(observation.targets[0].state.get("enabled"))
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE if done else TaskEvaluationStatus.INCOMPLETE,
            "done" if done else "not done",
            completion_evidence_refs=(observation.facts[0].fact_id,) if done else (),
        )


class ActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, result
        changed = before.targets[0].state.get("enabled") != after.targets[0].state.get("enabled")
        return ActionEvaluation(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ActionEvaluationStatus.EFFECT_CONFIRMED
            if changed
            else ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
            "changed" if changed else "authoritatively unchanged",
            (after.facts[0].fact_id,),
        )


def _loop() -> AgentLoop:
    return AgentLoop(FirstPolicy(), ActionEvaluator(), TaskEvaluator())


def _decision(result, kind=ConfirmationDecisionKind.CONFIRM) -> ConfirmationDecision:
    request = result.confirmation_request
    assert request is not None
    return ConfirmationDecision(request.confirmation_id, request.subject_id, kind)


def test_confirmation_freshly_rebinds_selector_and_executes_once() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("old", False, "#old"), _world("fresh", False, "#fresh"), _world("after", True, "#after")],
            [ActionResult("*", DispatchStatus.SENT, "dom", True)],
        )
        policy = FirstPolicy()
        runner = AgentEpisodeRunner(AgentLoop(policy, ActionEvaluator(), TaskEvaluator()))
        session = await runner.start(environment, _task())
        paused = await session.run_until_pause()

        assert paused.status == AgentLoopStatus.WAITING_CONFIRMATION
        assert paused.execution_count == 0
        assert paused.confirmation_request is not None

        completed = await session.resolve_confirmation(_decision(paused))

        assert completed.status == AgentLoopStatus.DONE
        assert completed.execution_count == 1
        assert len(environment.executed_requests) == 1
        assert environment.executed_requests[0].binding.payload["selector"] == "#fresh"
        assert policy.calls == 1
        assert "#old" not in repr(paused.confirmation_request)
        assert "#fresh" not in repr(paused.confirmation_request)

    asyncio.run(scenario())


def test_confirmation_wrong_identity_and_deny_fail_closed_without_execution() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment([_world("old", False, "#old")])
        session = await AgentEpisodeRunner(_loop()).start(environment, _task())
        paused = await session.run_until_pause()
        request = paused.confirmation_request
        assert request is not None

        wrong = await session.resolve_confirmation(
            ConfirmationDecision("confirmation:wrong", request.subject_id, ConfirmationDecisionKind.CONFIRM)
        )
        assert wrong.status == AgentLoopStatus.BLOCKED
        assert environment.executed_requests == []

        denied_environment = StaticEnvironment([_world("old", False, "#old")])
        denied_session = await AgentEpisodeRunner(_loop()).start(denied_environment, _task())
        denied_pause = await denied_session.run_until_pause()
        denied = await denied_session.resolve_confirmation(_decision(denied_pause, ConfirmationDecisionKind.DENY))
        assert denied.status == AgentLoopStatus.CANCELLED
        assert denied_environment.executed_requests == []
        assert denied_session.state.pending_confirmation is None

    asyncio.run(scenario())


def test_confirmation_subject_change_requires_new_confirmation() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("old", False, "#old"), _world("fresh", False, "#fresh", risk=ActionRisk.HIGH)]
        )
        policy = FirstPolicy()
        loop = AgentLoop(policy, ActionEvaluator(), TaskEvaluator())
        session = await AgentEpisodeRunner(loop).start(environment, _task())
        paused = await session.run_until_pause()

        changed = await session.resolve_confirmation(_decision(paused))

        assert changed.status == AgentLoopStatus.WAITING_CONFIRMATION
        assert changed.confirmation_request is not None
        assert changed.confirmation_request.subject_id != paused.confirmation_request.subject_id
        assert environment.executed_requests == []
        assert policy.calls == 2

    asyncio.run(scenario())


def test_not_sent_does_not_consume_confirmation_and_freshly_rebinds() -> None:
    async def scenario() -> None:
        attempts = 0

        def execute(request, observation):
            del observation
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return ActionResult(
                    request.request_id,
                    DispatchStatus.NOT_SENT,
                    "dom",
                    False,
                    ActionError.STALE_BINDING,
                )
            return ActionResult(request.request_id, DispatchStatus.SENT, "dom", True)

        environment = StaticEnvironment(
            [
                _world("initial", False, "#initial"),
                _world("confirmed", False, "#confirmed"),
                _world("rebound", False, "#rebound"),
                _world("after", True, "#after"),
            ],
            execute_fn=execute,
        )
        session = await AgentEpisodeRunner(_loop()).start(environment, _task())
        paused = await session.run_until_pause()

        completed = await session.resolve_confirmation(_decision(paused))

        assert completed.status == AgentLoopStatus.DONE
        assert completed.execution_count == 1
        assert attempts == 2
        assert [item.binding.payload["selector"] for item in environment.executed_requests] == [
            "#confirmed",
            "#rebound",
        ]

    asyncio.run(scenario())


def test_sent_unknown_no_effect_consumes_confirmation_and_waits_without_replay() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [
                _world("initial", False, "#initial"),
                _world("confirmed", False, "#confirmed"),
                _world("after", False, "#after"),
            ],
            [
                ActionResult(
                    "*",
                    DispatchStatus.SENT_UNKNOWN,
                    "dom",
                    False,
                    ActionError.EXECUTION_FAILED,
                )
            ],
        )
        session = await AgentEpisodeRunner(_loop()).start(environment, _task())
        first = await session.run_until_pause()

        second = await session.resolve_confirmation(_decision(first))

        assert second.status == AgentLoopStatus.WAITING_USER
        assert second.execution_count == 1
        assert second.confirmation_request is None
        assert len(environment.executed_requests) == 1

    asyncio.run(scenario())


def test_sent_unknown_unknown_waits_for_user_and_never_replays() -> None:
    class UnknownEvaluator:
        async def evaluate(self, task, before, request, result, after):
            del task, result
            return ActionEvaluation(
                request.request_id,
                before.observation_id,
                after.observation_id,
                ActionEvaluationStatus.UNKNOWN,
                "coverage is insufficient",
            )

    async def scenario() -> None:
        environment = StaticEnvironment(
            [
                _world("initial", False, "#initial"),
                _world("confirmed", False, "#confirmed"),
                _world("after", False, "#after"),
            ],
            [
                ActionResult(
                    "*",
                    DispatchStatus.SENT_UNKNOWN,
                    "dom",
                    False,
                    ActionError.EXECUTION_FAILED,
                )
            ],
        )
        loop = AgentLoop(FirstPolicy(), UnknownEvaluator(), TaskEvaluator())
        session = await AgentEpisodeRunner(loop).start(environment, _task())
        paused = await session.run_until_pause()

        waiting = await session.resolve_confirmation(_decision(paused))

        assert waiting.status == AgentLoopStatus.WAITING_USER
        assert waiting.execution_count == 1
        assert session.state.pending_unknown_request is not None
        assert len(environment.executed_requests) == 1
        assert await session.run_until_pause() == waiting

    asyncio.run(scenario())


def test_confirmation_decision_cannot_be_reused_after_effectful_send() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("initial", False, "#initial"), _world("fresh", False, "#fresh"), _world("after", True, "#after")],
            [ActionResult("*", DispatchStatus.SENT, "dom", True)],
        )
        session = await AgentEpisodeRunner(_loop()).start(environment, _task())
        paused = await session.run_until_pause()
        decision = _decision(paused)
        completed = await session.resolve_confirmation(decision)
        assert completed.status == AgentLoopStatus.DONE

        reused = await session.resolve_confirmation(decision)

        assert reused is completed
        assert reused.status == AgentLoopStatus.DONE
        assert len(environment.executed_requests) == 1

    asyncio.run(scenario())


def test_confirmation_requires_a_fresh_observation_identity() -> None:
    async def scenario() -> None:
        repeated = _world("same", False, "#same")
        environment = StaticEnvironment([repeated, repeated])
        session = await AgentEpisodeRunner(_loop()).start(environment, _task())
        paused = await session.run_until_pause()

        result = await session.resolve_confirmation(_decision(paused))

        assert result.status == AgentLoopStatus.FAILED
        assert "identity" in result.message
        assert environment.executed_requests == []

    asyncio.run(scenario())

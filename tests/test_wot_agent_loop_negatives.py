import asyncio
from dataclasses import replace

import pytest
from target_agent_loop_support import SharedStateActionEvaluator, SharedStateTaskEvaluator
from test_wot_surface_adapter import FakeWotTransport, shared_td

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus, SelectAction
from affordance_runtime.evaluation import ActionEvaluation, ActionEvaluationStatus
from affordance_runtime.surfaces.wot import WotDeploymentScope
from affordance_runtime.surfaces.wot.adapter import WotSurfaceAdapter
from affordance_runtime.surfaces.wot.contracts import WotTransportResult, WotTransportStatus
from affordance_runtime.task import LoopBudget, RiskProfile, TaskGoal
from affordance_runtime.world import ActionBinder, ActionSpaceBuilder
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


def _task(risk=RiskProfile.LOW, turns: int = 2) -> TaskGoal:
    return TaskGoal(
        "shared",
        "Enable shared state",
        allowed_effects=("shared_state_enabled",),
        risk_profile=risk,
        loop_budget=LoopBudget(turns, turns + 1),
    )


class FirstPolicy:
    def __init__(self, parameters=None) -> None:
        self.parameters = parameters or {}

    async def decide(self, context):
        task, world, action_space = context.task, context.world, context.actions
        recent_turns, optional_plan = context.history.items, context.progress.plan_summary
        del task, world, recent_turns, optional_plan
        return SelectAction(context.context_id, action_space.options[0].action_id, self.parameters)


class MissingPolicy:
    async def decide(self, context):
        task, world, action_space = context.task, context.world, context.actions
        recent_turns, optional_plan = context.history.items, context.progress.plan_summary
        del task, world, action_space, recent_turns, optional_plan
        return SelectAction(context.context_id, "missing-wot-action")


class UnknownEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, result
        return ActionEvaluation(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ActionEvaluationStatus.UNKNOWN,
            "WoT outcome remains unknown",
        )


class NeverEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, before, request, result, after
        raise AssertionError("lineage mismatch must fail before evaluation")


class WrongLineageWorld(UnifiedWorldEnvironment):
    async def execute(self, request):
        outcome = await super().execute(request)
        return replace(outcome, result=replace(outcome.result, request_id="wrong-request"))


def _run(transport, task, policy, *, scope=WotDeploymentScope.LOCAL_SIMULATION, evaluator=None, world_type=UnifiedWorldEnvironment):
    adapter = WotSurfaceAdapter(transport, deployment_scope=scope)
    world = world_type((adapter,))
    loop = AgentLoop(policy, evaluator or SharedStateActionEvaluator(), SharedStateTaskEvaluator())
    return asyncio.run(AgentEpisodeRunner(loop).run(world, task))


@pytest.mark.parametrize(
    "key",
    ["href", "endpoint", "method", "backend", "security", "credential"],
)
def test_wot_policy_cannot_inject_private_transport_fields(key: str) -> None:
    transport = FakeWotTransport()
    result = _run(transport, _task(), FirstPolicy({key: "injected"}))
    assert result.status == AgentLoopStatus.BLOCKED
    assert result.execution_count == 0
    assert transport.action_endpoint_calls == 0


def test_missing_wot_action_id_has_zero_execution() -> None:
    transport = FakeWotTransport()
    result = _run(transport, _task(), MissingPolicy())
    assert result.status == AgentLoopStatus.BLOCKED
    assert result.execution_count == 0
    assert transport.action_endpoint_calls == 0


@pytest.mark.parametrize("scope", [WotDeploymentScope.PHYSICAL_DEVICE, WotDeploymentScope.REMOTE_SERVICE])
def test_nonlocal_wot_scope_waits_for_confirmation(scope) -> None:
    transport = FakeWotTransport()
    result = _run(transport, _task(), FirstPolicy(), scope=scope)
    assert result.status == AgentLoopStatus.WAITING_CONFIRMATION
    assert result.execution_count == 0
    assert transport.action_endpoint_calls == 0


@pytest.mark.parametrize("risk", [RiskProfile.MEDIUM, RiskProfile.HIGH])
def test_medium_and_high_wot_task_waits_for_confirmation(risk) -> None:
    transport = FakeWotTransport()
    result = _run(transport, _task(risk), FirstPolicy())
    assert result.status == AgentLoopStatus.WAITING_CONFIRMATION
    assert result.execution_count == 0
    assert transport.action_endpoint_calls == 0


def test_wot_transport_success_without_property_change_is_not_complete() -> None:
    transport = FakeWotTransport()
    transport.apply_effect = False
    result = _run(transport, _task(turns=1), FirstPolicy())
    assert result.status != AgentLoopStatus.DONE
    assert result.execution_count == 1
    assert transport.action_endpoint_calls == 1


def test_wot_sent_unknown_confirmed_by_fresh_property_is_done_without_replay() -> None:
    transport = FakeWotTransport()
    transport.action_result = WotTransportResult(WotTransportStatus.SENT_UNKNOWN, False, "timeout")
    result = _run(transport, _task(), FirstPolicy())
    assert result.status == AgentLoopStatus.DONE
    assert result.execution_count == 1
    assert transport.action_endpoint_calls == 1


def test_wot_sent_unknown_and_unknown_property_waits_without_replay() -> None:
    transport = FakeWotTransport()
    transport.apply_effect = False
    transport.action_result = WotTransportResult(WotTransportStatus.SENT_UNKNOWN, False, "timeout")
    result = _run(transport, _task(), FirstPolicy(), evaluator=UnknownEvaluator())
    assert result.status == AgentLoopStatus.WAITING_USER
    assert result.execution_count == 1
    assert transport.action_endpoint_calls == 1


def test_wot_wrong_result_lineage_fails_before_evaluation() -> None:
    transport = FakeWotTransport()
    result = _run(
        transport,
        _task(),
        FirstPolicy(),
        evaluator=NeverEvaluator(),
        world_type=WrongLineageWorld,
    )
    assert result.status == AgentLoopStatus.FAILED
    assert result.execution_count == 1
    assert transport.action_endpoint_calls == 1


def test_wot_effect_legality_and_exact_binding_prevent_route_escape() -> None:
    async def scenario() -> None:
        transport = FakeWotTransport()
        adapter = WotSurfaceAdapter(transport, deployment_scope=WotDeploymentScope.LOCAL_SIMULATION)
        world = UnifiedWorldEnvironment((adapter,))
        acquisition_task = _task()
        acquisition = await world.reset(acquisition_task)
        assert acquisition.observation is not None
        observed = acquisition.observation
        allowed = observed.bindings[0]
        forbidden = replace(
            allowed,
            binding_id=allowed.binding_id + ":forbidden",
            semantic_effects=("forbidden_effect",),
            confidence=1.0,
        )
        observed = replace(observed, bindings=(forbidden, allowed))
        constrained = replace(
            acquisition_task,
            allowed_effects=("shared_state_enabled", "forbidden_effect"),
            forbidden_effects=("forbidden_effect",),
        )
        space = ActionSpaceBuilder().build(constrained, observed)
        assert len(space.options) == 1
        request = ActionBinder().bind(
            ActionSpaceBuilder().admit(space.options[0], {}), observed, "context:test"
        )
        assert request.binding.binding_id == allowed.binding_id

        unrelated = TaskGoal(
            "other",
            "Send message",
            allowed_effects=("message_sent",),
            risk_profile=RiskProfile.LOW,
        )
        assert ActionSpaceBuilder().build(unrelated, observed).options == ()

    asyncio.run(scenario())


def test_unresolved_security_and_event_subscription_offer_no_wot_action() -> None:
    async def scenario() -> None:
        transport = FakeWotTransport(shared_td(security="missing"))
        adapter = WotSurfaceAdapter(transport, deployment_scope=WotDeploymentScope.LOCAL_SIMULATION)
        world = UnifiedWorldEnvironment((adapter,))
        acquisition = await world.reset(_task())
        assert acquisition.observation is not None
        observed = acquisition.observation
        assert ActionSpaceBuilder().build(_task(), observed).options == ()
        assert observed.sources[0].artifacts["unsupported_events"] == ("changed",)

    asyncio.run(scenario())

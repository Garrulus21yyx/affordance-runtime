import asyncio
from dataclasses import replace

import pytest
from model_policy_support import ScriptedStructuredDecisionPort, first_action_model_policy
from test_action_paging import _paging_task, _two_action_world
from test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _sent, _task, _world
from test_confirmation_continuation import ActionEvaluator as ConfirmationActionEvaluator
from test_confirmation_continuation import TaskEvaluator as ConfirmationTaskEvaluator
from test_confirmation_continuation import _decision as confirmation_decision
from test_confirmation_continuation import _task as confirmation_task
from test_confirmation_continuation import _world as confirmation_world
from test_model_policy_admission import (
    _ActionEvaluator as DestinationActionEvaluator,
)
from test_model_policy_admission import (
    _destination_task,
    _destination_world,
)
from test_model_policy_admission import (
    _TaskEvaluator as DestinationTaskEvaluator,
)

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus
from affordance_runtime.model_boundary import ContextBuilder, ContextProjectionBudget
from affordance_runtime.model_policy import ModelBackedAgentPolicy
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import ActionPager, ActionSpaceBuilder, ObservationSourceProfile, SurfaceObservation


class FakeWaiter:
    def __init__(self) -> None:
        self.waits = []

    async def wait(self, max_wait_ms: int) -> None:
        self.waits.append(max_wait_ms)


def test_model_policy_can_page_then_select_from_the_exact_next_page() -> None:
    def script(context, call):
        if call == 1:
            return {
                "type": "request_action_page",
                "context_id": context["context_id"],
                "query": "",
                "target_id": "",
                "relevance_role": "",
                "cursor": context["actions"]["next_cursor"],
            }
        option = context["actions"]["options"][0]
        return {
            "type": "select_action",
            "context_id": context["context_id"],
            "action_id": option["action_id"],
            "parameters": {},
            "destination_id": "",
        }

    async def scenario() -> None:
        port = ScriptedStructuredDecisionPort(script)
        environment = StaticEnvironment(
            [_two_action_world("before", False), _two_action_world("after", True)],
            [_sent()],
        )
        result = await AgentEpisodeRunner(
            AgentLoop(
                ModelBackedAgentPolicy(port),
                SharedActionEvaluator(),
                SharedTaskEvaluator(),
                context_builder=ContextBuilder(pager=ActionPager(page_size=1)),
            )
        ).run(environment, _paging_task())

        assert result.status == AgentLoopStatus.DONE
        assert port.calls == 2 and len(set(port.context_ids)) == 2
        assert result.execution_count == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ("observation", "wait"))
def test_model_policy_observation_and_wait_receive_a_fresh_context(kind: str) -> None:
    def script(context, call):
        if call == 2:
            return {"type": "abort", "context_id": context["context_id"], "reason": "proof complete", "category": "policy"}
        if kind == "wait":
            return {"type": "wait", "context_id": context["context_id"], "reason": "settle", "max_wait_ms": 5}
        capability = context["world"]["observation_capabilities"][0]
        return {
            "type": "request_observation",
            "context_id": context["context_id"],
            "subject_id": "shared-toggle",
            "modality": capability["modality"],
            "required_assurance": capability["assurance"],
            "reason": "refresh",
        }

    async def scenario() -> None:
        port = ScriptedStructuredDecisionPort(script)
        waiter = FakeWaiter()
        result = await AgentEpisodeRunner(
            AgentLoop(
                ModelBackedAgentPolicy(port),
                SharedActionEvaluator(),
                SharedTaskEvaluator(),
                wait_controller=waiter,
            )
        ).run(StaticEnvironment([_world("before", False), _world("fresh", False)]), _task())

        assert result.status == AgentLoopStatus.FAILED
        assert len(set(port.context_ids)) == 2
        assert result.observation_count == 2 and result.execution_count == 0
        assert waiter.waits == ([5] if kind == "wait" else [])

    asyncio.run(scenario())


def test_model_propose_done_still_requires_the_deterministic_task_evaluator() -> None:
    def script(context, call):
        if call == 1:
            evidence = context["world"]["facts"]["items"][0]["fact_ref"]
            return {
                "type": "propose_done",
                "context_id": context["context_id"],
                "claimed_criteria": [],
                "evidence_refs": [evidence],
                "result_summary": "claimed done",
                "unresolved_items": [],
            }
        return {"type": "abort", "context_id": context["context_id"], "reason": "validator retained", "category": "policy"}

    class CountingEvaluator(SharedTaskEvaluator):
        def __init__(self) -> None:
            self.calls = 0

        async def evaluate(self, task, observation):
            self.calls += 1
            return await super().evaluate(task, observation)

    async def scenario() -> None:
        evaluator = CountingEvaluator()
        port = ScriptedStructuredDecisionPort(script)
        result = await AgentEpisodeRunner(
            AgentLoop(ModelBackedAgentPolicy(port), SharedActionEvaluator(), evaluator)
        ).run(StaticEnvironment([_world("before", False)]), _task())

        assert result.status == AgentLoopStatus.FAILED
        assert evaluator.calls == 2
        assert result.execution_count == 0

    asyncio.run(scenario())


def test_model_propose_done_can_reference_current_artifact_without_bypassing_evaluator() -> None:
    def script(context, call):
        if call == 1:
            evidence = context["world"]["artifact_summaries"]["items"][0]["evidence_ref"]
            return {
                "type": "propose_done",
                "context_id": context["context_id"],
                "claimed_criteria": [],
                "evidence_refs": [evidence],
                "result_summary": "artifact available",
                "unresolved_items": [],
            }
        return {"type": "abort", "context_id": context["context_id"], "reason": "not complete", "category": "policy"}

    class CountingEvaluator(SharedTaskEvaluator):
        def __init__(self) -> None:
            self.calls = 0

        async def evaluate(self, task, observation):
            self.calls += 1
            return await super().evaluate(task, observation)

    async def scenario() -> None:
        observation = _world("artifact", False)
        source = SurfaceObservation(
            observation.observation_id,
            "dom",
            "revision:artifact",
            ObservationSourceProfile.dom(),
            artifacts={"receipt": {"path": "/private/receipt", "value": "raw-secret"}},
        )
        observation = replace(observation, sources=(source,))
        evaluator = CountingEvaluator()
        port = ScriptedStructuredDecisionPort(script)

        result = await AgentEpisodeRunner(
            AgentLoop(ModelBackedAgentPolicy(port), SharedActionEvaluator(), evaluator)
        ).run(StaticEnvironment([observation]), _task())

        assert result.status == AgentLoopStatus.FAILED
        assert evaluator.calls == 2
        assert result.execution_count == 0
        request = port.requests[0].serialized_context
        assert "artifact:artifact:receipt" in request
        assert "/private/receipt" not in request and "raw-secret" not in request

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("claimed", "unresolved"),
    ((["criterion:invented"], []), ([], ["still pending"])),
)
def test_model_propose_done_rejects_unknown_criteria_and_unresolved_items(claimed, unresolved) -> None:
    def script(context, call):
        del call
        return {
            "type": "propose_done",
            "context_id": context["context_id"],
            "claimed_criteria": claimed,
            "evidence_refs": [],
            "result_summary": "done",
            "unresolved_items": unresolved,
        }

    async def scenario() -> None:
        environment = StaticEnvironment([_world("before", False)])
        result = await AgentEpisodeRunner(
            AgentLoop(
                ModelBackedAgentPolicy(ScriptedStructuredDecisionPort(script)),
                SharedActionEvaluator(),
                SharedTaskEvaluator(),
            )
        ).run(environment, _task())
        assert result.status == AgentLoopStatus.BLOCKED
        assert result.execution_count == result.currentness_probe_count == 0

    asyncio.run(scenario())


def test_stale_model_context_response_is_zero_execution() -> None:
    def script(context, call):
        del call
        return {
            "type": "select_action",
            "context_id": "context:stale",
            "action_id": context["actions"]["options"][0]["action_id"],
            "parameters": {},
            "destination_id": "",
        }

    async def scenario() -> None:
        port = ScriptedStructuredDecisionPort(script)
        environment = StaticEnvironment([_world("before", False)])
        result = await AgentEpisodeRunner(
            AgentLoop(ModelBackedAgentPolicy(port), SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status == AgentLoopStatus.FAILED
        assert port.calls == 1
        assert result.execution_count == 0 and environment.executed_requests == []

    asyncio.run(scenario())


def test_model_hidden_action_and_destination_are_rejected_by_runtime_admission() -> None:
    async def hidden_action() -> None:
        before = _two_action_world("before", False)
        hidden_id = ActionSpaceBuilder().build(_paging_task(), before).options[1].action_id

        def script(context, call):
            del call
            return {
                "type": "select_action",
                "context_id": context["context_id"],
                "action_id": hidden_id,
                "parameters": {},
                "destination_id": "",
            }

        environment = StaticEnvironment([before])
        result = await AgentEpisodeRunner(
            AgentLoop(
                ModelBackedAgentPolicy(ScriptedStructuredDecisionPort(script)),
                SharedActionEvaluator(),
                SharedTaskEvaluator(),
                context_builder=ContextBuilder(pager=ActionPager(page_size=1)),
            )
        ).run(environment, _paging_task())
        assert result.status == AgentLoopStatus.BLOCKED and environment.executed_requests == []

    async def hidden_destination() -> None:
        def script(context, call):
            del call
            return {
                "type": "select_action",
                "context_id": context["context_id"],
                "action_id": context["actions"]["options"][0]["action_id"],
                "parameters": {},
                "destination_id": "person:bob",
            }

        environment = StaticEnvironment([_destination_world("before", False)])
        result = await AgentEpisodeRunner(
            AgentLoop(
                ModelBackedAgentPolicy(ScriptedStructuredDecisionPort(script)),
                DestinationActionEvaluator(),
                DestinationTaskEvaluator(),
                context_builder=ContextBuilder(ContextProjectionBudget(max_destinations_per_option=1)),
            )
        ).run(environment, _destination_task())
        assert result.status == AgentLoopStatus.BLOCKED and environment.executed_requests == []

    asyncio.run(hidden_action())
    asyncio.run(hidden_destination())


@pytest.mark.parametrize("private_key", ("selector", "href", "backend"))
def test_model_private_execution_parameters_are_typed_failure_and_zero_execution(private_key: str) -> None:
    def script(context, call):
        del call
        return {
            "type": "select_action",
            "context_id": context["context_id"],
            "action_id": context["actions"]["options"][0]["action_id"],
            "parameters": {"nested": {private_key: "private"}},
            "destination_id": "",
        }

    async def scenario() -> None:
        environment = StaticEnvironment([_world("before", False)])
        result = await AgentEpisodeRunner(
            AgentLoop(
                ModelBackedAgentPolicy(ScriptedStructuredDecisionPort(script)),
                SharedActionEvaluator(),
                SharedTaskEvaluator(),
            )
        ).run(environment, _task())

        assert result.status == AgentLoopStatus.FAILED
        assert result.execution_count == 0 and environment.executed_requests == []

    asyncio.run(scenario())


def test_runtime_confirmation_wraps_model_policy_and_does_not_make_a_second_model_call() -> None:
    async def scenario() -> None:
        policy = first_action_model_policy()
        environment = StaticEnvironment(
            [
                confirmation_world("old", False, "#old"),
                confirmation_world("fresh", False, "#fresh"),
                confirmation_world("after", True, "#after"),
            ],
            [_sent()],
        )
        session = await AgentEpisodeRunner(
            AgentLoop(policy, ConfirmationActionEvaluator(), ConfirmationTaskEvaluator())
        ).start(environment, confirmation_task())
        paused = await session.run_until_pause()

        completed = await session.resolve_confirmation(confirmation_decision(paused))

        assert paused.status == AgentLoopStatus.WAITING_CONFIRMATION
        assert completed.status == AgentLoopStatus.DONE
        assert policy.port.calls == 1
        assert environment.executed_requests[0].binding.payload["selector"] == "#fresh"

    asyncio.run(scenario())
